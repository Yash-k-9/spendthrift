// 🔍 Insights: unnecessary expenses (ID3), unusual expenses (EM), alerts and recommendations.

import { api } from "../api.js";
import { alertBox, esc, metric, money, SEVERITY_ICON, shortDate, state, table } from "../ui.js";

export async function render(node) {
  const d = await api.get("/api/insights", { month: state.month });

  let unnecessary;
  if (!d.unnecessary) {
    unnecessary = alertBox("info", "No expenses this month.");
  } else {
    const u = d.unnecessary;
    unnecessary = `
      <div class="grid cols-2">
        ${metric("Flagged as unnecessary", money(u.total), `${u.count} of ${u.of} expenses`)}
        ${metric("Share of spending", `${u.share_pct.toFixed(1)}%`)}
      </div>
      <div class="mt">
        ${u.rows.length ? table(u.rows, [
          { key: "date", label: "Date", format: (v) => esc(shortDate(v)) },
          { key: "description", label: "Description" },
          { key: "category", label: "Category" },
          { key: "amount", label: "Amount", num: true, format: (v) => esc(money(v)) },
          { key: "reason", label: "Why (decision path)" },
        ], "medium") : alertBox("success", "Nothing flagged as unnecessary this month.")}
      </div>
      <p class="muted">Disagree? Label expenses yourself in <a href="#transactions">📋 Transactions</a>.
        The tree retrains on your labels.</p>`;
  }

  let unusual;
  if (d.anomalies === null) {
    unusual = alertBox("info", `Needs at least ${d.anomaly_min_transactions} expenses to learn what is normal.`);
  } else if (!d.anomalies.length) {
    unusual = alertBox("success", "Nothing unusual this month.");
  } else {
    unusual = d.anomalies.map((r) => alertBox("warning",
      `⚠️ <b>${esc(r.description)}</b>: ${esc(money(r.amount))} on ${esc(shortDate(r.date))}, ` +
      `${r.ratio.toFixed(1)}× your usual ${esc(r.category.toLowerCase())} expense.`)).join("");
  }

  const issues = d.issues.length
    ? d.issues.map((i) => `<div class="issue">
        <div>${SEVERITY_ICON[i.severity]} <b>${esc(i.title)}</b></div>
        <div class="detail">${esc(i.detail)}</div>
      </div>`).join("")
    : alertBox("success", "No problems found this month. 🎉");

  node.innerHTML = `
    <div class="grid cols-3-2">
      <div>
        <h2>🌳 Unnecessary expenses · Decision Tree (ID3)</h2>
        ${unnecessary}
        <h2>🚨 Unusual expenses · EM (Gaussian Mixture)</h2>
        ${unusual}
      </div>
      <div>
        <h2>Spending alerts (${d.issues.length})</h2>
        ${issues}
        <h2>Recommendations</h2>
        <ul class="tips">${d.tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
        <p class="muted">For an optimised plan, see the Genetic Algorithm in <a href="#predictions">🔮 Predictions</a>.</p>
      </div>
    </div>`;
}
