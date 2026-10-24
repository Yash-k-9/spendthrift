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
})();
