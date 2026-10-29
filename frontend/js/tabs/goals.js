// 🏆 Goals & Rewards: spending plans for any period, over-target alerts, and the points game.

import { api } from "../api.js";
import { alertBox, bar, errorText, esc, money, state, toast } from "../ui.js";
import { notificationStatus, requestNotifications } from "../notify.js";

let editing = null;   // plan being edited: null = none, {} = new plan, {...plan} = existing

function iso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function presetRange(kind) {
  const t = new Date();
  if (kind === "this-month") return [new Date(t.getFullYear(), t.getMonth(), 1), new Date(t.getFullYear(), t.getMonth() + 1, 0)];
  if (kind === "next-month") return [new Date(t.getFullYear(), t.getMonth() + 1, 1), new Date(t.getFullYear(), t.getMonth() + 2, 0)];
  if (kind === "this-week") {
    const monday = new Date(t);
    monday.setDate(t.getDate() - ((t.getDay() + 6) % 7));
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    return [monday, sunday];
  }
  return null;
}

const fmtDate = (d) => new Date(d + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

// ---------------------------------------------------------------- pieces
function levelHtml(r) {
  const l = r.level;
  const toNext = l.next_min ? (Math.max(r.total, 0) - l.min) / (l.next_min - l.min) : 1;
  return `<div class="card game-hero">
    <div class="game-level">${esc(l.name)}</div>
    <div class="game-points"><span>${r.total.toLocaleString()}</span> points</div>
    ${bar(toNext, "ok")}
    <div class="muted">${l.next_name ? `${(l.next_min - Math.max(r.total, 0)).toLocaleString()} points to ${esc(l.next_name)}`
      : "Top level reached!"}</div>
    <div class="game-stats">
      <div><b>🔥 ${r.streak}</b><span>day clean streak</span></div>
      <div><b>🏆 ${r.longest_streak}</b><span>best streak</span></div>
      <div><b class="${r.this_month >= 0 ? "pos" : "neg"}">${r.this_month >= 0 ? "+" : ""}${r.this_month}</b><span>this month</span></div>
      <div><b class="pos">+${r.earned.toLocaleString()}</b><span>earned</span></div>
      <div><b class="neg">−${r.lost.toLocaleString()}</b><span>lost</span></div>
    </div>
  </div>`;
}

function alertsHtml(alerts) {
  const notif = notificationStatus();
  const button = notif === "default"
    ? `<button id="enable-notif" class="btn small">🔔 Turn on notifications</button>`
    : notif === "granted" ? `<span class="pill">🔔 Notifications on</span>`
      : notif === "denied" ? `<span class="pill muted-pill">🔕 Blocked in browser settings</span>`
        : `<span class="pill muted-pill">Notifications not supported here</span>`;
  const icon = { exceeded: "🔴", warning: "🟠", info: "🔵" };
  return `<div class="card">
    <div class="row"><h3 style="margin:0">Reminders</h3><span class="spacer"></span>${button}</div>
    <p class="muted">You're notified at 80% and 100% of a plan (and of each planned category), when a monthly budget
      is exceeded, or when your pace means you'll overspend.</p>
    ${alerts.length ? alerts.map((a) => `<div class="issue"><div>${icon[a.level]} <b>${esc(a.title)}</b></div>
      <div class="detail">${esc(a.detail)}</div></div>`).join("") : alertBox("success", "All plans are on track. 🎉")}
  </div>`;
}

function planCard(p) {
  const pct = p.pct;
  const cls = pct > 1 ? "over" : pct > 0.8 ? "warn" : "ok";
  const statusPill = { active: `<span class="pill">● active · ${p.days_left} day(s) left</span>`,
    upcoming: `<span class="pill muted-pill">upcoming</span>`, finished: `<span class="pill">finished</span>` }[p.status];
  const cats = p.categories.map((c) => {
    if (c.unplanned) return `<div class="plan-cat unplanned"><span>${esc(c.category)} <i>(unplanned)</i></span>
      <span>${esc(money(c.spent))}</span></div>`;
    const ccls = c.pct > 1 ? "over" : c.pct > 0.8 ? "warn" : "ok";
    return `<div class="plan-cat"><span>${esc(c.category)}</span><span>${esc(money(c.spent))} / ${esc(money(c.planned))}</span>
      ${bar(c.pct, ccls)}</div>`;
  }).join("");
  const pace = p.status === "active" && p.projected > p.target_total
    ? `<p class="neg-text">At this pace: ~${esc(money(p.projected))} by ${esc(fmtDate(p.end_date))}.</p>` : "";
  return `<div class="card plan-card">
    <div class="row"><h3 style="margin:0">${esc(p.name)}</h3>${statusPill}<span class="spacer"></span>
      <button class="btn small secondary" data-edit="${p.id}">Edit</button>
      <button class="btn small danger-outline" data-delete="${p.id}">Delete</button></div>
    <p class="muted">${esc(fmtDate(p.start_date))} – ${esc(fmtDate(p.end_date))} · ${p.transactions} expenses</p>
    <div class="plan-total"><b>${esc(money(p.spent))}</b> of ${esc(money(p.target_total))}
      <span class="muted">(${(pct * 100).toFixed(0)}%)</span></div>
    ${bar(pct, cls)}
    ${pace}
    <details class="mt"><summary class="muted">Categories (${p.categories.length})</summary>${cats || "<p class=muted>No spending yet.</p>"}</details>
  </div>`;
}

function itemRow(item = {}) {
  const cats = Object.keys(state.meta.categories.expense).filter((c) => c !== state.meta.savings_category);
  return `<tr>
    <td><select class="i-cat">${cats.map((c) => `<option ${c === item.category ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></td>
    <td><input class="i-amount" type="number" min="0" step="100" value="${item.amount ?? ""}" placeholder="0"></td>
    <td><input class="i-note" maxlength="120" value="${esc(item.note ?? "")}" placeholder="optional"></td>
    <td><button type="button" class="btn small danger-outline i-del" aria-label="Remove">✕</button></td>
  </tr>`;
}

function editorHtml(p) {
  const [s, e] = p.id ? [p.start_date, p.end_date] : presetRange("next-month").map(iso);
  return `<form id="plan-form" class="card stack">
    <h3 style="margin:0">${p.id ? "Edit plan" : "New spending plan"}</h3>
    <p class="muted">Decide what you expect to spend in a period: a total ceiling, plus planned amounts per category.</p>
    <div class="grid cols-3">
      <label class="field"><span>Name</span><input name="name" required maxlength="80" value="${esc(p.name ?? "")}"
        placeholder="e.g. November, Goa trip"></label>
      <label class="field"><span>From</span><input name="start_date" type="date" required value="${s}"></label>
      <label class="field"><span>To</span><input name="end_date" type="date" required value="${e}"></label>
    </div>
    <div class="row">
      <span class="muted">Quick period:</span>
      <button type="button" class="btn small secondary" data-preset="this-week">This week</button>
      <button type="button" class="btn small secondary" data-preset="this-month">This month</button>
      <button type="button" class="btn small secondary" data-preset="next-month">Next month</button>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>Category</th><th>Planned amount</th><th>Note</th><th></th></tr></thead>
      <tbody id="items">${(p.items || []).map(itemRow).join("")}</tbody>
    </table></div>
    <div class="row">
      <button type="button" id="add-item" class="btn small secondary">+ Add expense</button>
      <button type="button" id="suggest" class="btn small secondary">✨ Fill from my recent spending</button>
      <span class="spacer"></span>
      <span class="muted">Planned: <b id="planned-sum">${esc(money(0))}</b></span>
    </div>
    <label class="field" style="max-width:280px"><span>Spending target for the whole period (${esc(state.meta.settings.currency)})</span>
      <input name="target_total" type="number" min="0" step="100" required value="${p.target_total ?? ""}"></label>
    <div class="row"><button type="submit" class="btn">💾 Save plan</button>
      <button type="button" id="cancel-plan" class="btn secondary">Cancel</button></div>
  </form>`;
}

function rewardsHtml(r) {
  const badges = r.badges.map((b) => `<div class="badge ${b.earned ? "earned" : ""}" title="${esc(b.desc)}">
    <div class="badge-name">${esc(b.name)}</div><div class="muted">${esc(b.desc)}</div>
    <div class="badge-state">${b.earned ? "Unlocked" : "🔒 Locked"}</div></div>`).join("");
  const events = r.events.slice(0, 25).map((e) => `<div class="event">
    <span class="event-pts ${e.points >= 0 ? "pos" : "neg"}">${e.points >= 0 ? "+" : ""}${e.points}</span>
    <span>${esc(e.text)}${e.member ? ` <span class="muted">· ${esc(e.member)}</span>` : ""}</span>
    <span class="muted event-date">${esc(fmtDate(e.date))}</span></div>`).join("");
  const medals = ["🥇", "🥈", "🥉"];
  const board = r.leaderboard.map((m, i) => `<tr>
    <td>${medals[i] ?? i + 1}</td><td><b>${esc(m.member)}</b></td>
    <td class="num">${(m.share_unnecessary * 100).toFixed(0)}%</td>
    <td class="num">${m.unnecessary} / ${m.expenses}</td>
    <td class="num">${esc(money(m.unnecessary_amount))}</td>
    <td class="num neg">${m.penalty_points}</td></tr>`).join("");
  return `
    <h2>🏅 Badges</h2>
    <div class="badges">${badges}</div>
    <div class="grid cols-2 mt">
      <div class="card"><h3>Recent points</h3><div class="events">${events || "<p class=muted>No points yet.</p>"}</div></div>
      <div class="stack">
        <div class="card"><h3>👪 Family leaderboard</h3>
          <p class="muted">Ranked by the share of each person's expenses that were unnecessary (lower is better).</p>
          <div class="table-wrap"><table><thead><tr><th></th><th>Member</th><th class="num">Unnecessary</th>
            <th class="num">Count</th><th class="num">Amount</th><th class="num">Points</th></tr></thead>
            <tbody>${board}</tbody></table></div></div>
        <div class="card"><h3>How points work</h3><ul class="tips">${r.rules.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
          <p class="muted">"Unnecessary" comes from the ID3 decision tree, or your own label in 📋 Transactions,
            which always wins.</p></div>
      </div>
    </div>`;
}

// ---------------------------------------------------------------- render
export async function render(node, ctx) {
  const [plans, alerts, rewards] = await Promise.all([api.get("/api/plans"), api.get("/api/alerts"),
    api.get("/api/rewards")]);

  node.innerHTML = `
    <div class="grid cols-2">${levelHtml(rewards)}${alertsHtml(alerts.alerts)}</div>
    <div class="row mt"><h2 style="margin:0">📋 Spending plans</h2><span class="spacer"></span>
      ${editing ? "" : `<button id="new-plan" class="btn">+ New plan</button>`}</div>
    <div id="editor" class="mt">${editing ? editorHtml(editing) : ""}</div>
    <div class="grid cols-2 mt">${plans.length ? plans.map(planCard).join("")
      : `<div class="card"><p class="muted">No plans yet. Create one to decide what you'll spend in a month, a week or on a
          trip. You'll get reminders when you get close, and points for keeping it.</p></div>`}</div>
    ${rewardsHtml(rewards)}`;

  node.querySelector("#enable-notif")?.addEventListener("click", async () => {
    await requestNotifications();
    ctx.refresh();
  });
  node.querySelector("#new-plan")?.addEventListener("click", () => { editing = {}; ctx.refresh(); });

  for (const btn of node.querySelectorAll("[data-edit]")) {
    btn.addEventListener("click", () => { editing = plans.find((p) => p.id === Number(btn.dataset.edit)); ctx.refresh(); });
  }
  for (const btn of node.querySelectorAll("[data-delete]")) {
    btn.addEventListener("click", async () => {
      const p = plans.find((x) => x.id === Number(btn.dataset.delete));
      if (!confirm(`Delete the plan “${p.name}”?`)) return;
      try {
        await api.del(`/api/plans/${p.id}`);
        toast("Plan deleted.");
        await ctx.refresh();
      } catch (err) {
        toast(errorText(err), "error");
      }
    });
  }
  if (editing) bindEditor(node, ctx);
}

function bindEditor(node, ctx) {
  const form = node.querySelector("#plan-form");
  const items = form.querySelector("#items");
  const sum = () => {
    const total = [...items.querySelectorAll(".i-amount")].reduce((a, i) => a + (Number(i.value) || 0), 0);
    form.querySelector("#planned-sum").textContent = money(total);
    return total;
  };
  sum();
  items.addEventListener("input", sum);
  items.addEventListener("click", (e) => {
    if (e.target.classList.contains("i-del")) { e.target.closest("tr").remove(); sum(); }
  });
  form.querySelector("#add-item").addEventListener("click", () => {
    items.insertAdjacentHTML("beforeend", itemRow());
    items.lastElementChild.querySelector(".i-amount").focus();
  });
  for (const b of form.querySelectorAll("[data-preset]")) {
    b.addEventListener("click", () => {
      const [s, e] = presetRange(b.dataset.preset).map(iso);
      form.start_date.value = s;
      form.end_date.value = e;
    });
  }
  form.querySelector("#suggest").addEventListener("click", async () => {
    try {
      const sug = await api.get("/api/plans/suggest", { start_date: form.start_date.value, end_date: form.end_date.value });
      items.innerHTML = sug.items.map(itemRow).join("");
      form.target_total.value = Math.round(sug.target_total);
      sum();
      toast("Filled from your recent spending (wants trimmed 15%). Adjust as you like.");
    } catch (err) {
      toast(errorText(err), "error");
    }
  });
  form.querySelector("#cancel-plan").addEventListener("click", () => { editing = null; ctx.refresh(); });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const rows = [...items.querySelectorAll("tr")].map((tr) => ({
      category: tr.querySelector(".i-cat").value,
      amount: Number(tr.querySelector(".i-amount").value) || 0,
      note: tr.querySelector(".i-note").value.trim(),
    })).filter((r) => r.amount > 0);
    const body = { name: form.name.value.trim(), start_date: form.start_date.value, end_date: form.end_date.value,
      target_total: Number(form.target_total.value) || sum(), items: rows };
    try {
      if (editing.id) await api.put(`/api/plans/${editing.id}`, body);
      else await api.post("/api/plans", body);
      toast(`Plan “${body.name}” saved.`);
      editing = null;
      await ctx.refresh();
    } catch (err) {
      toast(errorText(err), "error");
    }
  });
}
