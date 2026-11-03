// Shapes the sidebar as a circular segment and lines the section buttons up along its arc.
//
// The chord is the left edge of the screen (height H). The arc reaches W (--side-w) at the middle
// and E (--side-edge-w) at the top and bottom, so with d = W - E the circle has
//     radius r = (H²/4 + d²) / 2d,   centre at x = W - r (left of the screen), y = H/2.

const shell = document.querySelector(".sidebar-shell");
const sidebar = document.getElementById("sidebar");
const phone = window.matchMedia("(max-width: 820px)");

function px(name) {
  return parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
}

function layout() {
  if (!sidebar) return;
  const buttons = [...sidebar.querySelectorAll(".side-nav button")];
  if (phone.matches) {
    sidebar.style.removeProperty("--side-clip");
    document.documentElement.style.removeProperty("--side-clip");
    for (const b of buttons) b.style.removeProperty("--dx");
    return;
  }
  const H = shell.clientHeight;
  const W = px("--side-w");
  const E = px("--side-edge-w");
  const d = W - E;
  const r = (H * H / 4 + d * d) / (2 * d);
  const cx = W - r;
  sidebar.style.setProperty("--side-clip", `circle(${r.toFixed(1)}px at ${cx.toFixed(1)}px 50%)`);

  // Shift each button right by how far the arc bulges at its height, so the list follows the curve.
  const top = shell.getBoundingClientRect().top;
  for (const b of buttons) {
    const box = b.getBoundingClientRect();
    const dy = box.top - top + box.height / 2 - H / 2;   // transforms only move buttons sideways
    const arcX = cx + Math.sqrt(Math.max(r * r - dy * dy, 0));
    b.style.setProperty("--dx", `${Math.max(arcX - E, 0).toFixed(1)}px`);
  }
}

window.addEventListener("resize", layout);
phone.addEventListener("change", layout);
sidebar?.addEventListener("scroll", layout, { passive: true });
document.fonts?.ready.then(layout);
layout();

export { layout };
