// Intro animation: removes the splash overlay when its CSS animation ends, or on click / key press.
(() => {
  const splash = document.getElementById("splash");
  if (!splash) return;

  const remove = () => splash.remove();
  const skip = () => {
    splash.classList.add("splash-hide");
    setTimeout(remove, 320);
  };

  splash.addEventListener("animationend", (e) => {
    if (e.target === splash && e.animationName === "splash-out") remove();
  });
  splash.addEventListener("click", skip, { once: true });
  document.addEventListener("keydown", skip, { once: true });
  setTimeout(remove, 6000);   // safety net if animations are disabled

  startMoneyRain(splash);
})();

// Coins, notes and rupee signs drifting down behind the banknote while it plays.
// Stops by itself once the splash is removed from the page.
function startMoneyRain(splash) {
  const canvas = splash.querySelector(".splash-rain");
  if (!canvas || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const ctx = canvas.getContext("2d");

  const GLYPHS = ["🪙", "₹", "💸", "💵"];
  const COUNT = 35;
  const SPEED = 1.2;                       // px per frame at 60 fps ("2 of 5")
  const RUPEE_COLOR = "#1f9d60";           // pine green, readable on light and dark splash
  const FONT = '"Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", "Playfair Display", sans-serif';

  let w = 0, h = 0;
  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  resize();
  window.addEventListener("resize", resize);

  const rand = (a, b) => a + Math.random() * (b - a);
  const spawn = (d, top) => {
    d.glyph = GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
    d.size = rand(16, 36);
    d.x = rand(0, w);
    d.y = top ? rand(-40, h) : -40;        // first wave is already spread over the screen (the splash is short)
    d.v = rand(0.4, 1.4);
    d.alpha = rand(0.55, 1);
    d.rot = rand(-0.35, 0.35);
    d.spin = rand(-0.012, 0.012);
    d.sway = rand(0, Math.PI * 2);
    return d;
  };
  const drops = Array.from({ length: COUNT }, () => spawn({}, true));

  let last = performance.now();
  const frame = (now) => {
    if (!canvas.isConnected) { window.removeEventListener("resize", resize); return; }
    const k = Math.min((now - last) / 16.67, 3);   // frame-rate independent
    last = now;
    ctx.clearRect(0, 0, w, h);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const d of drops) {
      d.y += d.v * SPEED * k;
      d.sway += 0.02 * k;
      d.rot += d.spin * k;
      if (Math.abs(d.rot) > 0.6) d.spin = -d.spin;
      if (d.y > h + 40) spawn(d, false);

      ctx.save();
      ctx.globalAlpha = d.alpha;
      ctx.translate(d.x + Math.sin(d.sway) * 15, d.y);
      ctx.rotate(d.rot);
      ctx.font = `${d.glyph === "₹" ? "700 " : ""}${d.size.toFixed(0)}px ${FONT}`;
      ctx.fillStyle = RUPEE_COLOR;           // only affects ₹; emojis keep their own colours
      ctx.fillText(d.glyph, 0, 0);
      ctx.restore();
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}
