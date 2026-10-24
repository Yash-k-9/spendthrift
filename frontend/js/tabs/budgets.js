// 🎯 Budgets: per-category limits, suggestions and progress bars.

import { api } from "../api.js";
import { bar, errorText, esc, money, state, toast } from "../ui.js";

export async function render(node, ctx) {
  const d = await api.get("/api/budgets", { month: state.month });

  const rows = d.rows.map((r) => `<tr>
    <td>${esc(r.category)}</td>
    <td>${esc(r.type)}</td>
    <td class="num">${esc(money(r.spent))}</td>
    <td class="num" title="Recent average; wants trimmed 15%">${esc(money(r.suggested))}</td>
    <td class="num"><input type="number" min="0" step="100" value="${r.budget}" data-category="${esc(r.category)}"
      aria-label="Budget for ${esc(r.category)}" title="0 = no budget"></td>
  </tr>`).join("");

  const progress = d.progress.map((p) => {
    const cls = p.pct > 1 ? "over" : p.pct > 0.85 ? "warn" : "ok";
    const icon = p.pct > 1 ? "🔴" : p.pct > 0.85 ? "🟠" : "🟢";
    return `<div class="progress-row">
      <div>${icon} ${esc(p.category)}: ${esc(money(p.spent))} of ${esc(money(p.limit))} (${(p.pct * 100).toFixed(0)}%)</div>
      ${bar(p.pct, cls)}
    </div>`;
  }).join("");

  node.innerHTML = `
    <h2>🎯 Monthly category budgets</h2>
    <div class="table-wrap"><table>
      <thead><tr><th>Category</th><th>Type</th><th class="num">Spent this month</th><th class="num">Suggested</th>
        <th class="num">Budget</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <div class="grid cols-2 mt">
      <button id="save-budgets" class="btn">💾 Save budgets</button>
      <button id="use-suggested" class="btn secondary">✨ Use suggested budgets</button>
    </div>
    ${progress ? `<h2>Progress</h2><div class="card">${progress}</div>` : ""}`;

  node.querySelector("#save-budgets").addEventListener("click", async () => {
    const budgets = {};
    for (const input of node.querySelectorAll("input[data-category]")) {
      budgets[input.dataset.category] = Math.max(0, Number(input.value) || 0);
    }
    try {
      await api.put("/api/budgets", { budgets });
      toast("Budgets saved.");
      await ctx.refresh();
    } catch (err) {
      toast(errorText(err), "error");
    }
  });

  node.querySelector("#use-suggested").addEventListener("click", async () => {
    try {
      await api.post("/api/budgets/suggested", undefined, { month: state.month });
      toast("Suggested budgets applied.");
      await ctx.refresh();
    } catch (err) {
      toast(errorText(err), "error");
    }
  });
}
