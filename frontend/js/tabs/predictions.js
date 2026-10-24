// 🔮 Predictions: next month's forecast (LWR), chance of meeting the goal, and the GA savings plan.

import { api } from "../api.js";
import { alertBox, bar, errorText, esc, metric, money, monthName, plot, signed, state, table, toast } from "../ui.js";

let data = null;

function planHtml(p) {
  if (p.needed <= 0) return alertBox("success", `The forecast already meets a ${p.target}% savings rate. No cuts needed.`);
  return `
    <div class="grid cols-3">
      ${metric("Extra saving needed", money(p.needed))}
      ${metric("Plan saves", money(p.saved), `${money(p.saved * 12)} / year`)}
      ${metric("Savings rate with plan", `${p.new_savings_rate.toFixed(1)}%`)}
    </div>
    ${p.reached ? "" : alertBox("warning", `Even the maximum sensible cuts (${esc(money(p.max_possible))}) can't fully
      close the gap. Consider a lower target or a look at fixed costs.`)}
    <div class="mt">${table(p.rows, [
      { key: "category", label: "Category" },
      { key: "type", label: "Type" },
      { key: "current", label: "Expected", num: true, format: (v) => esc(money(v)) },
      { key: "cut_pct", label: "Cut", format: (v) => `<div class="row">${bar(v / 50)}<span>${v.toFixed(0)}%</span></div>` },
      { key: "saving", label: "Saving", num: true, format: (v) => esc(money(v)) },
      { key: "new_budget", label: "New budget", num: true, format: (v) => esc(money(v)) },
    ])}</div>
    <p class="muted">The GA trims categories that have grown above their usual level first, cuts wants before needs,
      and never touches rent, EMIs, insurance, school fees or healthcare.</p>
    <button id="apply-plan" class="btn">Use this plan as my budgets</button>`;
}

export async function render(node) {
  data = await api.get("/api/predictions", { month: state.month });
  if (!data.available) {
    node.innerHTML = alertBox("info", "Predictions need at least 2 months of data.");
    return;
  }
  const d = data;
  const nm = monthName(d.next_month);
  const [lo, hi] = d.spending_range;
  const rateDiff = d.savings_rate_pred - d.goal;

  let actual = "";
  if (d.actual) {
    const err = d.actual.spending ? (d.spending_pred - d.actual.spending) / d.actual.spending * 100 : 0;
    actual = alertBox("success", `✅ <b>${esc(nm)} has already happened, so the prediction can be checked:</b>
      actual regular spending was ${esc(money(d.actual.spending))} vs predicted ${esc(money(d.spending_pred))}
      (${signed(err)}% error).`);
  }

  const hasActual = d.categories.some((c) => c.actual !== undefined && c.actual !== null);
  const catCols = [
    { key: "category", label: "Category" },
    { key: "avg_3_months", label: "3-mo avg", num: true, format: (v) => esc(money(v)) },
    { key: "predicted", label: "Predicted", num: true, format: (v) => esc(money(v)) },
    { key: "change_pct", label: "Change", num: true, format: (v) => `${signed(v, 0)}%` },
  ];
  if (hasActual) catCols.push({ key: "actual", label: "Actual", num: true, format: (v) => esc(money(v)) });

  node.innerHTML = `
    <h2>🔮 Forecast for ${esc(nm)} · Locally Weighted Regression</h2>
    <p class="muted">Predicts regular spending from months up to ${esc(monthName(d.month))}.
      ${d.excluded_count} one-off purchases found by k-Means are left out, since a one-time laptop is not a trend.
      Bandwidth τ = ${d.tau} (picked automatically by back-testing).</p>
    <div class="grid cols-4">
      ${metric("Predicted income", money(d.income_pred))}
      ${metric("Predicted spending", money(d.spending_pred), `80% range ${money(lo)} – ${money(hi)}`)}
      ${metric("Predicted savings rate", `${d.savings_rate_pred.toFixed(1)}%`, `${signed(rateDiff)} pts vs goal`,
               rateDiff >= 0 ? "up" : "down")}
      ${metric(`Chance of meeting ${d.goal}% goal`, `${(d.prob_goal * 100).toFixed(0)}%`)}
    </div>
    ${actual}
    <div class="grid cols-3-2 mt">
      <div class="card"><div id="chart-forecast" class="chart h360"></div></div>
      <div>${table(d.categories, catCols, "medium")}</div>
    </div>
    ${d.rising.map((r) => `<p>📈 <b>${esc(r.category)}</b> is heading for ${esc(money(r.predicted))}
      (${signed(r.change_pct, 0)}% vs the 3-month average).</p>`).join("")}

    <h2>🧬 Best savings plan · Genetic Algorithm</h2>
    <label class="field" style="max-width:420px">
      <span>Target savings rate for the plan: <b id="target-value">${d.plan.target}%</b></span>
      <input id="target" type="range" min="5" max="60" value="${d.plan.target}">
    </label>
    <p class="muted">Defaults to your goal, or 5 points above the forecast if you're already on track.</p>
    <div id="plan">${planHtml(d.plan)}</div>`;

  bindPlan(node);
  const slider = node.querySelector("#target");
  slider.addEventListener("input", () => { node.querySelector("#target-value").textContent = `${slider.value}%`; });
  slider.addEventListener("change", async () => {
    const planEl = node.querySelector("#plan");
    planEl.style.opacity = 0.5;
    try {
      data = await api.get("/api/predictions", { month: state.month, target: slider.value });
      planEl.innerHTML = planHtml(data.plan);
      bindPlan(node);
    } catch (err) {
      toast(errorText(err), "error");
    } finally {
      planEl.style.opacity = 1;
    }
  });
}

function bindPlan(node) {
  node.querySelector("#apply-plan")?.addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      await api.post("/api/budgets/apply-plan", { month: state.month, target: data.plan.target });
      toast("Budgets updated. See 🎯 Budgets.");
    } catch (err) {
      toast(errorText(err), "error");
    } finally {
      e.target.disabled = false;
    }
  });
}

export function mounted() {
  if (!data?.available) return;
  const h = data.history;
  const last = h.months.length - 1;
  const [lo, hi] = data.spending_range;
  plot("chart-forecast", [
    { type: "scatter", mode: "lines+markers", name: "Spending (actual)", x: h.months, y: h.spending },
    { type: "scatter", mode: "lines+markers", name: "Income (actual)", x: h.months, y: h.income },
    { type: "scatter", mode: "lines+markers", name: "Predicted spending", x: [h.months[last], data.next_month],
      y: [h.spending[last], data.spending_pred], line: { dash: "dash" } },
    { type: "scatter", mode: "lines", name: "80% range", x: [data.next_month, data.next_month], y: [lo, hi],
      line: { width: 8 }, opacity: 0.3 },
  ], { xaxis: { type: "category" }, yaxis: { title: { text: state.meta.settings.currency } } });
}
