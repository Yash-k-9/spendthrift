// 📱 SMS & Security: demo bank SMS, test the parser, phone setup (network URL), and the encrypted ledger's integrity.

import { api } from "../api.js";
import { alertBox, errorText, esc, metric, money, table, toast } from "../ui.js";

let lastDemo = null;   // results of the last demo run, shown again after the tab redraws

const SAMPLE = {
  sender: "VM-HDFCBK",
  body: "Sent Rs.450.00 From HDFC Bank A/C *1234 To SWIGGY On 28/10/26 Ref 429812345678 Not You? Call 18002586161",
};

function resultHtml(r) {
  if (!r.ok || !r.stored) {
    return `<div class="sms-result rejected">
      <div class="sms-head"><b>${esc(r.sender)}</b><span class="pill muted-pill">not stored</span></div>
      <div class="sms-body">${esc(r.body)}</div>
      <div class="muted">${esc(r.reason)}</div>
    </div>`;
  }
  const t = r.transaction;
  return `<div class="sms-result">
    <div class="sms-head"><b>${esc(r.sender)}</b><span class="pill">🔒 encrypted &amp; signed · #${t.id}</span></div>
    <div class="sms-body">${esc(r.body)}</div>
    <div class="sms-parsed">→ <b>${esc(t.description)}</b> · ${esc(money(t.amount))} · ${esc(t.type)} · ${esc(t.date)}
      · <b>${esc(t.category)}</b> (k-NN ${(t.confidence * 100).toFixed(0)}%)${t.needs_review ? " ⚠️ check" : ""}</div>
  </div>`;
}

function securityHtml(s) {
  const i = s.integrity;
  const status = i.ok
    ? alertBox("success", `✅ <b>Ledger verified.</b> ${i.rows_checked} rows checked: every hash links to the one before,
        every signature is valid and every record decrypts.${i.deleted ? ` ${i.deleted} deleted (redacted) rows still verify.` : ""}`)
    : alertBox("error", `❌ <b>Integrity problems found (${i.problems.length}).</b>
        <ul class="tips">${i.problems.slice(0, 8).map((p) => `<li>${p.id ? `Row #${p.id}: ` : ""}${esc(p.issue)}</li>`).join("")}</ul>`);
  const algos = Object.entries(s.algorithms).map(([k, v]) => `<li><b>${esc(k.replace("_", " "))}:</b> ${esc(v)}</li>`).join("");
  return `
    ${status}
    ${s.legacy_plaintext_rows ? alertBox("warning", `⚠️ ${s.legacy_plaintext_rows} transactions are still in the old
      <b>unencrypted</b> table. Run <code>python scripts/encrypt_legacy.py</code> to move them into the encrypted ledger.`) : ""}
    <div class="card mt">
      <h3>How each transaction is protected</h3>
      <ul class="tips">${algos}</ul>
      <p class="muted">Key fingerprint <code>${esc(s.keys.encryption_key)}</code> · keys live in <code>.env</code>,
        never in the database. Back that file up: without it the data can't be decrypted.</p>
      <p class="muted">Chain head <code>${esc(i.head.slice(0, 24))}…</code></p>
      <button id="verify" class="btn secondary">🔁 Verify integrity again</button>
    </div>`;
}

export async function render(node, ctx) {
  const [net, recent, sec] = await Promise.all([api.get("/api/network"), api.get("/api/sms/recent"),
    api.get("/api/security")]);

  const urls = net.sms_urls.length
    ? net.sms_urls.map((u) => `<code>${esc(u)}</code>`).join("<br>")
    : `<span class="muted">No Wi-Fi/LAN address found.</span>`;
  const appUrls = net.app_urls.map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a>`).join("<br>");

  node.innerHTML = `
    <h2>📱 Bank SMS capture</h2>
    <p class="muted">Every bank SMS goes through: <b>parse → k-NN category → AES-256-GCM encrypt → hash chain → Ed25519 sign
      → store</b>. OTPs and promotional messages are rejected.</p>

    <div class="grid cols-2">
      <div class="card stack">
        <h3>🧪 Demo mode</h3>
        <p class="muted">Simulates realistic alerts from HDFC, SBI, ICICI, Axis and Kotak, plus one OTP/promo message
          that must be rejected.</p>
        <div class="row">
          <label class="field" style="flex:0 0 120px"><span>Messages</span>
            <select id="demo-count">${[3, 6, 10, 20].map((n) => `<option ${n === 6 ? "selected" : ""}>${n}</option>`).join("")}</select></label>
          <button id="demo-run" class="btn" style="align-self:flex-end">📨 Simulate bank SMS</button>
        </div>
        <div id="demo-results">${lastDemo ? lastDemo.map(resultHtml).join("") : ""}</div>
      </div>

      <div class="card stack">
        <h3>🔎 Test the parser</h3>
        <label class="field"><span>Sender</span><input id="t-sender" value="${esc(SAMPLE.sender)}"></label>
        <label class="field"><span>Message</span><textarea id="t-body" rows="4">${esc(SAMPLE.body)}</textarea></label>
        <div><button id="t-parse" class="btn secondary">Preview</button></div>
        <div id="t-result"></div>
        <p class="muted">Preview only. Nothing is stored.</p>
      </div>
    </div>

    <h2>Captured from SMS (${recent.rows.length})</h2>
    ${recent.rows.length ? table(recent.rows, [
      { key: "id", label: "#", num: true },
      { key: "date", label: "Date" },
      { key: "bank", label: "Bank" },
      { key: "account", label: "A/c", format: (v) => (v ? `••${esc(v)}` : "") },
      { key: "description", label: "Merchant" },
      { key: "amount", label: "Amount", num: true, format: (v, r) => `${r.type === "income" ? "+" : ""}${esc(money(v))}` },
      { key: "category", label: "Category" },
    ], "medium") : `<p class="muted">Nothing yet. Run the demo or connect a phone.</p>`}

    <h2>📶 Connect your phone (same Wi-Fi)</h2>
    <div class="card stack">
      <ol class="tips">
        <li>Start the server so other devices can reach it:<br><code>uvicorn api.main:app --host 0.0.0.0 --port 8000</code>
          <br><span class="muted">Allow Python through Windows Firewall when asked.</span></li>
        <li>Network URL of this app (open it on your phone to check):<br>${appUrls || "<span class=muted>none found</span>"}</li>
        <li>In an SMS forwarder app (e.g. <i>SMS to URL Forwarder</i>, MacroDroid or Tasker) send each bank SMS as
          <b>POST</b> to:<br>${urls}</li>
        <li>Add header <code>X-SMS-Token</code> with the value of <code>SMS_TOKEN</code> from your <code>.env</code> file
          (never shared in this page).</li>
        <li>Body (JSON): <code>{"sender": "VM-HDFCBK", "body": "&lt;the SMS text&gt;"}</code>.
          Filter to bank senders only, and skip messages containing "OTP".</li>
      </ol>
      <p class="muted">Away from home Wi-Fi, the phone needs a public address instead: a tunnel (Cloudflare Tunnel / ngrok)
        or a hosted server. No code changes needed.</p>
    </div>

    <h2>🛡️ Ledger security</h2>
    <div id="security">${securityHtml(sec)}</div>`;

  // ---- demo
  node.querySelector("#demo-run").addEventListener("click", async (e) => {
    e.target.disabled = true;
    const out = node.querySelector("#demo-results");
    out.innerHTML = `<p class="muted">Encrypting and signing…</p>`;
    try {
      const res = await api.post("/api/sms/demo", undefined, { count: node.querySelector("#demo-count").value });
      lastDemo = res.results;
      toast(`${res.stored} SMS transactions stored, encrypted and signed.`);
      await ctx.refresh();   // redraw: recent list, security report and month list all changed
    } catch (err) {
      out.innerHTML = alertBox("error", esc(errorText(err)));
      e.target.disabled = false;
    }
  });

  // ---- parser preview
  node.querySelector("#t-parse").addEventListener("click", async () => {
    const out = node.querySelector("#t-result");
    try {
      const r = await api.post("/api/sms/parse", {
        sender: node.querySelector("#t-sender").value.trim() || "UNKNOWN",
        body: node.querySelector("#t-body").value,
      });
      if (!r.ok) {
        out.innerHTML = alertBox("warning", esc(r.reason));
        return;
      }
      const t = r.transaction;
      out.innerHTML = alertBox("success", `<b>${esc(t.description)}</b> · ${esc(money(t.amount))} · ${esc(t.type)} ·
        ${esc(t.date)}<br>Category <b>${esc(t.category)}</b> (k-NN ${(t.confidence * 100).toFixed(0)}%) ·
        bank ${esc(t.bank)}${t.account ? ` · a/c ••${esc(t.account)}` : ""}${t.reference ? ` · ref ${esc(t.reference)}` : ""}
        ${t.duplicate ? "<br>⚠️ This exact SMS is already stored." : ""}
        ${t.merchant_found ? "" : "<br>⚠️ Merchant not recognised in this format."}`);
    } catch (err) {
      out.innerHTML = alertBox("error", esc(errorText(err)));
    }
  });

  // ---- verify
  node.querySelector("#security").addEventListener("click", async (e) => {
    if (e.target.id !== "verify") return;
    e.target.disabled = true;
    try {
      const s = await api.get("/api/security");
      node.querySelector("#security").innerHTML = securityHtml(s);
      toast(s.integrity.ok ? "Ledger verified." : "Integrity problems found.", s.integrity.ok ? "success" : "error");
    } catch (err) {
      toast(errorText(err), "error");
      e.target.disabled = false;
    }
  });
}

