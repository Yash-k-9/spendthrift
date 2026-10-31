// ➕ Add / Import: add a transaction (auto-categorized by k-NN), probe k-NN, import a CSV statement.

import { api } from "../api.js";
import { alertBox, bar, errorText, esc, money, state, table, toast } from "../ui.js";

const AUTO = "__auto__";
let preview = null;   // rows waiting to be imported

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export async function render(node, ctx) {
  const cats = state.meta.categories.all;
  preview = null;
  node.innerHTML = `
    <div class="grid cols-2">
      <div>
        <h2>Add a transaction</h2>
        <form id="add-form" class="card stack">
          <div class="radio-group" role="radiogroup" aria-label="Type">
            <label><input type="radio" name="type" value="expense" checked> expense</label>
            <label><input type="radio" name="type" value="income"> income</label>
          </div>
          <label class="field"><span>Description</span>
            <input name="description" required maxlength="200" placeholder="e.g. Swiggy dinner, Electricity bill, Salary"></label>
          <label class="field"><span>Amount (${esc(state.meta.settings.currency)})</span>
            <input name="amount" type="number" min="0" step="any" required></label>
          <div class="grid cols-2">
            <label class="field"><span>Date</span><input name="date" type="date" value="${today()}" required></label>
            <label class="field"><span>Family member</span><input name="member" value="Family" maxlength="64"></label>
          </div>
          <label class="field"><span>Category</span>
            <select name="category">
              <option value="${AUTO}">🤖 Auto-detect (k-NN)</option>
              ${cats.map((c) => `<option>${esc(c)}</option>`).join("")}
            </select></label>
          <div><button type="submit" class="btn">Add</button></div>
        </form>
        <div id="add-result"></div>

        <details class="panel mt">
          <summary>🔎 See how k-NN decides</summary>
          <div class="stack">
            <label class="field"><span>Try a description</span><input id="probe" value="UPI/BLINKIT/7781"></label>
            <div class="radio-group">
              <label><input type="radio" name="probe-type" value="expense" checked> expense</label>
              <label><input type="radio" name="probe-type" value="income"> income</label>
            </div>
            <div id="probe-result"></div>
          </div>
        </details>
      </div>

      <div>
        <h2>Import a bank statement (PDF or CSV)</h2>
        <p class="muted"><b>PDF:</b> the statement downloaded from net banking, or a UPI-app history (PhonePe, Paytm,
          Google Pay). Password-protected statements are supported. Scanned images aren't.</p>
        <p class="muted"><b>CSV:</b> columns <code>date</code>, <code>description</code>, <code>amount</code>, and
          optionally <code>type</code> (income/expense) and <code>member</code>. Without <code>type</code>, negative
          amounts are expenses.</p>
        <div class="card stack">
          <input id="csv-file" type="file" accept=".pdf,.csv,application/pdf,text/csv">
          <form id="pdf-password" class="row" hidden>
            <label class="field" style="flex:1"><span id="pw-label">This PDF is password-protected</span>
              <input name="password" type="password" autocomplete="off" placeholder="Statement password"></label>
            <button type="submit" class="btn" style="align-self:flex-end">Open</button>
          </form>
          <div id="import-preview"></div>
        </div>
      </div>
    </div>`;

  // ---- add form
  const form = node.querySelector("#add-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const description = form.description.value.trim();
    const amount = Number(form.amount.value);
    const result = node.querySelector("#add-result");
    if (!description || !(amount > 0)) {
      result.innerHTML = alertBox("error", "Enter a description and an amount above zero.");
      return;
    }
    const category = form.category.value === AUTO ? null : form.category.value;
    try {
      const r = await api.post("/api/transactions", {
        type: form.type.value, description, amount, date: form.date.value,
        member: form.member.value.trim() || "Family", category,
      });
      let note = "";
      if (r.source === "knn") {
        note = `: k-NN confidence ${(r.confidence * 100).toFixed(0)}%`;
        if (r.needs_review) note += `. ⚠️ Not sure, please check it in <a href="#transactions">📋 Transactions</a>`;
      }
      result.innerHTML = alertBox("success",
        `Added <b>${esc(description)}</b> (${esc(money(amount))}) as <b>${esc(r.category)}</b>${note}`);
      form.description.value = "";
      form.amount.value = "";
      await ctx.refresh({ keepView: true });
    } catch (err) {
      result.innerHTML = alertBox("error", esc(errorText(err)));
    }
  });

  // ---- k-NN probe
  const probe = node.querySelector("#probe");
  let probeTimer;
  const runProbe = () => {
    clearTimeout(probeTimer);
    probeTimer = setTimeout(async () => {
      const out = node.querySelector("#probe-result");
      const text = probe.value.trim();
      if (!text) { out.innerHTML = ""; return; }
      const type = node.querySelector("input[name=probe-type]:checked").value;
      try {
        const p = await api.get("/api/knn/predict", { description: text, type });
        out.innerHTML = `<p>Prediction: <b>${esc(p.category)}</b> · confidence ${(p.confidence * 100).toFixed(0)}%
          ${p.needs_review ? " · ⚠️ needs review" : ""}</p>
          ${table(p.neighbours, [
            { key: "description", label: "Nearest known description" },
            { key: "category", label: "Category" },
            { key: "similarity", label: "Similarity",
              format: (v) => `<div class="row">${bar(v)}<span>${v.toFixed(2)}</span></div>` },
          ])}`;
      } catch (err) {
        out.innerHTML = alertBox("error", esc(errorText(err)));
      }
    }, 250);
  };
  probe.addEventListener("input", runProbe);
  for (const r of node.querySelectorAll("input[name=probe-type]")) r.addEventListener("change", runProbe);
  runProbe();

  // ---- statement import (PDF or CSV)
  const fileInput = node.querySelector("#csv-file");
  const pwForm = node.querySelector("#pdf-password");
  const out = node.querySelector("#import-preview");

  const showPreview = (res) => {
    preview = res.rows;
    const fresh = () => preview.filter((r) => !(r.duplicate && skipDupes()));
    const skipDupes = () => out.querySelector("#skip-dupes")?.checked ?? true;
    const source = res.format === "pdf"
      ? `PDF · ${res.pages} page(s) · read from ${res.method === "tables" ? "tables" : "text lines"}`
      : "CSV";
    const notes = [];
    if (res.duplicates) notes.push(`${res.duplicates} look already recorded (same date, amount and type)`);
    if (res.unresolved) notes.push(`${res.unresolved} where debit/credit couldn't be told apart (set to expense)`);
    if (res.balance_mismatches) notes.push(`${res.balance_mismatches} that didn't match the running balance`);
    out.innerHTML = `
      ${table(res.rows, [
        { key: "date", label: "Date" },
        { key: "description", label: "Description" },
        { key: "amount", label: "Amount", num: true,
          format: (v, r) => `${r.type === "income" ? "+" : ""}${esc(money(v))}${r.type_guessed ? " ⚠️" : ""}` },
        { key: "type", label: "Type" },
        { key: "category", label: "Category", format: (v, r) => `${esc(v)}${r.needs_review ? " ⚠️" : ""}` },
        { key: "confidence", label: "Confidence",
          format: (v) => `<div class="row">${bar(v)}<span>${v.toFixed(2)}</span></div>` },
        { key: "duplicate", label: "", format: (v) => (v ? `<span class="pill muted-pill">already recorded?</span>` : "") },
      ], "medium")}
      <p class="muted">${esc(source)} · ${res.rows.length} rows categorized by k-NN · ${res.unsure} to double-check ⚠️</p>
      ${notes.length ? alertBox("warning", notes.map(esc).join("<br>")) : ""}
      ${res.duplicates ? `<label class="row"><input type="checkbox" id="skip-dupes" checked>
        Skip the ${res.duplicates} likely duplicates</label>` : ""}
      <button id="do-import" class="btn"></button>`;
    const btn = out.querySelector("#do-import");
    const label = () => {
      const n = fresh().length;
      btn.textContent = `Import ${n} transactions`;
      btn.disabled = n === 0;
    };
    label();
    out.querySelector("#skip-dupes")?.addEventListener("change", label);
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const rows = fresh().map(({ confidence, needs_review, type_guessed, duplicate, ...r }) => r);
        const { added } = await api.post("/api/import", rows);
        toast(`Imported ${added} transactions.`);
        fileInput.value = "";
        out.innerHTML = alertBox("success", `Imported ${added} transactions. They're encrypted and signed like every other entry.`);
        preview = null;
        await ctx.refresh({ keepView: true });
      } catch (err) {
        btn.disabled = false;
        toast(errorText(err), "error");
      }
    });
  };

  const readStatement = async (password) => {
    const file = fileInput.files[0];
    preview = null;
    if (!file) { out.innerHTML = ""; pwForm.hidden = true; return; }
    out.innerHTML = `<p class="muted">Reading ${esc(file.name)} and categorizing with k-NN…</p>`;
    try {
      const res = await api.upload("/api/import/preview", file, { password });
      if (res.password_required) {
        pwForm.hidden = false;
        node.querySelector("#pw-label").textContent = res.wrong_password
          ? "Wrong password, please try again" : "This PDF is password-protected";
        out.innerHTML = `<p class="muted">Banks usually set this to something like your customer ID or date of
          birth; the statement email says which. The password is only used to open the file and isn't stored.</p>`;
        pwForm.password.value = "";
        pwForm.password.focus();
        return;
      }
      pwForm.hidden = true;
      showPreview(res);
    } catch (err) {
      out.innerHTML = alertBox("error", esc(errorText(err)));
    }
  };

  fileInput.addEventListener("change", () => readStatement());
  pwForm.addEventListener("submit", (e) => {
    e.preventDefault();
    readStatement(pwForm.password.value);
  });
}
