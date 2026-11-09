// Gentle 3D tilt for elements marked [data-tilt] (the hero "short answer" card).
// Dash renders the page after load, so listen on the document instead of binding to the element.
(function () {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (window.matchMedia("(hover: none)").matches) return;   // skip on touch screens
  const MAX = 7;   // degrees
  let active = null;

  document.addEventListener("mousemove", function (e) {
    const el = e.target.closest && e.target.closest("[data-tilt]");
    if (active && active !== el) reset(active);
    if (!el) return;
    active = el;
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    el.style.setProperty("--rx", (-y * MAX).toFixed(2) + "deg");
    el.style.setProperty("--ry", (x * MAX).toFixed(2) + "deg");
    el.style.setProperty("--gx", ((x + 0.5) * 100).toFixed(1) + "%");
    el.style.setProperty("--gy", ((y + 0.5) * 100).toFixed(1) + "%");
    el.classList.add("is-tilting");
  });

  document.addEventListener("mouseleave", function () { if (active) reset(active); }, true);

  function reset(el) {
    el.style.setProperty("--rx", "0deg");
    el.style.setProperty("--ry", "0deg");
    el.classList.remove("is-tilting");
    active = null;
  }
})();
