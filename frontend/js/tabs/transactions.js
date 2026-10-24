// 📋 Transactions: filter, correct categories (k-NN learns), label necessity (ID3 learns), delete, export.

import { api } from "../api.js";
import { empty, errorText, esc, money, monthName, state, toast } from "../ui.js";

const filters = { month: "", category: "", q: "" };

export async function render(node, ctx) {
  const d = await api.get("/api/transactions", filters);
  if (!state.meta.months.length) {
    node.innerHTML = `<h2>All transactions</h2>${empty("Nothing here yet.")}`;
    return;
  }
  const allCats = state.meta.categories.all;
  const option = (v, label, selected) => `<option value="${esc(v)}" ${selected ? "selected" : ""}>${esc(label)}</option>`;

  const rows = d.rows.map((r) => `<tr data-id="${r.id}" data-category="${esc(r.category)}" data-necessity="${esc(r.necessity ?? "")}">
    <td class="num">${r.id}</td>
    <td>${esc(r.date)}</td>
    <td>${esc(r.description)}</td>
    <td class="num">${esc(money(r.amount))}</td>
    <td>${esc(r.type)}</td>
    <td><select class="f-category" aria-label="Category">${allCats.map((c) => option(c, c, c === r.category)).join("")}</select></td>
    <td><select class="f-necessity" aria-label="My label">
      ${["", "Reasonable", "Unnecessary"].map((v) => option(v, v || "–", v === (r.necessity ?? ""))).join("")}
    </select></td>
    <td>${esc(r.member)}</td>
    <td title="manual = you chose · knn = predicted · demo = sample data">${esc(r.source)}</td>
    <td><input type="checkbox" class="f-delete" aria-label="Delete"></td>
  </tr>`).join("");

  node.innerHTML = `
    <h2>All transactions</h2>
    <div class="grid cols-3">
      <label class="field"><span>Month</span><select id="tx-month">
        ${option("", "All", !filters.month)}
        ${state.meta.months.map((m) => option(m, monthName(m), m === filters.month)).join("")}
      </select></label>
      <label class="field"><span>Category</span><select id="tx-cat">
        ${option("", "All", !filters.category)}
        ${d.categories.map((c) => option(c, c, c === filters.category)).join("")}
      </select></label>
      <label class="field"><span>Search description</span><input id="tx-q" value="${esc(filters.q)}"></label>
    </div>
    <p class="muted mt">Teach the models: fix a wrong <b>category</b> (k-NN learns it) or label an expense
      <b>Reasonable / Unnecessary</b> (the decision tree learns it). Tick <b>Delete</b> to remove a row.</p>
    <div class="table-wrap tall"><table>
      <thead><tr><th class="num">id</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>Type</th>
        <th>Category</th><th>My label</th><th>Member</th><th>Source</th><th>Delete</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="10" class="muted">No matching transactions.</td></tr>`}</tbody>
    </table></div>
    <div class="row mt">
      <button id="apply" class="btn" hidden></button>
      <span class="spacer"></span>
      <a class="btn secondary" href="${esc(api.exportUrl("/api/transactions/export.csv", filters))}" download>⬇️ Export CSV</a>
    </div>`;

  // ---- filters
  const rerender = () => ctx.refresh();
  node.querySelector("#tx-month").addEventListener("change", (e) => { filters.month = e.target.value; rerender(); });
  node.querySelector("#tx-cat").addEventListener("change", (e) => { filters.category = e.target.value; rerender(); });
  let timer;
  node.querySelector("#tx-q").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => { filters.q = e.target.value; rerender(); }, 350);
  });

  // ---- pending edits
  const applyBtn = node.querySelector("#apply");
  const changes = () => [...node.querySelectorAll("tbody tr[data-id]")].map((tr) => ({
    tr,
    id: Number(tr.dataset.id),
    category: tr.querySelector(".f-category").value,
    necessity: tr.querySelector(".f-necessity").value,
    del: tr.querySelector(".f-delete").checked,
  })).filter((c) => c.del || c.category !== c.tr.dataset.category || c.necessity !== c.tr.dataset.necessity);

  const update = () => {
    for (const tr of node.querySelectorAll("tbody tr[data-id]")) tr.classList.remove("changed", "to-delete");
    const pending = changes();
    for (const c of pending) c.tr.classList.add(c.del ? "to-delete" : "changed");
    applyBtn.hidden = !pending.length;
    applyBtn.textContent = `Apply ${pending.length} change(s)`;
  };
  node.querySelector("tbody").addEventListener("change", update);

  applyBtn.addEventListener("click", async () => {
    applyBtn.disabled = true;
    try {
      for (const c of changes()) {
        if (c.del) {
          await api.del(`/api/transactions/${c.id}`);
          continue;
        }
        const patch = {};
        if (c.category !== c.tr.dataset.category) patch.category = c.category;
        if (c.necessity !== c.tr.dataset.necessity) patch.necessity = c.necessity;
        await api.patch(`/api/transactions/${c.id}`, patch);
      }
      toast("Changes applied. The models will learn from them.");
    } catch (err) {
      toast(errorText(err), "error");
    }
    await ctx.refresh();
  });
}

export function mounted(node) {
  // Keep focus in the search box while typing (the tab re-renders on each search).
  const q = node.querySelector("#tx-q");
  if (q && filters.q) {
    q.focus();
    q.setSelectionRange(q.value.length, q.value.length);
  }
}
