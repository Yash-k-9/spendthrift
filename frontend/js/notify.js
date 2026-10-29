// Over-target reminders: polls /api/alerts and shows each new alert once, as a toast and (if allowed)
// a desktop/phone notification. Works while the app is open in any tab of the browser.

import { api } from "./api.js";
import { toast } from "./ui.js";

const SEEN_KEY = "budget.seenAlerts";
const POLL_MS = 60_000;

export function notificationStatus() {
  return "Notification" in window ? Notification.permission : "unsupported";
}

export async function requestNotifications() {
  if (!("Notification" in window)) return "unsupported";
  const result = await Notification.requestPermission();
  if (result === "granted") new Notification("Family Budget", { body: "Reminders are on. You'll be told when spending passes a target." });
  return result;
}

function loadSeen() {
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveSeen(seen) {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-300)));
  } catch { /* private mode: alerts may repeat after reload, which is harmless */ }
}

let seen = loadSeen();
let timer = null;
let checking = false;

/** Fetch alerts and announce the ones not shown before. */
export async function checkAlerts() {
  if (checking) return;   // one check at a time, so an alert is never announced twice
  checking = true;
  let alerts;
  try {
    ({ alerts } = await api.get("/api/alerts"));
  } catch {
    return;   // offline or no data yet - try again next time
  } finally {
    checking = false;
  }
  const fresh = alerts.filter((a) => !seen.has(a.id));
  for (const a of fresh.slice(0, 3)) {
    toast(`${a.level === "exceeded" ? "🔴" : a.level === "warning" ? "🟠" : "🔵"} ${a.title}: ${a.detail}`,
      a.level === "exceeded" ? "error" : "success");
    if (notificationStatus() === "granted") {
      new Notification(a.title, { body: a.detail, tag: a.id });
    }
  }
  for (const a of fresh) seen.add(a.id);
  if (fresh.length) saveSeen(seen);
}

export function startAlertWatcher() {
  if (timer) return;   // the first check happens in main.js's refresh()
  timer = setInterval(checkAlerts, POLL_MS);
}
