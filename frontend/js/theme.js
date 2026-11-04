// Light / dark theme switch. The choice is remembered on this device; with no choice the app follows
// the system setting. index.html applies the saved choice before the page is drawn (no flash).

const KEY = "budget.theme";   // "light" | "dark" | absent = follow the system
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

export function savedTheme() {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

export function currentTheme() {
  return savedTheme() ?? (systemDark.matches ? "dark" : "light");
}

/** theme: "light" | "dark" | null (follow the system). */
export function setTheme(theme) {
  try {
    if (theme) localStorage.setItem(KEY, theme);
    else localStorage.removeItem(KEY);
  } catch { /* private mode: the choice lasts until the page is closed */ }
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
  window.dispatchEvent(new CustomEvent("themechange", { detail: currentTheme() }));
}

/** Wire the switch and the "Follow system" button in Settings. */
export function initThemeSwitch() {
  const toggle = document.getElementById("theme-toggle");
  const follow = document.getElementById("theme-follow");
  if (!toggle) return;
  const sync = () => {
    const theme = currentTheme();
    toggle.setAttribute("aria-checked", String(theme === "dark"));
    toggle.querySelector(".theme-name").textContent = theme === "dark" ? "Dark" : "Light";
    follow.hidden = savedTheme() === null;
  };
  toggle.addEventListener("click", () => setTheme(currentTheme() === "dark" ? "light" : "dark"));
  follow.addEventListener("click", () => setTheme(null));
  window.addEventListener("themechange", sync);
  toggle.closest("details")?.addEventListener("toggle", sync);   // in case a system change event was missed
  systemDark.addEventListener("change", () => {
    if (savedTheme() === null) window.dispatchEvent(new CustomEvent("themechange", { detail: currentTheme() }));
  });
  sync();
}
