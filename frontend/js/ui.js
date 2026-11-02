// Shared rendering helpers: formatting, HTML escaping, metrics, tables and Plotly charts.

export const state = {
  meta: null,      // /api/meta response: settings, months, categories
  month: null,     // month selected in the sidebar (YYYY-MM)
};

export const SEVERITY_ICON = { high: "🔴", medium: "🟠", low: "🟡" };

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);

export const cur = () => state.meta?.settings.currency ?? "₹";
export const goal = () => state.meta?.settings.savings_goal_pct ?? 20;

export function money(x) {
  const n = Number(x) || 0;
  return `${n < 0 ? "-" : ""}${cur()}${Math.abs(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}
export const pct = (x, digits = 0) => `${(Number(x) * 100).toFixed(digits)}%`;
export const signed = (x, digits = 1) => `${x >= 0 ? "+" : ""}${Number(x).toFixed(digits)}`;

export function monthName(m) {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}
export function shortDate(d) {
  return new Date(d + "T00:00:00").toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

/** A metric tile. delta: text; tone: "up" | "down" | "" (colour of the delta). */
export function metric(label, value, delta = "", tone = "") {
  return `<div class="card metric">
    <div class="label">${esc(label)}</div>
    <div class="value">${esc(value)}</div>
    ${delta ? `<div class="delta ${tone}">${esc(delta)}</div>` : ""}
  </div>`;
}

/** Delta between two money amounts, toned so that "good" is green. */
export function moneyDelta(now, before, higherIsGood = true) {
  if (before === null || before === undefined) return ["", ""];
  const d = now - before;
  const tone = d === 0 ? "" : (d > 0) === higherIsGood ? "up" : "down";
  return [`${d >= 0 ? "▲" : "▼"} ${money(d)} vs last month`, tone];
}

export const alertBox = (kind, html) => `<div class="alert ${kind}">${html}</div>`;
export const empty = (html) => `<div class="empty">${html}</div>`;

export function bar(fraction, cls = "") {
  const w = Math.max(0, Math.min(1, fraction)) * 100;
  return `<div class="bar ${cls}"><span style="width:${w.toFixed(1)}%"></span></div>`;
}

/**
 * Simple table. columns: [{key, label, num?, format?(value, row) -> html}]
 * Values without a format function are escaped.
 */
export function table(rows, columns, cls = "") {
  const head = columns.map((c) => `<th class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("");
  const body = rows.map((r) => `<tr>${columns.map((c) => {
    const v = c.format ? c.format(r[c.key], r) : esc(r[c.key]);
    return `<td class="${c.num ? "num" : ""}">${v}</td>`;
  }).join("")}</tr>`).join("");
  return `<div class="table-wrap ${cls}"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

// ---------------------------------------------------------------- toasts & confirm
export function toast(message, kind = "success") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  document.getElementById("toasts").append(el);
  setTimeout(() => el.remove(), kind === "error" ? 7000 : 4000);
}

export function errorText(err) {
  return err?.message || String(err);
}

// ---------------------------------------------------------------- charts (Plotly)
// Distinct, muted hues that sit well next to pine and gold: neighbouring slices and series stay easy
// to tell apart, and nothing is neon. Pine and gold come first so the main series match the brand.
const PALETTE = ["#2f7d5c", "#c99a3c", "#4f7cac", "#c4664e", "#7d6aa8", "#5aa39a", "#d48aa0", "#8c9a4f",
                 "#9b7653", "#6f7f8c"];

function chartTheme() {
  const css = getComputedStyle(document.documentElement);
  const text = css.getPropertyValue("--text").trim();
  const muted = css.getPropertyValue("--muted").trim();
  const grid = css.getPropertyValue("--border").trim();
  const surface = css.getPropertyValue("--surface").trim();
  const axis = { gridcolor: grid, zerolinecolor: grid, linecolor: grid, automargin: true,
                 tickfont: { color: muted, size: 11 }, title: { font: { color: muted, size: 11 } } };
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, system-ui, -apple-system, Segoe UI, sans-serif", color: text, size: 12 },
    colorway: PALETTE,
    margin: { t: 30, b: 40, l: 50, r: 20 },
    legend: { orientation: "h", y: 1.15, font: { color: muted, size: 11.5 } },
    xaxis: axis,
    yaxis: axis,
    hoverlabel: { bgcolor: surface, bordercolor: grid, font: { family: "Inter, system-ui, sans-serif", color: text } },
  };
}

function merge(base, extra) {
  const out = { ...base };
  for (const [k, v] of Object.entries(extra || {})) {
    out[k] = v && typeof v === "object" && !Array.isArray(v) && typeof base[k] === "object" ? merge(base[k], v) : v;
  }
  return out;
}

/** Draw a Plotly chart into the element with this id. */
export function plot(id, traces, layout = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!window.Plotly) {
    el.innerHTML = `<p class="muted">Charts need the Plotly library (loaded from cdn.jsdelivr.net).</p>`;
    return;
  }
  window.Plotly.newPlot(el, traces, merge(chartTheme(), layout), { responsive: true, displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d"] });
}
