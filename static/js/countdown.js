// Live countdown to the event date in #countdown[data-target] (ISO 8601).
(function () {
  const root = document.getElementById('countdown');
  if (!root) return;
  const target = new Date(root.dataset.target).getTime();
  const units = {};
  root.querySelectorAll('[data-unit]').forEach((el) => { units[el.dataset.unit] = el; });

  function tick() {
    const diff = target - Date.now();
    if (diff <= 0) {
      root.hidden = true;
      document.getElementById('countdown-done').hidden = false;
      clearInterval(timer);
      return;
    }
    const s = Math.floor(diff / 1000);
    units.days.textContent = Math.floor(s / 86400);
    units.hours.textContent = String(Math.floor((s % 86400) / 3600)).padStart(2, '0');
    units.minutes.textContent = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
    units.seconds.textContent = String(s % 60).padStart(2, '0');
  }

  const timer = setInterval(tick, 1000);
  tick();
})();
