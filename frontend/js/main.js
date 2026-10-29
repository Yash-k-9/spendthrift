// App shell: sidebar (month, settings, data), tab routing and re-rendering.

import { api } from "./api.js";
import { empty, errorText, esc, monthName, state, toast } from "./ui.js";
import * as dashboard from "./tabs/dashboard.js";
import * as insights from "./tabs/insights.js";
import * as predictions from "./tabs/predictions.js";
import * as patterns from "./tabs/patterns.js";
import * as budgets from "./tabs/budgets.js";
import * as add from "./tabs/add.js";
import * as transactions from "./tabs/transactions.js";
import * as models from "./tabs/models.js";
import * as sms from "./tabs/sms.js";

const TABS = { dashboard, insights, predictions, patterns, budgets, add, transactions, sms, models };
const NEEDS_DATA = new Set(["dashboard", "insights", "predictions", "patterns", "budgets"]);

const view = document.getElementById("view");
const monthSelect = document.getElementById("month-select");
const settingsForm = document.getElementById("settings-form");
let renderToken = 0;

function currentTab() {
  const tab = location.hash.slice(1);
  return TABS[tab] ? tab : "dashboard";
}

async function loadMeta() {
  state.meta = await api.get("/api/meta");
  const months = state.meta.months;
  if (!months.includes(state.month)) state.month = months[0] ?? null;

  monthSelect.innerHTML = months.length
    ? months.map((m) => `<option value="${esc(m)}">${esc(monthName(m))}</option>`).join("")
    : `<option value="">No data yet</option>`;
  monthSelect.disabled = !months.length;
  monthSelect.value = state.month ?? "";

  const s = state.meta.settings;
  settingsForm.currency.value = s.currency;
  settingsForm.savings_goal_pct.value = s.savings_goal_pct;
  settingsForm.family_size.value = s.family_size;
  document.getElementById("goal-value").textContent = `${s.savings_goal_pct}%`;
}

async function render() {
  const tab = currentTab();
  const token = ++renderToken;
  for (const btn of document.querySelectorAll("#tabs button")) {
    btn.setAttribute("aria-selected", String(btn.dataset.tab === tab));
  }
  if (NEEDS_DATA.has(tab) && !state.month) {
    view.innerHTML = empty(`No transactions yet. Add some in <a href="#add">➕ Add / Import</a>,
      or load the demo family from <b>🗂️ Data</b> in the sidebar.`);
    return;
  }
  view.innerHTML = `<div class="loading">Loading…</div>`;
  try {
    // Each tab renders into a detached node, so a slow response can't overwrite a newer tab.
    const node = document.createElement("div");
    await TABS[tab].render(node, { refresh, isCurrent: () => token === renderToken });
    if (token !== renderToken) return;
    view.replaceChildren(node);
    TABS[tab].mounted?.(node);
  } catch (err) {
    if (token === renderToken) view.innerHTML = `<div class="alert error">${esc(errorText(err))}</div>`;
  }
}

/** Reload months/settings from the server and redraw the current tab (unless keepView). */
async function refresh({ keepView = false } = {}) {
  await loadMeta();
  if (!keepView) await render();
}

// ---------------------------------------------------------------- sidebar events
monthSelect.addEventListener("change", () => {
  state.month = monthSelect.value;
  render();
});

settingsForm.savings_goal_pct.addEventListener("input", (e) => {
  document.getElementById("goal-value").textContent = `${e.target.value}%`;
});

settingsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api.put("/api/settings", {
      currency: settingsForm.currency.value.trim(),
      savings_goal_pct: Number(settingsForm.savings_goal_pct.value),
      family_size: Number(settingsForm.family_size.value),
    });
    toast("Settings saved.");
    await refresh();
  } catch (err) {
    toast(errorText(err), "error");
  }
});

document.getElementById("load-demo").addEventListener("click", async (e) => {
  if (state.meta?.transaction_count && !confirm("This replaces all current transactions with the demo family. Continue?")) return;
  e.target.disabled = true;
  try {
    const { added } = await api.post("/api/demo");
    state.month = null;
    toast(`Loaded ${added} demo transactions.`);
    await refresh();
  } catch (err) {
    toast(errorText(err), "error");
  } finally {
    e.target.disabled = false;
  }
});

document.getElementById("clear-all").addEventListener("click", async () => {
  if (!confirm("This permanently deletes every transaction. Continue?")) return;
  try {
    await api.del("/api/transactions");
    toast("All transactions deleted.");
    await refresh();
  } catch (err) {
    toast(errorText(err), "error");
  }
});

for (const btn of document.querySelectorAll("#tabs button")) {
  btn.addEventListener("click", () => { location.hash = btn.dataset.tab; });
}
window.addEventListener("hashchange", render);

refresh().catch((err) => {
  view.innerHTML = `<div class="alert error">Couldn't reach the backend: ${esc(errorText(err))}</div>`;
});
