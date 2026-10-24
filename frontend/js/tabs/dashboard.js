// 📊 Dashboard: income, spending, savings rate, category donut, 50/30/20 check, monthly trend.

import { api } from "../api.js";
import { esc, metric, money, moneyDelta, plot, signed, state } from "../ui.js";

let data = null;

export async function render(node) {
  data = await api.get("/api/dashboard", { month: state.month });
  const s = data.summary;
  const p = data.previous;
  const rateDiff = s.savings_rate_pct - data.goal;

  node.innerHTML = `
    <div class="grid cols-4">
      ${metric("Income", money(s.income), ...moneyDelta(s.income, p?.income, true))}
      ${metric("Spending", money(s.spending), ...moneyDelta(s.spending, p?.spending, false))}
      ${metric("Net savings", money(s.net_savings), ...moneyDelta(s.net_savings, p?.net_savings, true))}
      ${metric("Savings rate", `${s.savings_rate_pct}%`, `${signed(rateDiff)} pts vs ${data.goal}% goal`,
               rateDiff >= 0 ? "up" : "down")}
    </div>
    ${s.invested ? `<p class="muted mt">Includes ${esc(money(s.invested))} moved into savings &amp; investments.</p>` : ""}

    <div class="grid cols-2 mt">
      <div class="card">
        <h3>Where the money went</h3>
        <div id="chart-donut" class="chart h360"></div>
      </div>
      <div class="card">
        <h3>50 / 30 / 20 check</h3>
        <div id="chart-split" class="chart h360"></div>
      </div>
    </div>

    <div class="card mt">
      <h3>Monthly trend</h3>
      <div id="chart-trend" class="chart h360"></div>
    </div>`;
}

export function mounted() {
  const b = data.breakdown;
  plot("chart-donut", [{
    type: "pie", hole: 0.5, labels: b.map((r) => r.category), values: b.map((r) => r.amount),
    textposition: "inside", textinfo: "percent+label", sort: false,
    hovertemplate: "%{label}<br>%{value:,.0f}<extra></extra>",
  }], { showlegend: false, margin: { t: 10, b: 10, l: 10, r: 10 } });

  const sp = data.split;
  const you = [sp.need_pct, sp.want_pct, sp.saving_pct];
  const labels = ["Needs", "Wants", "Savings"];
  plot("chart-split", [
    { type: "bar", name: "You", x: labels, y: you, text: you.map((v) => `${v}%`), textposition: "auto" },
    { type: "bar", name: "Target", x: labels, y: [50, 30, 20], opacity: 0.45 },
  ], { barmode: "group", yaxis: { title: { text: "% of income" } } });

  const t = data.trend;
  const months = t.map((r) => r.month);
  plot("chart-trend", [
    { type: "bar", name: "Income", x: months, y: t.map((r) => r.income) },
    { type: "bar", name: "Spending", x: months, y: t.map((r) => r.spending) },
    { type: "scatter", mode: "lines+markers", name: "Savings rate %", x: months, y: t.map((r) => r.savings_rate_pct),
      yaxis: "y2" },
  ], {
    barmode: "group",
    xaxis: { type: "category" },
    yaxis2: { overlaying: "y", side: "right", title: { text: "Savings rate %" }, showgrid: false },
  });
}
