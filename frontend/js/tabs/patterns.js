// 🧩 Patterns: k-Means clusters with a scatter plot and adjustable k.

import { api } from "../api.js";
import { alertBox, errorText, esc, money, plot, state, toast } from "../ui.js";

let data = null;
let k = 4;

function bodyHtml(d) {
  if (!d.available) return alertBox("info", "Needs more expenses to find patterns.");
  const cards = d.summary.map((r) => `
    <div class="card">
      <b>${esc(r.name)}</b>
      <div class="metric"><div class="label">This month</div><div class="value">${esc(money(r.this_month))}</div></div>
      <p class="muted">${r.transactions} expenses · typically ${esc(money(r.typical_amount))} ·
        ${r.per_month.toFixed(1)}×/month · seen in ${r.recurrence_pct.toFixed(0)}% of months</p>
      <p class="muted">e.g. ${esc(r.examples)}</p>
    </div>`).join("");
  const tips = d.summary.filter((r) => r.name.startsWith("Frequent")).map((r) => alertBox("info",
    `💡 <b>${esc(r.name)}</b> add up to ${esc(money(r.this_month))} this month. Small repeated purchases are the
     easiest place to save, so try a weekly limit.`)).join("");
  return `<div class="grid cols-4">${cards}</div>
    <div class="card mt"><div id="chart-patterns" class="chart h420"></div></div>
    ${tips}`;
}

export async function render(node) {
  data = await api.get("/api/patterns", { month: state.month, k });
  node.innerHTML = `
    <h2>🧩 Spending patterns · k-Means clustering</h2>
    <label class="field" style="max-width:420px">
      <span>Number of clusters (k): <b id="k-value">${k}</b></span>
      <input id="k" type="range" min="2" max="7" value="${k}">
    </label>
    <p class="muted">See the elbow chart in <a href="#models">🧠 Models</a> for a good k.</p>
    <div id="patterns-body">${bodyHtml(data)}</div>`;

  const slider = node.querySelector("#k");
  slider.addEventListener("input", () => { node.querySelector("#k-value").textContent = slider.value; });
  slider.addEventListener("change", async () => {
    k = Number(slider.value);
    const body = node.querySelector("#patterns-body");
    body.style.opacity = 0.5;
    try {
      data = await api.get("/api/patterns", { month: state.month, k });
      body.innerHTML = bodyHtml(data);
      mounted();
    } catch (err) {
      toast(errorText(err), "error");
    } finally {
      body.style.opacity = 1;
    }
  });
}

export function mounted() {
  if (!data?.available) return;
  const groups = {};
  for (const p of data.points) (groups[p.pattern] ??= []).push(p);
  plot("chart-patterns", Object.entries(groups).map(([name, pts]) => ({
    type: "scatter", mode: "markers", name,
    x: pts.map((p) => p.per_month), y: pts.map((p) => p.amount), text: pts.map((p) => p.description),
    marker: { size: 9, opacity: 0.7 },
    hovertemplate: "<b>%{text}</b><br>%{x:.1f}×/month · %{y:,.0f}<extra>" + name.replace(/[<>&]/g, "") + "</extra>",
  })), {
    xaxis: { title: { text: "Times per month" } },
    yaxis: { type: "log", title: { text: `Amount (${state.meta.settings.currency}, log scale)` } },
  });
}
