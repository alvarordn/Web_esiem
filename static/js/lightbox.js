// Click-to-enlarge for any [data-lightbox="<image url>"] (optional data-caption), shown in <dialog id="lightbox">
// (templates/includes/lightbox.html). Delegated, so it also works for content rendered later (e.g. panel.js).
(function () {
  const dialog = document.getElementById('lightbox');
  if (!dialog) return;
  const img = document.getElementById('lightbox-img');
  const caption = document.getElementById('lightbox-caption');

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-lightbox]');
    if (!trigger) return;
    event.preventDefault(); // links keep an href as a no-JS fallback
    img.src = trigger.dataset.lightbox;
    img.alt = trigger.dataset.caption || '';
    caption.textContent = trigger.dataset.caption || '';
    dialog.showModal();
  });

  // Close with the × button or by clicking the backdrop (outside the image); Esc is handled by <dialog>.
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog || event.target.closest('[data-lightbox-close]')) dialog.close();
  });
})();
