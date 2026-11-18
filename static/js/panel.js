// Private area (admin CRM + exhibitor portal). Both roles share the same tab renderers;
// the API decides what each role may read or change, the UI only hides what it can't use.
(function () {
  'use strict';

  const config = JSON.parse(document.getElementById('panel-config').textContent);
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const isOrganizer = config.isOrganizer;
  const POLL_MS = 30000;

  const TABS = isOrganizer
    ? [['summary', 'Resumen & Bitácora'], ['attendees', 'Personas que asistirán al evento'], ['dossier', 'Dossier y Stand']]
    : [['general', 'Datos generales'], ['attendees', 'Personas que asistirán al evento'], ['dossier', 'Dossier y Stand']];

  // Organizers switch between two top-level views: «Empresas» (default) and «Registro» (organization diary).
  // composerKind: email kind to preload once in the composer (set by the overview's Aceptar/Rechazar).
  const state = { view: 'empresas', company: null, tab: TABS[0][0], templates: null, refreshers: [], composerKind: null };

  // ---------- helpers ----------

  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const labelOf = (choices, value) => (choices.find(([v]) => v === value) || [value, value])[1];
  const options = (choices, selected) => choices
    .map(([v, l]) => `<option value="${esc(v)}"${v === selected ? ' selected' : ''}>${esc(l)}</option>`).join('');
  const fmtDateTime = (iso) => new Date(iso).toLocaleString('es-ES', { dateStyle: 'long', timeStyle: 'medium' });
  const fileName = (url) => decodeURIComponent((url || '').split('/').pop());

  let uid = 0;
  function field(label, name, value, { type = 'text', required = false, attrs = '' } = {}) {
    const id = `f-${name}-${++uid}`;
    return `<div class="field"><label for="${id}">${esc(label)}</label>
      <input id="${id}" name="${name}" type="${type}" value="${esc(value)}" ${required ? 'required' : ''} ${attrs}></div>`;
  }
  function selectField(label, name, choices, value, attrs = '') {
    const id = `f-${name}-${++uid}`;
    return `<div class="field"><label for="${id}">${esc(label)}</label>
      <select id="${id}" name="${name}" ${attrs}>${options(choices, value)}</select></div>`;
  }
  function textareaField(label, name, value, rows = 4) {
    const id = `f-${name}-${++uid}`;
    return `<div class="field"><label for="${id}">${esc(label)}</label>
      <textarea id="${id}" name="${name}" rows="${rows}">${esc(value)}</textarea></div>`;
  }
  const formObject = (form) => Object.fromEntries(new FormData(form).entries());

  let toastTimer;
  function toast(message, isError = false) {
    const el = $('#toast');
    el.textContent = message;
    el.classList.toggle('error', isError);
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 7000 : 3500);
  }

  class ApiError extends Error {
    constructor(data, status) {
      super(ApiError.describe(data) || `Error ${status}`);
      this.data = data;
    }
    static describe(data) {
      if (!data || typeof data !== 'object') return '';
      return Object.entries(data).map(([key, value]) => {
        const text = Array.isArray(value) ? value.join(' ') : (typeof value === 'object' ? ApiError.describe(value) : value);
        return key === 'detail' || key === 'non_field_errors' ? text : `${key}: ${text}`;
      }).join(' · ');
    }
  }

  async function api(path, { method = 'GET', json, form } = {}) {
    const opts = { method, credentials: 'same-origin', headers: { 'X-CSRFToken': csrf, Accept: 'application/json' } };
    if (json !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(json);
    } else if (form) {
      opts.body = form;
    }
    const res = await fetch(config.apiRoot + path, opts);
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(data, res.status);
    return data;
  }

  // Run an async action from a form/button, disabling it meanwhile and reporting errors.
  async function run(button, action, successMessage) {
    if (button) button.disabled = true;
    try {
      const result = await action();
      if (successMessage) toast(successMessage);
      return result;
    } catch (err) {
      toast(err.message || 'Ha ocurrido un error.', true);
      return undefined;
    } finally {
      if (button) button.disabled = false;
    }
  }

  // ---------- company selection & header ----------

  function markView(view) {
    state.view = view;
    document.querySelectorAll('#main-tabs [data-view]').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.view === view)));
  }

  // Top-level views: leave any selected company and render the view from scratch.
  function showView(view) {
    markView(view);
    state.company = null;
    state.refreshers = [];
    $('#tabs').hidden = true;
    history.replaceState(null, '', view === 'registro' ? '?vista=registro' : location.pathname);
    (view === 'registro' ? renderRegistro : renderOverview)().catch((err) => toast(err.message, true));
  }

  async function selectCompany(id) {
    const company = await run(null, () => api(`companies/${id}/`));
    if (!company) return;
    markView('empresas');
    state.company = company;
    if (isOrganizer) history.replaceState(null, '', `?empresa=${id}`);
    renderHeader();
    renderTabs();
    showTab(state.tab);
  }

  async function reloadCompany() {
    state.company = await api(`companies/${state.company.id}/`);
    renderHeader();
  }

  function renderHeader() {
    const c = state.company;
    const primary = c.contacts.find((x) => x.is_primary) || c.contacts[0];
    $('#company-header').innerHTML = `
      <div class="card p-5 md:p-6 flex flex-col md:flex-row md:items-center gap-4 justify-between border-l-8 border-l-azul">
        <div>
          <div class="flex flex-wrap items-center gap-3">
            <h2 class="text-3xl">${esc(c.name)}</h2>
            <span class="badge badge-${esc(c.status)}">${esc(c.status_display)}</span>
          </div>
          <p class="text-gray-600 mt-1">${esc(c.sector_display)}${c.cif ? ` · CIF ${esc(c.cif)}` : ''}${c.website ? ` · <a class="text-azul hover:underline" href="${esc(c.website)}" target="_blank" rel="noopener noreferrer">${esc(c.website)}</a>` : ''}</p>
          ${primary ? `<p class="text-sm text-gray-600 mt-1">Contacto principal: ${esc(primary.name || '')} &lt;${esc(primary.email)}&gt;${primary.phone ? ` · ${esc(primary.phone)}` : ''}</p>` : ''}
          ${isOrganizer ? headerAccess(c) : ''}
        </div>
        <div class="text-center md:text-right shrink-0">
          <p class="text-xs uppercase font-bold text-gray-500">Stand asignado</p>
          <p class="font-display text-4xl text-rojo">${esc(c.stand_number || '—')}</p>
        </div>
      </div>`;
  }

  // Organizer header extras: accept/reject a company that sent the form, and its portal credentials.
  function headerAccess(c) {
    const access = c.portal_access;
    const decisions = c.status === 'interested' ? `
      <div class="flex flex-wrap items-center gap-2 mt-3">
        <span class="text-sm font-semibold text-amber-700">Pendiente de respuesta:</span>
        <button type="button" class="btn btn-accept btn-sm" data-decide="acceptance">✓ Aceptar</button>
        <button type="button" class="btn btn-reject btn-sm" data-decide="rejection">✕ Rechazar</button>
      </div>` : '';
    const credentials = access ? `
      <div class="mt-3 inline-flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-azul/20 bg-blue-50 px-3 py-2 text-sm">
        <span class="font-semibold text-azul">Acceso al portal${access.active ? '' : ' <span class="text-rojo">(desactivado)</span>'}</span>
        <span>Usuario: <code class="font-mono font-semibold">${esc(access.username)}</code></span>
        <span>Contraseña: ${access.password ? `<code class="font-mono font-semibold">${esc(access.password)}</code>` : '<span class="text-gray-500">no guardada</span>'}</span>
        <button type="button" class="text-azul font-semibold hover:underline" data-copy-access>Copiar</button>
        <button type="button" class="text-azul font-semibold hover:underline" data-decide="acceptance" title="Abre el correo de aceptación con este usuario y contraseña">Reenviar por correo</button>
      </div>` : '';
    return decisions + credentials;
  }

  // Header buttons (the header is re-rendered on every poll, so listen once on the container).
  $('#company-header').addEventListener('click', async (e) => {
    const decide = e.target.closest('[data-decide]');
    if (decide && state.company) {
      openDecision(state.company.id, decide.dataset.decide);
      return;
    }
    if (e.target.closest('[data-copy-access]') && state.company?.portal_access) {
      const { username, password } = state.company.portal_access;
      try {
        await navigator.clipboard.writeText(`Usuario: ${username}\nContraseña: ${password}`);
        toast('Usuario y contraseña copiados.');
      } catch {
        toast('No se ha podido copiar al portapapeles.', true);
      }
    }
  });

  function renderTabs() {
    const nav = $('#tabs');
    nav.hidden = false;
    nav.innerHTML = TABS.map(([key, label]) =>
      `<button type="button" class="tab" role="tab" data-tab="${key}" aria-selected="${key === state.tab}">${esc(label)}</button>`).join('');
  }

  function showTab(key) {
    state.tab = key;
    state.refreshers = [];
    document.querySelectorAll('#tabs [data-tab]').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === key)));
    // Fresh element per render so listeners from the previous tab don't pile up.
    const panel = document.createElement('div');
    panel.innerHTML = '<p class="text-gray-500">Cargando…</p>';
    $('#tab-panel').replaceChildren(panel);
    RENDERERS[key](panel).catch((err) => {
      panel.innerHTML = `<div class="card p-6 text-rojo">${esc(err.message || 'No se pudo cargar la pestaña.')}</div>`;
    });
  }

  // ---------- organizer: overview + search + new company ----------

  // Overview progress cell; states come from crm.serializers.file_state.
  const PROGRESS = {
    done: ['✓', 'Entregado', 'font-semibold text-green-700'],
    pending: ['Por confirmar', 'Subido por la organización, la empresa aún no lo ha confirmado', 'text-xs font-semibold text-amber-700'],
    missing: ['—', 'Sin entregar', 'text-gray-400'],
  };
  const progressCell = (state) => {
    const [text, title, cls] = PROGRESS[state] || PROGRESS.missing;
    return `<span class="${cls}" title="${esc(title)}">${esc(text)}<span class="sr-only"> (${esc(title)})</span></span>`;
  };

  async function renderOverview() {
    const companies = await api('companies/');
    const counts = Object.fromEntries(config.statuses.map(([v]) => [v, 0]));
    companies.forEach((c) => { counts[c.status] += 1; });
    $('#tabs').hidden = true;
    $('#company-header').innerHTML = `
      <div class="grid grid-cols-3 gap-3">
        ${config.statuses.map(([v, l]) => `<div class="card p-4"><p class="text-sm text-gray-600">${esc(l)}${v === 'interested' && counts[v] ? ' · pendientes de respuesta' : ''}</p><p class="font-display text-4xl">${counts[v]}</p></div>`).join('')}
      </div>
      <div class="flex flex-wrap items-center gap-3 mt-4">
        <span class="text-sm font-semibold text-gray-600">Material de todas las empresas (ZIP):</span>
        <a class="btn btn-ghost btn-sm" href="${esc(config.apiRoot)}companies/materials-zip/?group=catalogo" download
           title="Logotipo, dossier y anuncio de cada empresa, en una carpeta por empresa">⬇ Descargar material del dossier</a>
        <a class="btn btn-ghost btn-sm" href="${esc(config.apiRoot)}companies/materials-zip/?group=stand" download
           title="Platabanda de cada empresa, en una carpeta por empresa">⬇ Descargar material del stand</a>
      </div>`;
    // Fresh element per render so the delete listener doesn't pile up.
    const panel = document.createElement('div');
    $('#tab-panel').replaceChildren(panel);
    panel.addEventListener('click', async (e) => {
      const button = e.target.closest('[data-delete-company]');
      if (!button) return;
      e.stopPropagation(); // don't open the company (row click is handled on document)
      const name = button.dataset.name;
      if (!confirm(`¿Borrar la empresa «${name}»?\n\nSe eliminarán también sus contactos, notas, asistentes, historial de correos y documentación. Esta acción no se puede deshacer.`)) return;
      const ok = await run(button, () => api(`companies/${button.dataset.deleteCompany}/`, { method: 'DELETE' }).then(() => true), `Empresa «${name}» borrada.`);
      if (ok) showView('empresas');
    });
    panel.innerHTML = companies.length ? `
      <div class="card overflow-x-auto">
        <table class="data-table">
          <thead><tr>
            <th>Empresa</th><th>Sector</th><th>Estado</th>
            <th class="text-center">Asistentes</th><th class="text-center">Logotipo</th>
            <th class="text-center">Dossier</th><th class="text-center">Anuncio</th><th class="text-center">Platabanda</th>
            <th><span class="sr-only">Acciones</span></th>
          </tr></thead>
          <tbody>${companies.map((c) => `
            <tr class="hover:bg-gray-50 cursor-pointer" data-company="${c.id}">
              <td class="font-semibold text-azul">${esc(c.name)}</td>
              <td>${esc(labelOf(config.sectors, c.sector))}</td>
              <td><span class="badge badge-${esc(c.status)}">${esc(c.status_display)}</span></td>
              <td class="text-center">${c.attendee_count
                ? `<span class="font-semibold text-green-700" title="${c.attendee_count} asistente(s) registrados">✓ ${c.attendee_count}</span>`
                : progressCell('missing')}</td>
              <td class="text-center">${progressCell(c.logo_state)}</td>
              <td class="text-center">${progressCell(c.dossier_state)}</td>
              <td class="text-center">${progressCell(c.advert_state)}</td>
              <td class="text-center">${progressCell(c.banner_state)}</td>
              <td class="text-right">
                <button type="button" class="text-sm font-semibold text-rojo hover:underline disabled:opacity-50"
                  data-delete-company="${c.id}" data-name="${esc(c.name)}" aria-label="Borrar ${esc(c.name)}">Borrar</button>
              </td>
            </tr>`).join('')}</tbody>
        </table>
      </div>` : `
      <div class="card p-10 text-center text-gray-600">
        Todavía no hay empresas. Aparecerán aquí como «Interesada» cuando envíen el formulario de participación.
      </div>`;
  }

  function setupOrganizerControls() {
    const input = $('#company-search');
    const list = $('#company-results');
    let timer;

    async function search() {
      const results = await api(`companies/?search=${encodeURIComponent(input.value.trim())}`).catch(() => []);
      list.innerHTML = results.length
        ? results.map((c) => `<li role="option" class="px-4 py-2 hover:bg-gray-100 cursor-pointer flex justify-between gap-3" data-company="${c.id}">
            <span>${esc(c.name)}</span><span class="badge badge-${esc(c.status)}">${esc(c.status_display)}</span></li>`).join('')
        : '<li class="px-4 py-2 text-gray-500">Sin resultados</li>';
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }
    function close() {
      list.hidden = true;
      input.setAttribute('aria-expanded', 'false');
    }

    input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, 200); });
    input.addEventListener('focus', search);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') close();
      if (e.key === 'Enter') {
        const first = list.querySelector('[data-company]');
        if (first) { first.click(); e.preventDefault(); }
      }
    });
    document.addEventListener('click', (e) => {
      const pick = e.target.closest('[data-company]');
      if (pick) {
        close();
        input.value = '';
        selectCompany(pick.dataset.company);
      } else if (!e.target.closest('#company-search')) {
        close();
      }
    });
  }

  // ---------- organizer: «Registro» (organization diary linked to objectives) ----------

  const parseDate = (iso) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d); };
  const fmtDate = (iso) => parseDate(iso).toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' });
  const daysLeft = (iso) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.round((parseDate(iso) - today) / 86400000);
  };
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  // Objectives are stored relative to the event date, so they carry over to the next edition.
  function eventOffset(days) {
    if (days > 0) return `${plural(days, 'día', 'días')} antes del evento`;
    if (days < 0) return `${plural(-days, 'día', 'días')} después del evento`;
    return 'El día del evento';
  }

  // [label, border colour, text colour] for an objective's deadline situation.
  function objectiveStatus(o) {
    if (o.done) return ['Completado', 'border-l-green-600', 'text-green-700'];
    const days = daysLeft(o.deadline);
    if (days < 0) return [`Vencido hace ${plural(-days, 'día', 'días')}`, 'border-l-rojo', 'text-rojo'];
    if (days === 0) return ['Vence hoy', 'border-l-rojo', 'text-rojo'];
    if (days <= 14) return [`Faltan ${plural(days, 'día', 'días')}`, 'border-l-oro', 'text-amber-700'];
    return [`Faltan ${plural(days, 'día', 'días')}`, 'border-l-azul', 'text-gray-600'];
  }

  async function renderRegistro() {
    const panel = document.createElement('div');
    panel.innerHTML = '<p class="text-gray-500">Cargando…</p>';
    $('#tab-panel').replaceChildren(panel);
    $('#company-header').innerHTML = '';

    let objectives = [];
    let entries = [];
    let selected = null; // id of the objective whose diary is unfolded

    panel.innerHTML = `
      <div class="grid gap-6 lg:grid-cols-3">
        <section class="card p-5 lg:col-span-2">
          <div class="flex items-center justify-between gap-3">
            <h2 class="text-2xl">Objetivos</h2>
            <button type="button" class="btn btn-ghost btn-sm" data-action="new-objective">+ Nuevo objetivo</button>
          </div>
          <form id="objective-form" class="mt-4 grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end border border-gray-200 rounded-lg p-4" hidden>
            ${field('Objetivo', 'title', '', { required: true })}
            ${field('Fecha límite', 'deadline', '', { type: 'date', required: true })}
            <div class="flex gap-2"><button class="btn btn-primary btn-sm">Crear</button><button type="button" class="btn btn-ghost btn-sm" data-action="cancel-objective">Cancelar</button></div>
          </form>
          <p class="text-sm text-gray-600 mt-2">Haz clic en un objetivo para ver su diario.</p>
          <div id="objective-grid" class="mt-4 flex flex-col gap-2"></div>
          <div id="objective-detail" class="mb-2" hidden></div>
        </section>
        <div class="space-y-6">
          <section class="card p-5">
            <h2 class="text-2xl">Nueva anotación</h2>
            <form id="entry-form" class="mt-4 space-y-3">
              <div class="field"><label for="entry-objective">Objetivo</label><select id="entry-objective" name="objective"></select></div>
              <div class="field"><label for="entry-text">Acción realizada</label>
                <textarea id="entry-text" name="text" rows="4" required placeholder="Ej.: Enviado correo a Conserjería para reservar el aula 1.1"></textarea></div>
              <button class="btn btn-primary">Añadir al registro</button>
            </form>
          </section>
          <section class="card p-5">
            <h2 class="text-2xl">Diario</h2>
            <div id="diary" class="timeline mt-4"></div>
          </section>
        </div>
      </div>`;

    const grid = $('#objective-grid', panel);
    const detail = $('#objective-detail', panel);
    const entryForm = $('#entry-form', panel);
    const objectiveForm = $('#objective-form', panel);
    const select = entryForm.elements.objective;

    const entryItem = (e, withObjective) => `
      <div class="timeline-item">
        <p class="text-xs text-gray-500"><strong class="text-gray-700">${esc(fmtDateTime(e.created_at))}</strong> · ${esc(e.author_name)}</p>
        ${withObjective && e.objective ? `<button type="button" class="badge badge-confirmed mt-1 text-left hover:underline" data-objective="${e.objective}">${esc(e.objective_title)}</button>` : ''}
        ${withObjective && !e.objective ? '<span class="badge mt-1">General</span>' : ''}
        <p class="mt-1 whitespace-pre-line">${esc(e.text)}</p>
      </div>`;

    function renderStats() {
      const done = objectives.filter((o) => o.done).length;
      const overdue = objectives.filter((o) => !o.done && daysLeft(o.deadline) < 0).length;
      const next = objectives.filter((o) => !o.done && daysLeft(o.deadline) >= 0)
        .sort((a, b) => a.deadline.localeCompare(b.deadline))[0];
      $('#company-header').innerHTML = `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div class="card p-4"><p class="text-sm text-gray-600">Objetivos</p><p class="font-display text-4xl">${objectives.length}</p></div>
          <div class="card p-4"><p class="text-sm text-gray-600">Completados</p><p class="font-display text-4xl text-green-700">${done}</p></div>
          <div class="card p-4"><p class="text-sm text-gray-600">Vencidos sin completar</p><p class="font-display text-4xl text-rojo">${overdue}</p></div>
          <div class="card p-4"><p class="text-sm text-gray-600">Próxima fecha límite</p>
            ${next ? `<p class="font-display text-2xl">${esc(fmtDate(next.deadline))}</p><p class="text-xs text-gray-600 truncate" title="${esc(next.title)}">${esc(next.title)}</p>` : '<p class="font-display text-4xl">—</p>'}</div>
        </div>`;
    }

    function renderSelect() {
      const current = select.value;
      select.innerHTML = '<option value="">— General (sin objetivo) —</option>' + objectives
        .map((o) => `<option value="${o.id}">${esc(o.title)} · ${esc(fmtDate(o.deadline))}${o.done ? ' (completado)' : ''}</option>`).join('');
      select.value = objectives.some((o) => String(o.id) === current) ? current : '';
    }

    function renderGrid() {
      grid.innerHTML = objectives.map((o) => {
        const [label, border, color] = objectiveStatus(o);
        const isSelected = o.id === selected;
        return `
          <button type="button" data-objective="${o.id}" aria-expanded="${isSelected}" aria-controls="objective-detail"
            class="card px-4 py-3 text-left border-l-8 ${border} hover:shadow-md transition flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 ${isSelected ? 'ring-2 ring-azul' : ''} ${o.done ? 'opacity-70' : ''}">
            <span class="font-semibold leading-snug flex-1 ${o.done ? 'line-through' : ''}">${esc(o.title)}</span>
            <span class="text-sm sm:w-28 shrink-0"><strong>${esc(fmtDate(o.deadline))}</strong></span>
            <span class="text-xs font-semibold sm:w-36 shrink-0 ${color}">${esc(label)}</span>
            <span class="text-xs text-gray-500 sm:w-24 shrink-0 sm:text-right">${esc(plural(o.entry_count, 'anotación', 'anotaciones'))}</span>
          </button>`;
      }).join('') || '<p class="text-gray-500">No hay objetivos.</p>';
    }

    function renderDetail() {
      const o = objectives.find((x) => x.id === selected);
      if (!o) { detail.hidden = true; return; }
      const [label, border, color] = objectiveStatus(o);
      const own = entries.filter((e) => e.objective === o.id);
      detail.hidden = false;
      detail.innerHTML = `
        <div class="border border-gray-200 border-l-8 ${border} rounded-lg p-5">
          <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
            <div>
              <h3 class="text-2xl">${esc(o.title)}</h3>
              <p class="text-sm mt-1">Fecha límite: <strong>${esc(fmtDate(o.deadline))}</strong> · <span class="font-semibold ${color}">${esc(label)}</span></p>
              <p class="text-xs text-gray-500 mt-1">${esc(eventOffset(o.days_before_event))}</p>
            </div>
            <div class="flex gap-2 shrink-0">
              <button type="button" class="btn ${o.done ? 'btn-ghost' : 'btn-accent'} btn-sm" data-action="toggle-done">${o.done ? 'Reabrir' : 'Marcar como completado'}</button>
              <button type="button" class="btn btn-ghost btn-sm" data-action="close-detail" aria-label="Cerrar diario">✕</button>
            </div>
          </div>
          <div class="timeline mt-5">${own.map((e) => entryItem(e, false)).join('') || '<p class="text-gray-500">Todavía no hay anotaciones para este objetivo.</p>'}</div>
        </div>`;
      // Unfold right below the clicked objective (renderGrid has just detached it).
      grid.querySelector(`[data-objective="${o.id}"]`).after(detail);
    }

    function renderDiary() {
      $('#diary', panel).innerHTML = entries.map((e) => entryItem(e, true)).join('') || '<p class="text-gray-500">Sin anotaciones todavía.</p>';
    }

    async function load() {
      [objectives, entries] = await Promise.all([api('objectives/'), api('log-entries/')]);
      renderStats();
      renderSelect();
      renderGrid();
      renderDetail();
      renderDiary();
    }

    function open(id) {
      selected = selected === id ? null : id;
      if (selected) select.value = String(selected); // new entries default to the unfolded objective
      renderGrid();
      renderDetail();
      if (selected) detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    panel.addEventListener('click', async (e) => {
      const card = e.target.closest('[data-objective]');
      if (card) {
        if (!grid.contains(card)) selected = null; // a diary badge always unfolds, never folds
        open(Number(card.dataset.objective));
        return;
      }
      const button = e.target.closest('[data-action]');
      if (!button) return;
      const action = button.dataset.action;
      if (action === 'new-objective') {
        objectiveForm.reset();
        objectiveForm.hidden = false;
        objectiveForm.elements.title.focus();
      } else if (action === 'cancel-objective') {
        objectiveForm.hidden = true;
      } else if (action === 'close-detail') {
        open(selected);
      } else if (action === 'toggle-done') {
        const o = objectives.find((x) => x.id === selected);
        const ok = await run(button, () => api(`objectives/${o.id}/`, { method: 'PATCH', json: { done: !o.done } }),
          o.done ? 'Objetivo reabierto.' : 'Objetivo completado.');
        if (ok) await load();
      }
    });

    objectiveForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const created = await run($('button', objectiveForm), () => api('objectives/', { method: 'POST', json: formObject(objectiveForm) }), 'Objetivo creado.');
      if (created) {
        objectiveForm.hidden = true;
        selected = created.id;
        await load();
        select.value = String(created.id);
      }
    });

    entryForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const data = formObject(entryForm);
      const saved = await run($('button', entryForm), () => api('log-entries/', { method: 'POST', json: { text: data.text, objective: data.objective || null } }), 'Anotación añadida.');
      if (saved) {
        entryForm.elements.text.value = '';
        await load();
      }
    });

    await load();
    state.refreshers.push(load);
  }

  // ---------- email composer (organizer, «Resumen & Bitácora») ----------

  // All organizer emails go out from the «Resumen & Bitácora» composer. Each kind loads its default
  // template. «Aceptación» and «Rechazo» also decide the company's status when they are sent
  // (acceptance creates the portal user whose credentials are in the email).
  const EMAIL_KINDS = [
    ['acceptance', 'Aceptación'],
    ['rejection', 'Rechazo'],
    ['summary', 'Seguimiento'],
    ['attendees', 'Solicitar lista de asistentes'],
    ['dossier', 'Solicitar materiales'],
  ];
  const DECISIONS = {
    acceptance: {
      action: '✓ Aceptar y enviar correo de aceptación', cls: 'btn-accept', status: '«Aceptada»',
      register: 'Ya lo he enviado: aceptar la empresa', done: 'Empresa aceptada y correo registrado.',
    },
    rejection: {
      action: '✕ Rechazar y enviar correo de rechazo', cls: 'btn-reject', status: '«Rechazada»',
      register: 'Ya lo he enviado: rechazar la empresa', done: 'Empresa rechazada y correo registrado.',
    },
  };

  // From the overview's «Aceptar» / «Rechazar» buttons: open the company with that draft loaded.
  function openDecision(companyId, kind) {
    state.tab = 'summary';
    state.composerKind = kind;
    selectCompany(companyId);
  }

  async function mountComposer(el, onSent) {
    if (!state.templates) state.templates = await api('email-templates/');
    const contacts = state.company.contacts;
    let kind = state.composerKind || 'summary';
    const scrollIntoView = Boolean(state.composerKind);
    state.composerKind = null;
    let credentials = null; // {username, password} of the acceptance draft
    const defaultTemplate = state.templates.defaults[kind];
    el.innerHTML = `
      <h2 class="text-2xl">Enviar correo</h2>
      ${state.company.status === 'interested' ? `
        <p class="mt-2 rounded-lg bg-amber-50 border border-oro p-3 text-sm">Esta empresa está <strong>pendiente de respuesta</strong>. Elige el tipo de correo «Aceptación» o «Rechazo».</p>` : ''}
      ${contacts.length ? `
      <form class="space-y-4 mt-4">
        <div class="field"><label>Tipo de correo</label>
          <select name="kind">${options(EMAIL_KINDS, kind)}</select>
          <span class="field-help">«Aceptación» y «Rechazo» cambian el estado de la empresa al enviarse.</span></div>
        <fieldset>
          <legend class="font-semibold text-sm mb-2">Destinatarios</legend>
          <div class="space-y-1">${contacts.map((c) => `
            <label class="flex items-center gap-2 text-sm">
              <input type="checkbox" name="recipients" value="${esc(c.email)}" ${c.is_primary ? 'checked' : ''}>
              <span>${esc(c.name || c.email)}${c.name ? ` &lt;${esc(c.email)}&gt;` : ''}${c.position ? ` <span class="text-gray-500">· ${esc(c.position)}</span>` : ''}</span>
            </label>`).join('')}
          </div>
        </fieldset>
        <div class="field"><label>Plantilla (.txt)</label>
          <select name="template">${state.templates.templates.map((t) => `<option${t === defaultTemplate ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>
        </div>
        <p data-credentials hidden class="rounded-lg bg-azul/10 border border-azul/30 p-3 text-sm text-azul">El usuario y la contraseña del correo son los del recuadro «Acceso al portal del expositor» (debajo de «Contactos»). Si los cambias allí, se cambian aquí.</p>
        <div class="field"><label>Asunto</label><input name="subject" required></div>
        <div class="field"><label>Mensaje</label><textarea name="body" rows="14" required class="font-mono text-sm"></textarea>
          <span class="field-help">Las variables de la plantilla ya están sustituidas. Puedes editar el texto libremente antes de enviar.</span></div>
        <div data-decision hidden>
          <button type="button" data-decide-send class="btn w-full sm:w-auto"></button>
          <p class="text-xs text-gray-500 mt-2" data-decision-help></p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" data-open="web" class="btn btn-primary">Abrir en Outlook (web)</button>
          <button type="button" data-open="app" class="btn btn-ghost">Abrir en la app de correo</button>
          <button type="button" data-open="copy" class="btn btn-ghost">Copiar texto</button>
          ${config.automaticEmail ? '<button type="submit" class="btn btn-ghost" data-auto>Enviar automáticamente</button>' : ''}
        </div>
        <div data-pending hidden class="rounded-lg border border-oro bg-amber-50 p-4 text-sm">
          <p data-pending-text></p>
          <div class="mt-3 flex flex-wrap gap-2">
            <button type="button" data-register class="btn btn-primary btn-sm">Ya lo he enviado: registrar</button>
            <button type="button" data-discard class="btn btn-ghost btn-sm">No lo he enviado</button>
          </div>
        </div>
      </form>` : '<p class="text-gray-600 mt-3">La empresa no tiene contactos. Añade uno en «Contactos».</p>'}`;

    const form = $('form', el);
    if (!form) return;
    const pendingBox = $('[data-pending]', form);
    let pending = null; // snapshot of the message opened in the organizer's mail client
    let dirty = false;
    form.body.addEventListener('input', () => { dirty = true; });
    form.subject.addEventListener('input', () => { dirty = true; });

    // Show the decision button and the generated credentials for «Aceptación» / «Rechazo».
    function refreshKindUI() {
      const decision = DECISIONS[kind];
      const box = $('[data-decision]', form);
      box.hidden = !decision;
      const openWeb = $('[data-open="web"]', form);
      openWeb.classList.toggle('btn-primary', !decision);
      openWeb.classList.toggle('btn-ghost', Boolean(decision));
      if (decision) {
        const button = $('[data-decide-send]', box);
        const resend = kind === 'acceptance' && state.company.status === 'confirmed';
        button.textContent = resend ? '✓ Enviar de nuevo el correo con el acceso' : decision.action;
        button.className = `btn ${decision.cls} w-full sm:w-auto`;
        $('[data-decision-help]', box).textContent = config.automaticEmail
          ? `Envía el correo y la empresa pasa a ${decision.status}.`
          : `Abre el correo en Outlook; cuando lo envíes, confírmalo aquí y la empresa pasará a ${decision.status}.`;
      }
      $('[data-credentials]', form).hidden = !(kind === 'acceptance' && credentials);
    }

    // The «Acceso al portal» box changed usuario/contraseña: rewrite them in the message
    // (whole-token matches of the value currently in it). `credentials` = the values in the body.
    function applyCredential(key, value, markDirty = true) {
      const previous = credentials?.[key];
      value = (value || '').trim();
      if (!previous || !value || value === previous) return;
      const quoted = previous.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const token = new RegExp(`(?<![\\w.@+-])${quoted}(?![\\w.@+-])`, 'g');
      form.body.value = form.body.value.replace(token, () => value);
      credentials = { ...credentials, [key]: value };
      if (markDirty) dirty = true;
    }

    async function loadTemplate() {
      if (dirty && !confirm('¿Reemplazar el texto editado por la plantilla seleccionada?')) return;
      const tpl = await run(null, () => api(`companies/${state.company.id}/email-template/?name=${encodeURIComponent(form.template.value)}`));
      if (!tpl) return;
      form.subject.value = tpl.subject;
      form.body.value = tpl.body;
      credentials = tpl.credentials;
      if (credentials) {
        // Use the usuario/contraseña of the «Acceso al portal» box, not the ones the server proposed.
        if (state.access) {
          applyCredential('username', state.access.username, false);
          applyCredential('password', state.access.password, false);
        }
        // A template with usuario/contraseña is an acceptance: only that kind creates the portal account.
        if (kind !== 'acceptance') {
          kind = 'acceptance';
          form.elements.kind.value = kind;
        }
      }
      dirty = false;
      refreshKindUI();
    }
    form.template.addEventListener('change', loadTemplate);
    form.elements.kind.addEventListener('change', async () => {
      const previous = kind;
      kind = form.elements.kind.value;
      const template = state.templates.defaults[kind];
      if (template && form.template.value !== template) {
        const before = form.template.value;
        form.template.value = template;
        await loadTemplate();
        // loadTemplate keeps the edited text if the organizer cancels; keep the selectors consistent.
        if (dirty) {
          form.template.value = before;
          kind = previous;
          form.elements.kind.value = previous;
        }
      }
      refreshKindUI();
    });
    if (form.template.value) await loadTemplate();
    refreshKindUI();
    if (scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'start' });

    function message() {
      const recipients = [...form.querySelectorAll('[name=recipients]:checked')].map((x) => x.value);
      if (!recipients.length) { toast('Selecciona al menos un destinatario.', true); return null; }
      const f = form.elements;
      const msg = { recipients, subject: f.subject.value, body: f.body.value, template: f.template.value, kind };
      if (kind === 'acceptance' && credentials) {
        const username = (state.access?.username || '').trim();
        const password = (state.access?.password || '').trim();
        if (username.length < 3) { toast('El usuario del recuadro «Acceso al portal» debe tener al menos 3 caracteres.', true); return null; }
        if (password.length < 8) { toast('La contraseña del recuadro «Acceso al portal» debe tener al menos 8 caracteres.', true); return null; }
        if (!msg.body.includes(username) || !msg.body.includes(password)) {
          toast('El mensaje no contiene el usuario o la contraseña del recuadro «Acceso al portal». Revisa el texto.', true);
          return null;
        }
        Object.assign(msg, { username, password });
      }
      return msg;
    }

    async function save(button, msg, successMessage) {
      const sent = await run(button, () => api(`companies/${state.company.id}/send-email/`, { method: 'POST', json: msg }), successMessage);
      if (sent) {
        dirty = false;
        if (DECISIONS[msg.kind]) await reloadCompany();
        if (onSent) await onSent();
      }
      return sent;
    }

    // Outlook on the web (the US mailboxes live in Microsoft 365) or the default mail app.
    const composeUrl = {
      web: (m) => 'https://outlook.office.com/mail/deeplink/compose?' + new URLSearchParams(
        { to: m.recipients.join(','), subject: m.subject, body: m.body }).toString().replace(/\+/g, '%20'),
      app: (m) => `mailto:${m.recipients.map(encodeURIComponent).join(',')}?subject=${encodeURIComponent(m.subject)}&body=${encodeURIComponent(m.body)}`,
    };

    function markPending(msg) {
      pending = msg;
      const decision = DECISIONS[msg.kind];
      $('[data-pending-text]', form).textContent = decision
        ? `Cuando lo hayas enviado desde tu correo, confírmalo: la empresa pasará a ${decision.status} y el envío quedará en la Bitácora CRM.`
        : 'Cuando lo hayas enviado desde tu correo, regístralo para que conste en la Bitácora CRM.';
      $('[data-register]', form).textContent = decision ? decision.register : 'Ya lo he enviado: registrar';
      pendingBox.hidden = false;
    }

    async function openIn(how, msg) {
      if (how === 'copy') {
        try {
          await navigator.clipboard.writeText(`Para: ${msg.recipients.join(', ')}\nAsunto: ${msg.subject}\n\n${msg.body}`);
          toast('Texto copiado. Pégalo en un correo nuevo de Outlook.');
        } catch {
          toast('No se ha podido copiar al portapapeles.', true);
          return;
        }
      } else if (how === 'web') {
        window.open(composeUrl.web(msg), '_blank', 'noopener');
      } else {
        window.location.href = composeUrl.app(msg);
      }
      markPending(msg);
    }

    form.querySelectorAll('[data-open]').forEach((button) => button.addEventListener('click', () => {
      const msg = message();
      if (msg) openIn(button.dataset.open, msg);
    }));

    // «Aceptar y enviar…» / «Rechazar y enviar…»: sends it (automatic mode) or opens it in Outlook.
    $('[data-decide-send]', form).addEventListener('click', async (e) => {
      const msg = message();
      if (!msg) return;
      const decision = DECISIONS[msg.kind];
      if (!config.automaticEmail) {
        openIn('web', msg);
        return;
      }
      if (!confirm(`¿Enviar el correo a ${msg.recipients.length} destinatario(s)? La empresa pasará a ${decision.status}.`)) return;
      await save(e.currentTarget, msg, decision.done.replace(' y correo registrado', ' y correo enviado'));
    });

    $('[data-register]', form).addEventListener('click', async (e) => {
      const decision = DECISIONS[pending.kind];
      if (await save(e.currentTarget, { ...pending, manual: true }, decision ? decision.done : 'Envío registrado.')) {
        pending = null;
        pendingBox.hidden = true;
      }
    });
    $('[data-discard]', form).addEventListener('click', () => {
      pending = null;
      pendingBox.hidden = true;
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const msg = message();
      if (!msg) return;
      const decision = DECISIONS[msg.kind];
      const question = `¿Enviar el correo automáticamente a ${msg.recipients.length} destinatario(s)?${decision ? ` La empresa pasará a ${decision.status}.` : ''}`;
      if (!confirm(question)) return;
      await save(e.submitter, msg, decision ? decision.done.replace(' y correo registrado', ' y correo enviado') : 'Correo enviado.');
    });
    return { applyCredential };
  }

  // «Acceso al portal del expositor», below «Contactos»: the usuario/contraseña of the acceptance
  // email. Editable while the company isn't accepted, read-only (they can only be resent) afterwards.
  async function loadPortalAccess(force = false) {
    const c = state.company;
    if (!force && state.access?.companyId === c.id && state.access.status === c.status) return;
    const data = await api(`companies/${c.id}/portal-credentials/`);
    state.access = { ...data, companyId: c.id, status: c.status };
  }

  function renderPortalAccess(target, onChange) {
    const el = target.cloneNode(false);
    target.replaceWith(el);
    const access = state.access;
    if (!access) return;
    // Accepted: both fixed, except a password that wasn't kept (it can be reset by resending).
    const fixed = { username: access.locked, password: access.locked && access.password_known };
    const input = (name, label) => `
      <label class="block text-sm font-semibold">${label}
        <input name="${name}" value="${esc(access[name])}" autocomplete="off" spellcheck="false"${fixed[name] ? ' readonly' : ''}
          class="input mt-1 font-mono text-base text-gray-900${fixed[name] ? ' bg-blue-100 cursor-not-allowed' : ''}"></label>`;
    let help = 'Puedes cambiarlos. Se copian automáticamente en el correo de «Aceptación» y la cuenta se crea con ellos al aceptar la empresa.';
    if (access.locked) {
      help = access.password_known
        ? 'La empresa ya está aceptada: estos son sus datos de acceso y no se pueden cambiar. Puedes reenviarlos con el correo de «Aceptación».'
        : 'La empresa ya está aceptada, pero su contraseña no está guardada. Esta es una nueva: al reenviar el correo de «Aceptación» se le asigna y queda fijada.';
    }
    el.className = 'rounded-xl bg-azul text-white p-5 shadow-md';
    el.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <h2 class="text-2xl text-oro">Acceso al portal del expositor</h2>
        ${access.locked ? '<span class="badge badge-confirmed">🔒 Aceptada</span>' : ''}
      </div>
      <div class="mt-4 grid gap-3 sm:grid-cols-2">${input('username', 'Usuario')}${input('password', 'Contraseña')}</div>
      <p class="text-xs text-white/80 mt-3">${help}</p>`;
    el.querySelectorAll('input:not([readonly])').forEach((field) => field.addEventListener('input', () => {
      access[field.name] = field.value.trim();
      onChange(field.name, access[field.name]);
    }));
  }

  // ---------- "Datos generales" form (both roles) ----------

  // Companies see their identity and the organizers' fields disabled (disabled controls are not
  // submitted, and CompanyPortalSerializer makes them read-only anyway).
  function companyDataForm(c) {
    const locked = isOrganizer ? '' : 'disabled';
    return `
      <form id="company-form" class="card p-5 space-y-4">
        <h2 class="text-2xl">Datos generales</h2>
        ${isOrganizer ? '' : '<p class="text-sm text-gray-600">Revisa y, si hace falta, corrige los datos de tu empresa. El nombre, CIF, sector y estado solo los puede cambiar la organización.</p>'}
        <div class="grid gap-4 sm:grid-cols-2">
          ${field('Nombre', 'name', c.name, { required: true, attrs: locked })}
          ${field('CIF', 'cif', c.cif, { attrs: locked })}
          ${selectField('Sector', 'sector', config.sectors, c.sector, locked)}
          ${selectField('Estado', 'status', config.statuses, c.status, locked)}
          ${field('Sitio web', 'website', c.website, { type: 'url', attrs: 'placeholder="https://"' })}
          ${isOrganizer ? field('Stand asignado', 'stand_number', c.stand_number) : ''}
        </div>
        ${isOrganizer ? textareaField('Resumen público (directorio)', 'summary', c.summary, 3) : ''}
        <h3 class="text-xl pt-2">Contrato y facturación</h3>
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="sm:col-span-2">${field('Domicilio', 'address', c.address)}</div>
          ${field('Población', 'city', c.city)}
          ${field('Código postal', 'postal_code', c.postal_code)}
          ${field('Teléfono', 'phone', c.phone)}
          ${field('Fax', 'fax', c.fax)}
          ${field('Firmante del contrato', 'signer_name', c.signer_name)}
          ${field('Calidad en la que firma', 'signer_capacity', c.signer_capacity)}        </div>
        <button class="btn btn-primary">Guardar cambios</button>
      </form>`;
  }

  function bindCompanyDataForm(root) {
    $('#company-form', root).addEventListener('submit', async (e) => {
      e.preventDefault();
      const updated = await run($('button', e.target), () => api(`companies/${state.company.id}/`, { method: 'PATCH', json: formObject(e.target) }), 'Datos guardados.');
      if (updated) { state.company = updated; renderHeader(); }
    });
  }

  // ---------- tab: Datos generales (company) ----------

  async function renderGeneral(root) {
    root.innerHTML = `<div class="max-w-3xl">${companyDataForm(state.company)}</div>`;
    bindCompanyDataForm(root);
  }

  // ---------- tab: Resumen & Bitácora (organizer) ----------

  async function renderSummary(root) {
    const c = state.company;
    root.innerHTML = `
      <div class="grid gap-6 lg:grid-cols-2">
        <div class="space-y-6">
          ${companyDataForm(c)}
          <section class="card p-5" id="contacts"></section>
          <section id="portal-access"></section>
        </div>
        <div class="space-y-6">
          <section class="card p-5">
            <h2 class="text-2xl">Bitácora CRM</h2>
            <form id="note-form" class="mt-4 space-y-3">
              <div class="field"><label for="note-text">Nueva anotación</label>
                <textarea id="note-text" name="text" rows="3" required placeholder="Ej.: Llamada telefónica: aceptan participar"></textarea></div>
              <div class="flex gap-3 items-end">
                <div class="field flex-1"><label for="note-kind">Tipo</label><select id="note-kind" name="kind">${options(config.noteKinds, 'note')}</select></div>
                <button class="btn btn-primary">Añadir nota</button>
              </div>
            </form>
            <div id="timeline" class="timeline mt-6"></div>
          </section>
          <section class="card p-5" id="composer"></section>
        </div>
      </div>`;

    bindCompanyDataForm(root);

    const timeline = $('#timeline', root);
    async function loadNotes() {
      const notes = await api(`notes/?company=${c.id}`);
      const open = new Set([...timeline.querySelectorAll('details[open]')].map((d) => d.dataset.note));
      timeline.innerHTML = notes.length ? notes.map((n) => `
        <div class="timeline-item kind-${esc(n.kind)}">
          <p class="text-xs text-gray-500"><strong class="text-gray-700">${esc(fmtDateTime(n.created_at))}</strong> · ${esc(n.author_name)} · <span class="badge">${esc(n.kind_display)}</span></p>
          ${noteBody(n, open.has(String(n.id)))}
        </div>`).join('') : '<p class="text-gray-500">Sin anotaciones todavía.</p>';
    }
    // Sent emails are logged as "summary line, blank line, message": show the message collapsed.
    function noteBody(n, isOpen) {
      const split = n.kind === 'email' ? n.text.indexOf('\n\n') : -1;
      if (split < 0) return `<p class="mt-1 whitespace-pre-line">${esc(n.text)}</p>`;
      return `<p class="mt-1 whitespace-pre-line">${esc(n.text.slice(0, split))}</p>
        <details class="mt-1" data-note="${n.id}"${isOpen ? ' open' : ''}><summary class="cursor-pointer text-sm text-azul">Ver correo</summary>
          <pre class="mt-2 text-sm whitespace-pre-wrap font-sans text-gray-700 border-l-2 border-gray-200 pl-3">${esc(n.text.slice(split + 2))}</pre>
        </details>`;
    }
    async function afterEmailSent() {
      // An acceptance/rejection changes the status: keep the form in sync so saving it doesn't revert it.
      $('#company-form', root).elements.status.value = state.company.status;
      await Promise.all([loadNotes(), showPortalAccess()]);
    }
    let composer = null;
    async function showPortalAccess() {
      await loadPortalAccess();
      renderPortalAccess($('#portal-access', root), (key, value) => composer?.applyCredential(key, value));
    }
    $('#note-form', root).addEventListener('submit', async (e) => {
      e.preventDefault();
      const note = await run($('button', e.target), () => api('notes/', { method: 'POST', json: { ...formObject(e.target), company: c.id } }), 'Nota añadida.');
      if (note) { e.target.reset(); loadNotes(); }
    });

    renderContacts($('#contacts', root));
    await showPortalAccess(); // before the composer, which writes these credentials in the acceptance draft
    [composer] = await Promise.all([mountComposer($('#composer', root), afterEmailSent), loadNotes()]);
    state.refreshers.push(loadNotes);
  }

  function renderContacts(target) {
    const c = state.company;
    const el = target.cloneNode(false);
    target.replaceWith(el);
    el.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <h2 class="text-2xl">Contactos</h2>
        <button type="button" class="btn btn-ghost btn-sm" data-action="new">+ Añadir contacto</button>
      </div>
      <ul class="mt-4 divide-y divide-gray-200">${c.contacts.map((x) => `
        <li class="py-3 flex justify-between gap-3">
          <div class="min-w-0">
            <p class="font-semibold">${esc(x.name || '(sin nombre)')} ${x.is_primary ? '<span class="badge badge-confirmed">Principal</span>' : ''}</p>
            <p class="text-sm text-gray-600 break-all">${esc(x.email)}${x.phone ? ` · ${esc(x.phone)}` : ''}${x.position ? ` · ${esc(x.position)}` : ''}</p>
          </div>
          <div class="flex gap-2 shrink-0">
            <button type="button" class="btn btn-ghost btn-sm" data-action="edit" data-id="${x.id}">Editar</button>
            <button type="button" class="btn btn-ghost btn-sm text-rojo" data-action="delete" data-id="${x.id}">Borrar</button>
          </div>
        </li>`).join('') || '<li class="py-3 text-gray-500">Sin contactos.</li>'}
      </ul>
      <form class="mt-4 space-y-3 border-t border-gray-200 pt-4" hidden>
        <h3 class="text-lg" data-form-title>Nuevo contacto</h3>
        <div class="grid gap-3 sm:grid-cols-2">
          ${field('Nombre', 'name', '')}${field('Email', 'email', '', { type: 'email', required: true })}
          ${field('Teléfono', 'phone', '')}${field('Cargo', 'position', '', { attrs: 'placeholder="RRHH, Director de Talento…"' })}
        </div>
        <label class="flex items-center gap-2 text-sm"><input type="checkbox" name="is_primary"> Contacto principal</label>
        <div class="flex gap-2"><button class="btn btn-primary btn-sm">Guardar</button><button type="button" class="btn btn-ghost btn-sm" data-action="cancel">Cancelar</button></div>
      </form>`;

    const form = $('form', el);
    el.addEventListener('click', async (e) => {
      const button = e.target.closest('[data-action]');
      if (!button) return;
      const contact = c.contacts.find((x) => String(x.id) === button.dataset.id);
      if (button.dataset.action === 'new' || button.dataset.action === 'edit') {
        form.reset();
        form.dataset.id = contact ? contact.id : '';
        $('[data-form-title]', form).textContent = contact ? 'Editar contacto' : 'Nuevo contacto';
        if (contact) {
          // form.elements: form.name would return the form's own name attribute.
          ['name', 'email', 'phone', 'position'].forEach((k) => { form.elements[k].value = contact[k] || ''; });
          form.elements.is_primary.checked = contact.is_primary;
        }
        form.hidden = false;
        form.elements.email.focus();
      } else if (button.dataset.action === 'cancel') {
        form.hidden = true;
      } else if (button.dataset.action === 'delete' && confirm(`¿Borrar el contacto ${contact.email}?`)) {
        if (await run(button, () => api(`contacts/${contact.id}/`, { method: 'DELETE' }).then(() => true), 'Contacto borrado.')) {
          await reloadCompany();
          renderContacts(el);
        }
      }
    });
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const data = { ...formObject(form), is_primary: form.elements.is_primary.checked, company: c.id };
      const id = form.dataset.id;
      const saved = await run($('button', form), () => api(id ? `contacts/${id}/` : 'contacts/', { method: id ? 'PATCH' : 'POST', json: data }), 'Contacto guardado.');
      if (saved) {
        await reloadCompany();
        renderContacts(el);
      }
    });
  }

  // ---------- tab: Personas que asistirán al evento (both roles) ----------

  const ATTENDEE_FIELDS = [
    ['first_name', 'Nombre', { required: true }],
    ['last_name', 'Apellidos', { required: true }],
    ['dni', 'DNI', { required: true }],
    ['position', 'Cargo', {}],
    ['email', 'Email', { type: 'email' }],
    ['phone', 'Teléfono', { type: 'tel' }],
  ];

  async function renderAttendees(root) {
    const companyId = state.company.id;
    root.innerHTML = `
      <div class="space-y-6">
          <section class="card p-5">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-2xl">Equipo que acudirá al stand</h2>
              <button type="button" class="btn btn-accent btn-sm" data-action="new">+ Añadir persona</button>
            </div>
            <div class="overflow-x-auto mt-4" id="attendee-list"></div>
          </section>
          <form class="card p-5 space-y-4" id="attendee-form" hidden>
            <h2 class="text-2xl" data-form-title>Nueva persona</h2>
            <div class="grid gap-4 sm:grid-cols-2">
              ${ATTENDEE_FIELDS.map(([name, label, opts]) => field(label, name, '', opts)).join('')}
            </div>
            ${field('Alergias / necesidades de catering', 'dietary_needs', '', { attrs: 'placeholder="Ej.: celíaca, vegetariano, alergia a frutos secos"' })}
            <div class="flex gap-2"><button class="btn btn-primary">Guardar</button><button type="button" class="btn btn-ghost" data-action="cancel">Cancelar</button></div>
          </form>
      </div>`;

    const list = $('#attendee-list', root);
    const form = $('#attendee-form', root);
    let attendees = [];

    async function load(force = false) {
      if (!force && !form.hidden) return; // polling must not re-render under someone editing
      attendees = await api(`attendees/?company=${companyId}`);
      list.innerHTML = attendees.length ? `
        <table class="data-table">
          <thead><tr><th>Nombre</th><th>DNI</th><th>Cargo</th><th>Contacto</th><th>Catering</th><th></th></tr></thead>
          <tbody>${attendees.map((a) => `
            <tr>
              <td class="font-semibold">${esc(a.first_name)} ${esc(a.last_name)}</td>
              <td>${esc(a.dni)}</td>
              <td>${esc(a.position)}</td>
              <td class="text-sm break-all">${esc(a.email)}${a.phone ? `<br>${esc(a.phone)}` : ''}</td>
              <td class="text-sm">${a.dietary_needs ? `<span class="badge badge-invited">${esc(a.dietary_needs)}</span>` : '—'}</td>
              <td class="whitespace-nowrap text-right">
                <button type="button" class="btn btn-ghost btn-sm" data-action="edit" data-id="${a.id}">Editar</button>
                <button type="button" class="btn btn-ghost btn-sm text-rojo" data-action="delete" data-id="${a.id}">Borrar</button>
              </td>
            </tr>`).join('')}</tbody>
        </table>
        <p class="text-sm text-gray-600 mt-3">${attendees.length} persona(s) registrada(s).</p>`
        : '<p class="text-gray-500">Todavía no hay personas registradas.</p>';
    }

    root.addEventListener('click', async (e) => {
      const button = e.target.closest('[data-action]');
      if (!button) return;
      const attendee = attendees.find((a) => String(a.id) === button.dataset.id);
      if (button.dataset.action === 'new' || button.dataset.action === 'edit') {
        form.reset();
        form.dataset.id = attendee ? attendee.id : '';
        $('[data-form-title]', form).textContent = attendee ? 'Editar persona' : 'Nueva persona';
        if (attendee) [...ATTENDEE_FIELDS.map(([n]) => n), 'dietary_needs'].forEach((n) => { form.elements[n].value = attendee[n] || ''; });
        form.hidden = false;
        form.elements.first_name.focus();
      } else if (button.dataset.action === 'cancel') {
        form.hidden = true;
      } else if (button.dataset.action === 'delete' && confirm(`¿Eliminar a ${attendee.first_name} ${attendee.last_name}?`)) {
        if (await run(button, () => api(`attendees/${attendee.id}/`, { method: 'DELETE' }).then(() => true), 'Persona eliminada.')) load(true);
      }
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = form.dataset.id;
      const saved = await run($('button', form), () => api(id ? `attendees/${id}/` : 'attendees/', {
        method: id ? 'PATCH' : 'POST',
        json: { ...formObject(form), company: companyId },
      }), 'Persona guardada.');
      if (saved) {
        form.hidden = true;
        load();
      }
    });

    await load(true);
    state.refreshers.push(() => load());
  }

  // ---------- tab: Dossier y Stand (both roles) ----------

  // [field, label, accepted extensions, short description, example links [[label, url], ...]]
  const STATIC = (path) => `/static/${path}`;
  const MATERIAL_GROUPS = [
    {
      title: 'Material corporativo: catálogo',
      intro: 'Material para el catálogo de empresas participantes y la web del encuentro.',
      files: [
        ['logo', 'Logotipo', '.png,.svg,.jpg,.jpeg,.webp',
          'Logotipo de la empresa, preferiblemente con fondo transparente.'],
        ['dossier', 'Dossier corporativo (PDF/DOC)', '.pdf,.doc,.docx',
          'Presentación de la empresa: actividad, perfiles que buscáis, ofertas de empleo y prácticas.'],
        ['advert', 'Anuncio', '.pdf,.png,.jpg,.jpeg,.webp,.svg',
          'Anuncio de la empresa para el catálogo del encuentro (PDF o imagen).'],
      ],
    },
    {
      title: 'Material corporativo: stand',
      intro: 'Stand modular blanco de 3 × 2 m y 2,5 m de alto, en la planta baja de la Escuela.',
      files: [
        ['banner', 'Platabanda', '.png,.jpg,.jpeg,.webp,.svg,.pdf',
          'Franja superior del frontal del stand (2,93 × 0,40 m; zona de rótulo de unos 2,79 × 0,26 m), donde va el rótulo de la empresa en vinilo adhesivo negro (máx. 15 caracteres). Sube el diseño o el texto tal como debe aparecer.',
          [['Ejemplo de platabanda en un stand', STATIC('img/expositores/stand01.jpg')],
            ['Medidas del stand', STATIC('img/expositores/stand-medidas.svg')]]],
      ],
    },
  ];

  async function renderDossier(root) {
    const c = state.company;
    const doc = await api(`companies/${c.id}/documentation/`);

    const fileRow = ([name, label, accept, help, examples = []]) => {
      const url = doc[name];
      const preview = url && name === 'logo' ? `<div class="logo-tile border border-gray-200 rounded-lg mt-2 w-48"><img src="${esc(url)}" alt="Logotipo"></div>` : '';
      // Only files the organizers uploaded for the company carry a confirmation step.
      const fromOrganizer = url && doc[`${name}_by_organizer`];
      const confirmedAt = doc[`${name}_confirmed_at`];
      let status = '';
      if (fromOrganizer && isOrganizer) {
        status = confirmedAt
          ? `<p class="text-sm mt-2 text-green-700">✔ Confirmado por la empresa el ${esc(fmtDateTime(confirmedAt))}</p>`
          : '<p class="text-sm mt-2 text-amber-700">Subido por la organización · pendiente de confirmación por la empresa</p>';
      } else if (fromOrganizer) {
        status = `
          <p class="text-sm mt-2 text-gray-600">Este archivo lo ha subido la organización del ESIEM. Puedes reemplazarlo por otro o confirmar que es el que queréis usar.</p>
          <label class="flex items-start gap-2 mt-2 text-sm font-semibold cursor-pointer">
            <input type="checkbox" data-confirm="${name}" class="mt-0.5" ${confirmedAt ? 'checked' : ''}>
            <span>Confirmo que este es el archivo que queremos usar${confirmedAt ? ` <span class="font-normal text-gray-500">(${esc(fmtDateTime(confirmedAt))})</span>` : ''}</span>
          </label>`;
      } else if (url && isOrganizer) {
        status = '<p class="text-sm mt-2 text-gray-500">Subido por la empresa</p>';
      }
      return `
        <form class="border border-gray-200 rounded-lg p-4" data-file="${name}">
          <p class="font-semibold">${esc(label)}</p>
          ${help ? `<p class="text-sm text-gray-600 mt-1">${esc(help)}</p>` : ''}
          ${examples.length ? `<p class="text-sm mt-1">${examples.map(([text, href]) => `<a class="text-azul hover:underline cursor-zoom-in" href="${esc(href)}" target="_blank" rel="noopener" data-lightbox="${esc(href)}" data-caption="${esc(text)}">🖼 ${esc(text)}</a>`).join(' · ')}</p>` : ''}
          <p class="text-sm mt-2">${url ? `<a class="text-azul hover:underline break-all" href="${esc(url)}" target="_blank" rel="noopener">${esc(fileName(url))}</a> · <a class="text-azul hover:underline" href="${esc(url)}" download>Descargar</a>` : '<span class="text-gray-500">Sin archivo</span>'}</p>
          ${preview}
          ${status}
          <div class="flex flex-col sm:flex-row gap-2 mt-3 sm:items-center">
            <label class="file-picker flex-1">
              <input type="file" name="${name}" accept="${accept}" required>
              <span class="file-picker-btn">📎 Seleccionar archivo</span>
              <span class="file-picker-name">Ningún archivo seleccionado</span>
            </label>
            <button class="btn btn-primary btn-sm">${url ? 'Reemplazar' : 'Subir'}</button>
          </div>
        </form>`;
    };

    root.innerHTML = `
      <div class="max-w-3xl space-y-6">
        ${isOrganizer ? `
          <div class="flex flex-wrap items-center justify-between gap-3">
            <p class="text-sm text-gray-600">Descarga en un ZIP todos los archivos que ha subido ${esc(c.name)}.</p>
            <a class="btn btn-primary btn-sm" href="${esc(config.apiRoot)}companies/${c.id}/materials-zip/" download>⬇ Descargar todo (ZIP)</a>
          </div>` : ''}
        ${MATERIAL_GROUPS.map((group) => `
          <section class="card p-5 space-y-4">
            <div>
              <h2 class="text-2xl">${esc(group.title)}</h2>
              <p class="text-sm text-gray-600 mt-1">${esc(group.intro)}</p>
            </div>
            ${group.files.map(fileRow).join('')}
          </section>`).join('')}
      </div>`;

    root.querySelectorAll('[data-file]').forEach((form) => {
      const input = $('input[type=file]', form);
      input.addEventListener('change', () => {
        const picked = input.files[0];
        const nameEl = $('.file-picker-name', form);
        nameEl.textContent = picked ? picked.name : 'Ningún archivo seleccionado';
        nameEl.classList.toggle('has-file', Boolean(picked));
      });
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const ok = await run($('button', form), () => api(`companies/${c.id}/documentation/`, { method: 'PATCH', form: new FormData(form) }), 'Archivo subido.');
        if (ok) showTab('dossier');
      });
    });

    root.querySelectorAll('[data-confirm]').forEach((box) => {
      box.addEventListener('change', async () => {
        const name = box.dataset.confirm;
        const message = box.checked ? 'Archivo confirmado.' : 'Confirmación retirada.';
        const ok = await run(box, () => api(`companies/${c.id}/documentation/`, { method: 'PATCH', json: { [`${name}_confirmed`]: box.checked } }), message);
        if (ok) showTab('dossier');
        else box.checked = !box.checked;
      });
    });
  }

  const RENDERERS = { summary: renderSummary, general: renderGeneral, attendees: renderAttendees, dossier: renderDossier };

  // ---------- boot ----------

  $('#tabs').addEventListener('click', (e) => {
    const tab = e.target.closest('[data-tab]');
    if (tab) showTab(tab.dataset.tab);
  });

  // Changes made by the other side (admin <-> company) show up without reloading the page.
  setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    if (state.company) reloadCompany().catch(() => {});
    state.refreshers.forEach((fn) => fn().catch(() => {}));
  }, POLL_MS);

  if (isOrganizer) {
    setupOrganizerControls();
    $('#main-tabs').addEventListener('click', (e) => {
      const tab = e.target.closest('[data-view]');
      if (tab) showView(tab.dataset.view);
    });
    if (config.companyId) selectCompany(config.companyId);
    else showView(new URLSearchParams(location.search).get('vista') === 'registro' ? 'registro' : 'empresas');
  } else {
    selectCompany(config.companyId);
  }
})();
