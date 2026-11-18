// Public company directory: client-side sector filter + live text search.
(function () {
  const companies = JSON.parse(document.getElementById('companies-data').textContent);
  const grid = document.getElementById('company-grid');
  const search = document.getElementById('company-search');
  const filters = document.getElementById('sector-filters');
  const count = document.getElementById('result-count');
  const empty = document.getElementById('no-results');
  let activeSector = '';

  const normalize = (text) => (text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  function card(company) {
    const el = document.createElement('article');
    el.className = 'card overflow-hidden flex flex-col';

    const logo = document.createElement('div');
    logo.className = 'logo-tile border-b border-gray-200';
    if (company.logo) {
      const img = document.createElement('img');
      img.src = company.logo;
      img.alt = company.name;
      img.loading = 'lazy';
      logo.appendChild(img);
    } else {
      logo.innerHTML = '<span class="font-display text-2xl text-azul"></span>';
      logo.firstChild.textContent = company.name;
    }

    const body = document.createElement('div');
    body.className = 'p-5 flex-1 flex flex-col';
    const badge = document.createElement('span');
    badge.className = 'badge self-start';
    badge.textContent = company.sectorLabel;
    const title = document.createElement('h2');
    title.className = 'text-xl mt-2';
    title.textContent = company.name;
    const summary = document.createElement('p');
    summary.className = 'text-gray-600 text-sm mt-2 flex-1';
    summary.textContent = company.summary || 'Empresa participante en el encuentro.';
    body.append(badge, title, summary);

    if (company.website && /^https?:\/\//i.test(company.website)) {
      const link = document.createElement('a');
      link.href = company.website;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.className = 'text-azul font-semibold text-sm mt-4 hover:underline';
      link.textContent = 'Visitar web →';
      body.appendChild(link);
    }
    el.append(logo, body);
    return el;
  }

  function render() {
    const query = normalize(search.value.trim());
    const visible = companies.filter((c) =>
      (!activeSector || c.sector === activeSector) &&
      (!query || normalize(`${c.name} ${c.summary} ${c.sectorLabel}`).includes(query)));
    grid.replaceChildren(...visible.map(card));
    empty.hidden = visible.length > 0;
    count.textContent = companies.length ? `${visible.length} de ${companies.length} empresas` : '';
  }

  filters.addEventListener('click', (event) => {
    const button = event.target.closest('[data-sector]');
    if (!button) return;
    activeSector = button.dataset.sector;
    filters.querySelectorAll('[data-sector]').forEach((b) => {
      const active = b === button;
      b.classList.toggle('btn-primary', active);
      b.classList.toggle('btn-ghost', !active);
      b.setAttribute('aria-pressed', String(active));
    });
    render();
  });
  search.addEventListener('input', render);
  render();
})();
