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

  // Popup with Cancelar / Aceptar (the #confirm-dialog of panel.html). Resolves true on «Aceptar».
  // `messageHtml` must already be escaped.
  function askConfirmation(title, messageHtml) {
    const dialog = $('#confirm-dialog');
    $('[data-title]', dialog).textContent = title;
    $('[data-message]', dialog).innerHTML = messageHtml;
    dialog.returnValue = '';
    return new Promise((resolve) => {
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'accept'), { once: true });
      dialog.showModal();
      $('button[value="cancel"]', dialog).focus();
    });
  }

  // «Confirmar» of a section (attendees / materials): the company confirms it as final and can't
  // change it any more; organizers see when it was confirmed and can reopen it.
  const SECTION_TEXTS = {
    attendees: { what: 'las personas que asistirán al evento', button: 'Confirmar personas asistentes' },
    materials: { what: 'el dossier y el material del stand', button: 'Confirmar dossier y material' },
  };

  function sectionConfirmBar(section, company) {
    const confirmedAt = company[`${section}_confirmed_at`];
    const { what, button } = SECTION_TEXTS[section];
    if (confirmedAt) {
      return `
        <div class="rounded-lg border border-green-300 bg-green-50 p-4 flex flex-wrap items-center justify-between gap-3">
          <p class="text-sm text-green-800">✔ ${isOrganizer ? 'La empresa confirmó' : 'Confirmaste'} ${esc(what)} el ${esc(fmtDateTime(confirmedAt))}.
            ${isOrganizer ? 'La empresa ya no puede modificarlos; la organización sí.' : 'Ya no se pueden modificar. Si necesitas algún cambio, contacta con la organización.'}</p>
          ${isOrganizer ? '<button type="button" class="btn btn-ghost btn-sm" data-section-action="reopen">Reabrir para la empresa</button>' : ''}
        </div>`;
    }
    if (isOrganizer) return `<p class="text-sm text-gray-500">La empresa todavía no ha confirmado ${esc(what)}.</p>`;
    return `
      <div class="rounded-lg border border-gray-200 bg-gray-50 p-4 flex flex-wrap items-center justify-between gap-3">
        <p class="text-sm text-gray-700">Cuando hayas revisado que todo es correcto, confírmalo. Después ya no podrás modificarlo.</p>
        <button type="button" class="btn btn-primary btn-sm" data-section-action="confirm">${esc(button)}</button>
      </div>`;
  }

  // Wires the bar's buttons; `done` re-renders the tab after a change.
  function bindSectionConfirmBar(el, section, done) {
    el.addEventListener('click', async (e) => {
      const button = e.target.closest('[data-section-action]');
      if (!button) return;
      const { what } = SECTION_TEXTS[section];
      const reopen = button.dataset.sectionAction === 'reopen';
      const accepted = reopen
        ? await askConfirmation('Reabrir para la empresa', `<p>La empresa podrá volver a modificar ${esc(what)} y tendrá que confirmarlos de nuevo.</p>`)
        : await askConfirmation('Confirmar datos', `
            <p>Vas a confirmar que ${esc(what)} son correctos.</p>
            <p class="font-semibold text-rojo">Si pulsas «Aceptar», no podrás volver a modificarlos.</p>`);
      if (!accepted) return;
      const path = `companies/${state.company.id}/confirm-section/`;
      const updated = await run(button, () => (reopen
        ? api(`${path}?section=${section}`, { method: 'DELETE' })
        : api(path, { method: 'POST', json: { section } })), reopen ? 'Sección reabierta.' : 'Datos confirmados.');
      if (updated) {
        state.company = updated;
        renderHeader();
        done();
      }
    });
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
    $('#deadlines').hidden = true;
    history.replaceState(null, '', view === 'empresas' ? location.pathname : `?vista=${view}`);
    const VIEWS = { empresas: renderOverview, registro: renderRegistro, contactos: renderContactos };
    (VIEWS[view] || renderOverview)().catch((err) => toast(err.message, true));
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
    $('#deadlines').hidden = false; // «Fechas límite» box, above the company tabs
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
    $('#deadlines').hidden = true;
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
                ? `<span class="font-semibold text-green-700" title="${c.attendee_count} de ${esc(c.max_attendees)} asistente(s) registrados">✓ ${c.attendee_count}/${esc(c.max_attendees)}</span>`
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

  // ---------- view: Contactos (organizer) ----------

  // Contacts of every company, filtered by what each company has done, and one email to the
  // selected ones (api/mailing/). The filter is a list of rules «<campo> es / no es <valor>»
  // combined with «todas» (Y) or «alguna» (O). Each rule tests the company `c` or the contact `p`.
  const FILE_OPTIONS = [['done', 'Subido'], ['missing', 'Falta'], ['pending', 'Subido por la organización, sin confirmar']];
  const companyDone = (c) => Boolean(c.attendees_confirmed_at && c.materials_confirmed_at);
  const companyNothing = (c) => !c.attendee_count && ['logo', 'dossier', 'advert', 'banner'].every((f) => c[`${f}_state`] === 'missing');
  const FILTER_FIELDS = {
    status: { label: 'Estado de la empresa', options: () => config.statuses, test: (c, p, v) => c.status === v },
    sector: { label: 'Sector', options: () => config.sectors, test: (c, p, v) => c.sector === v },
    progress: {
      label: 'Progreso general',
      options: () => [['nothing', 'No ha hecho nada (ni asistentes ni archivos)'], ['partial', 'A medias'], ['done', 'Todo confirmado (asistentes y material)']],
      test: (c, p, v) => ({ nothing: companyNothing(c), done: companyDone(c), partial: !companyNothing(c) && !companyDone(c) })[v],
    },
    attendees: {
      label: 'Personas asistentes',
      options: () => [['none', 'Ninguna registrada'], ['some', 'Alguna registrada'], ['full', 'Cupo completo'],
        ['confirmed', 'Confirmadas por la empresa'], ['unconfirmed', 'Sin confirmar']],
      test: (c, p, v) => ({
        none: !c.attendee_count, some: c.attendee_count > 0, full: c.attendee_count >= c.max_attendees,
        confirmed: Boolean(c.attendees_confirmed_at), unconfirmed: !c.attendees_confirmed_at,
      })[v],
    },
    materials: {
      label: 'Dossier y material del stand',
      options: () => [['confirmed', 'Confirmado por la empresa'], ['unconfirmed', 'Sin confirmar'],
        ['complete', 'Todos los archivos subidos'], ['incomplete', 'Falta algún archivo']],
      test: (c, p, v) => {
        const complete = ['logo', 'dossier', 'advert', 'banner'].every((f) => c[`${f}_state`] !== 'missing');
        return ({ confirmed: Boolean(c.materials_confirmed_at), unconfirmed: !c.materials_confirmed_at, complete, incomplete: !complete })[v];
      },
    },
    logo: { label: 'Logotipo', options: () => FILE_OPTIONS, test: (c, p, v) => c.logo_state === v },
    dossier: { label: 'Dossier', options: () => FILE_OPTIONS, test: (c, p, v) => c.dossier_state === v },
    advert: { label: 'Anuncio', options: () => FILE_OPTIONS, test: (c, p, v) => c.advert_state === v },
    banner: { label: 'Platabanda', options: () => FILE_OPTIONS, test: (c, p, v) => c.banner_state === v },
    contact: {
      label: 'Tipo de contacto', options: () => [['primary', 'Contacto principal'], ['other', 'Otros contactos']],
      test: (c, p, v) => (v === 'primary') === Boolean(p.is_primary),
    },
  };
  const ACCEPTED = { field: 'status', negate: false, value: 'confirmed' };
  const FILTER_PRESETS = [
    ['Todos los contactos', []],
    ['No han hecho nada', [ACCEPTED, { field: 'progress', negate: false, value: 'nothing' }]],
    ['Asistentes sin confirmar', [ACCEPTED, { field: 'attendees', negate: false, value: 'unconfirmed' }]],
    ['Material sin confirmar', [ACCEPTED, { field: 'materials', negate: false, value: 'unconfirmed' }]],
    ['Les falta algún archivo', [ACCEPTED, { field: 'materials', negate: false, value: 'incomplete' }]],
    ['Falta el logotipo', [ACCEPTED, { field: 'logo', negate: false, value: 'missing' }]],
    ['Falta la platabanda', [ACCEPTED, { field: 'banner', negate: false, value: 'missing' }]],
    ['Pendientes de respuesta', [{ field: 'status', negate: false, value: 'interested' }]],
  ];
  const BULK_KINDS = [['summary', 'Seguimiento'], ['attendees', 'Solicitar lista de asistentes'], ['dossier', 'Solicitar materiales']];

  async function renderContactos() {
    $('#company-header').innerHTML = '';
    const panel = document.createElement('div');
    panel.innerHTML = '<p class="text-gray-500">Cargando…</p>';
    $('#tab-panel').replaceChildren(panel);
    if (!state.templates) state.templates = await api('email-templates/');
    let companies = await api('mailing/');

    const filter = { combine: 'all', search: '', rules: [] };
    const selected = new Set(); // contact ids
    let visible = []; // [{c, p}] after filtering
    let preview = null; // the reviewed message: {subject, body, recipients, companies: [{id, name, recipients}]}

    panel.innerHTML = `
      <div class="space-y-6">
        <section class="card p-5 space-y-4">
          <div>
            <h2 class="text-2xl">Contactos de las empresas</h2>
            <p class="text-sm text-gray-600 mt-1">Filtra por lo que ha hecho cada empresa, marca los contactos y envíales un correo. Queda registrado en la Bitácora de cada empresa.</p>
          </div>
          <div class="flex flex-wrap gap-2" data-presets>
            <span class="text-sm font-semibold text-gray-600 self-center">Filtros rápidos:</span>
            ${FILTER_PRESETS.map(([label], i) => `<button type="button" class="btn btn-ghost btn-sm" data-preset="${i}">${esc(label)}</button>`).join('')}
          </div>
          <div class="rounded-lg border border-gray-200 p-4 space-y-3">
            <div class="flex flex-wrap items-center gap-2 text-sm">
              <span>Mostrar los contactos que cumplan</span>
              <select data-combine class="input !w-auto !py-1">${options([['all', 'todas las condiciones (Y)'], ['any', 'alguna condición (O)']], 'all')}</select>
            </div>
            <div class="space-y-2" data-rules></div>
            <div class="flex flex-wrap items-center gap-3">
              <button type="button" class="btn btn-ghost btn-sm" data-add-rule>+ Añadir condición</button>
              <input type="search" data-search class="input sm:!w-80" placeholder="Buscar por empresa, nombre o email…">
            </div>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <p class="text-sm" data-count></p>
            <div class="flex gap-2">
              <button type="button" class="btn btn-ghost btn-sm" data-select="all">Seleccionar todos</button>
              <button type="button" class="btn btn-ghost btn-sm" data-select="none">Quitar selección</button>
            </div>
          </div>
          <div class="overflow-x-auto" data-list></div>
        </section>

        <form class="card p-5 space-y-4" data-composer>
          <h2 class="text-2xl">Enviar correo a los contactos seleccionados</h2>
          <p class="text-sm" data-recipients-summary></p>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="field"><label for="bulk-kind">Tipo de correo</label>
              <select id="bulk-kind" name="kind">${options(BULK_KINDS, 'summary')}</select>
              <span class="field-help">La aceptación y el rechazo se envían desde la ficha de cada empresa.</span></div>
            <div class="field"><label for="bulk-template">Plantilla (.txt)</label>
              <select id="bulk-template" name="template">${state.templates.templates.map((t) => `<option${t === state.templates.defaults.summary ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select></div>
          </div>
          <div class="field"><label for="bulk-subject">Asunto</label><input id="bulk-subject" name="subject" required></div>
          <div class="field"><label for="bulk-body">Mensaje</label><textarea id="bulk-body" name="body" rows="14" required class="font-mono text-sm"></textarea>
            <span class="field-help">Se envía <strong>un único correo con todos los destinatarios en copia oculta (CCO)</strong>: nadie ve a quién más se ha enviado. Por eso el texto es el mismo para todas las empresas: los datos de cada empresa de la plantilla (nombre, contacto, stand, máximo de asistentes) se cambian por un texto general que puedes retocar.</span></div>
          <button type="submit" class="btn btn-primary">Revisar el envío</button>
          <div data-preview hidden></div>
        </form>
      </div>`;

    const $p = (sel) => $(sel, panel);
    const form = $p('[data-composer]');

    // ----- filter -----
    function ruleRow(rule, i) {
      const field = FILTER_FIELDS[rule.field];
      return `
        <div class="flex flex-wrap items-center gap-2" data-rule="${i}">
          <select data-part="field" class="input !w-auto !py-1">${options(Object.entries(FILTER_FIELDS).map(([k, f]) => [k, f.label]), rule.field)}</select>
          <select data-part="negate" class="input !w-auto !py-1">${options([['no', 'es'], ['yes', 'no es']], rule.negate ? 'yes' : 'no')}</select>
          <select data-part="value" class="input !w-auto !py-1 max-w-full">${options(field.options(), rule.value)}</select>
          <button type="button" class="btn btn-ghost btn-sm text-rojo" data-remove-rule="${i}" aria-label="Quitar condición">✕</button>
        </div>`;
    }
    function renderRules() {
      $p('[data-rules]').innerHTML = filter.rules.length
        ? filter.rules.map(ruleRow).join('')
        : '<p class="text-sm text-gray-500">Sin condiciones: se muestran todos los contactos.</p>';
      $p('[data-combine]').value = filter.combine;
    }
    function matches(c, p) {
      const q = filter.search.trim().toLowerCase();
      if (q && ![c.name, p.name, p.email].some((x) => (x || '').toLowerCase().includes(q))) return false;
      if (!filter.rules.length) return true;
      const results = filter.rules.map((r) => Boolean(FILTER_FIELDS[r.field].test(c, p, r.value)) !== r.negate);
      return filter.combine === 'all' ? results.every(Boolean) : results.some(Boolean);
    }

    // ----- list -----
    const STATE_ICON = { done: ['✓', 'text-green-700'], pending: ['…', 'text-amber-700'], missing: ['✗', 'text-rojo'] };
    const fileBadges = (c) => [['logo', 'Logo'], ['dossier', 'Dossier'], ['advert', 'Anuncio'], ['banner', 'Platabanda']]
      .map(([f, label]) => {
        const [icon, cls] = STATE_ICON[c[`${f}_state`]] || STATE_ICON.missing;
        return `<span class="whitespace-nowrap ${cls}" title="${esc(label)}">${icon} ${esc(label)}</span>`;
      }).join(' · ');

    function renderList() {
      visible = [];
      companies.forEach((c) => c.contacts.forEach((p) => { if (matches(c, p)) visible.push({ c, p }); }));
      const visibleIds = new Set(visible.map(({ p }) => p.id));
      [...selected].forEach((id) => { if (!visibleIds.has(id)) selected.delete(id); }); // only filtered contacts are sent to
      const allChecked = visible.length > 0 && visible.every(({ p }) => selected.has(p.id));
      $p('[data-list]').innerHTML = visible.length ? `
        <table class="data-table">
          <thead><tr>
            <th><input type="checkbox" data-check-all ${allChecked ? 'checked' : ''} aria-label="Seleccionar todos los contactos filtrados"></th>
            <th>Empresa</th><th>Contacto</th><th>Email</th><th>Asistentes</th><th>Material</th>
          </tr></thead>
          <tbody>${visible.map(({ c, p }) => `
            <tr>
              <td><input type="checkbox" data-check="${p.id}" ${selected.has(p.id) ? 'checked' : ''} aria-label="Seleccionar a ${esc(p.name || p.email)}"></td>
              <td><button type="button" class="font-semibold text-azul hover:underline text-left" data-open-company="${c.id}">${esc(c.name)}</button>
                <br><span class="badge badge-${esc(c.status)}">${esc(c.status_display)}</span></td>
              <td>${esc(p.name || '—')}${p.is_primary ? ' <span class="text-xs text-oro font-semibold">★ principal</span>' : ''}${p.position ? `<br><span class="text-xs text-gray-500">${esc(p.position)}</span>` : ''}</td>
              <td class="text-sm break-all">${esc(p.email)}</td>
              <td class="text-sm whitespace-nowrap">${c.attendee_count}/${esc(c.max_attendees)}${c.attendees_confirmed_at ? '<br><span class="text-green-700">✔ confirmadas</span>' : ''}</td>
              <td class="text-xs">${fileBadges(c)}${c.materials_confirmed_at ? '<br><span class="text-green-700 text-sm">✔ confirmado</span>' : ''}</td>
            </tr>`).join('')}</tbody>
        </table>` : '<p class="text-gray-500">Ningún contacto cumple el filtro.</p>';
      updateCounts();
    }

    function selectedByCompany() {
      const groups = new Map();
      visible.forEach(({ c, p }) => {
        if (!selected.has(p.id)) return;
        if (!groups.has(c.id)) groups.set(c.id, { company: c, contacts: [] });
        groups.get(c.id).contacts.push(p);
      });
      return groups;
    }
    function updateCounts() {
      const companiesShown = new Set(visible.map(({ c }) => c.id)).size;
      const groups = selectedByCompany();
      $p('[data-count]').innerHTML = `<strong>${visible.length}</strong> contacto(s) de ${companiesShown} empresa(s) · <strong>${selected.size}</strong> seleccionado(s)`;
      $p('[data-recipients-summary]').innerHTML = selected.size
        ? `Se enviará a <strong>${selected.size} contacto(s)</strong> de <strong>${groups.size} empresa(s)</strong>, un correo por empresa.`
        : '<span class="text-gray-500">Selecciona contactos en la lista de arriba.</span>';
      const all = $p('[data-check-all]');
      if (all) all.checked = visible.length > 0 && visible.every(({ p }) => selected.has(p.id));
      clearPreview();
    }

    function refresh() { renderRules(); renderList(); }

    panel.addEventListener('click', (e) => {
      const preset = e.target.closest('[data-preset]');
      if (preset) {
        filter.rules = FILTER_PRESETS[preset.dataset.preset][1].map((r) => ({ ...r }));
        filter.combine = 'all';
        refresh();
        return;
      }
      if (e.target.closest('[data-add-rule]')) {
        filter.rules.push({ field: 'status', negate: false, value: config.statuses[0][0] });
        refresh();
        return;
      }
      const remove = e.target.closest('[data-remove-rule]');
      if (remove) {
        filter.rules.splice(Number(remove.dataset.removeRule), 1);
        refresh();
        return;
      }
      const bulk = e.target.closest('[data-select]');
      if (bulk) {
        visible.forEach(({ p }) => (bulk.dataset.select === 'all' ? selected.add(p.id) : selected.delete(p.id)));
        renderList();
        return;
      }
      const open = e.target.closest('[data-open-company]');
      if (open) {
        markView('empresas');
        selectCompany(Number(open.dataset.openCompany));
      }
    });

    panel.addEventListener('change', (e) => {
      const row = e.target.closest('[data-rule]');
      if (row) {
        const rule = filter.rules[Number(row.dataset.rule)];
        const part = e.target.dataset.part;
        if (part === 'field') {
          rule.field = e.target.value;
          rule.value = FILTER_FIELDS[rule.field].options()[0][0];
        } else if (part === 'negate') {
          rule.negate = e.target.value === 'yes';
        } else {
          rule.value = e.target.value;
        }
        refresh();
      } else if (e.target.matches('[data-combine]')) {
        filter.combine = e.target.value;
        renderList();
      } else if (e.target.matches('[data-check-all]')) {
        visible.forEach(({ p }) => (e.target.checked ? selected.add(p.id) : selected.delete(p.id)));
        renderList();
      } else if (e.target.matches('[data-check]')) {
        const id = Number(e.target.dataset.check);
        if (e.target.checked) selected.add(id); else selected.delete(id);
        updateCounts();
      }
    });
    $p('[data-search]').addEventListener('input', (e) => {
      filter.search = e.target.value;
      renderList();
    });

    // ----- composer -----
    let dirty = false;
    async function loadTemplate() {
      if (dirty && !confirm('¿Reemplazar el texto editado por la plantilla seleccionada?')) return;
      const tpl = await run(null, () => api(`email-templates/general/?name=${encodeURIComponent(form.elements.template.value)}`));
      if (!tpl) return;
      if (tpl.credentials) {
        toast('Esa plantilla lleva el usuario y la contraseña del portal: envíala desde la ficha de cada empresa.', true);
        return;
      }
      form.elements.subject.value = tpl.subject;
      form.elements.body.value = tpl.body;
      dirty = false;
      clearPreview();
    }
    form.elements.template.addEventListener('change', loadTemplate);
    form.elements.kind.addEventListener('change', () => {
      const template = state.templates.defaults[form.elements.kind.value];
      if (template && form.elements.template.value !== template) {
        form.elements.template.value = template;
        loadTemplate();
      }
    });
    ['subject', 'body'].forEach((name) => form.elements[name].addEventListener('input', () => { dirty = true; clearPreview(); }));

    function draft(extra = {}) {
      const f = form.elements;
      return { contacts: [...selected], subject: f.subject.value, body: f.body.value, template: f.template.value, kind: f.kind.value, ...extra };
    }

    function clearPreview() {
      preview = null;
      const box = $p('[data-preview]');
      if (box) { box.hidden = true; box.innerHTML = ''; }
    }

    // «Revisar el envío»: the server returns the final text and the recipients. Then it's sent as a
    // single email with everyone in Bcc (automatic mode), or opened in the organizer's mail client
    // with everyone in Bcc and registered once sent (manual mode).
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!selected.size) { toast('Selecciona al menos un contacto.', true); return; }
      const message = await run(e.submitter, () => api('mailing/preview/', { method: 'POST', json: draft() }));
      if (!message) return;
      preview = message;
      const box = $p('[data-preview]');
      box.innerHTML = `
        <div class="rounded-lg border border-azul/30 bg-azul/5 p-4 space-y-3">
          <h3 class="text-xl">Revisión: un único correo a ${message.recipients.length} destinatario(s) en copia oculta</h3>
          <p class="text-sm">Nadie verá a quién más se ha enviado. Quedará registrado en la Bitácora de ${message.companies.length} empresa(s).</p>
          <details class="rounded border border-gray-200 bg-white p-3"><summary class="text-sm text-azul cursor-pointer">Destinatarios por empresa (${message.companies.length})</summary>
            <ul class="text-sm mt-2 space-y-1">${message.companies.map((c) => `<li><strong>${esc(c.name)}</strong> · ${esc(c.recipients.join(', '))}</li>`).join('')}</ul></details>
          <div class="rounded border border-gray-200 bg-white p-3">
            <p class="text-sm"><strong>Asunto:</strong> ${esc(message.subject)}</p>
            <pre class="whitespace-pre-wrap text-sm font-mono mt-2">${esc(message.body)}</pre>
          </div>
          ${config.automaticEmail ? `
            <div class="flex flex-wrap gap-2">
              <button type="button" class="btn btn-primary" data-send>Enviar el correo (CCO)</button>
              <button type="button" class="btn btn-ghost" data-cancel-preview>Volver a editar</button>
            </div>` : `
            <p class="text-sm">El envío automático está desactivado: ábrelo en tu correo con todos en copia oculta, envíalo y después regístralo aquí. Si el campo CCO no aparece relleno (con muchos destinatarios algunos programas lo cortan), usa «Copiar destinatarios» y pégalos en CCO.</p>
            <div class="flex flex-wrap gap-2">
              <button type="button" class="btn btn-primary" data-open="web">Abrir en Outlook (web)</button>
              <button type="button" class="btn btn-ghost" data-open="app">Abrir en la app de correo</button>
              <button type="button" class="btn btn-ghost" data-copy-bcc>Copiar destinatarios</button>
              <button type="button" class="btn btn-ghost" data-cancel-preview>Volver a editar</button>
            </div>
            <div data-pending hidden class="rounded-lg border border-oro bg-amber-50 p-4 text-sm">
              <p>Cuando lo hayas enviado desde tu correo, regístralo para que conste en la Bitácora de cada empresa.</p>
              <button type="button" class="btn btn-primary btn-sm mt-3" data-register>Ya lo he enviado: registrar</button>
            </div>`}
        </div>`;
      box.hidden = false;
      box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    async function finish(button, json) {
      const result = await run(button, () => api('mailing/send/', { method: 'POST', json }));
      if (!result) return;
      toast(`Correo ${json.manual ? 'registrado' : 'enviado'}: ${result.recipients} destinatario(s) de ${result.companies} empresa(s), anotado en la Bitácora de cada una.`);
      dirty = false;
      selected.clear();
      companies = await api('mailing/');
      renderList();
    }

    $p('[data-preview]').addEventListener('click', async (e) => {
      if (!preview) return;
      const target = e.target.closest('button');
      if (!target) return;
      if (target.matches('[data-cancel-preview]')) {
        clearPreview();
      } else if (target.matches('[data-open]')) {
        const how = target.dataset.open;
        if (how === 'web') window.open(composeUrl.webBcc(preview), '_blank', 'noopener');
        else window.location.href = composeUrl.bcc(preview);
        $p('[data-pending]').hidden = false;
      } else if (target.matches('[data-copy-bcc]')) {
        try {
          await navigator.clipboard.writeText(preview.recipients.join('; '));
          toast('Destinatarios copiados. Pégalos en el campo CCO.');
        } catch {
          toast('No se ha podido copiar al portapapeles.', true);
        }
      } else if (target.matches('[data-send]')) {
        const ok = await askConfirmation('Enviar correo', `<p>Se enviará <strong>un único correo</strong> a ${preview.recipients.length} destinatario(s) en copia oculta y quedará en la Bitácora de ${preview.companies.length} empresa(s).</p>`);
        if (ok) await finish(target, draft());
      } else if (target.matches('[data-register]')) {
        const ok = await askConfirmation('Registrar envío', `<p>Se registrará el correo en la Bitácora de <strong>${preview.companies.length} empresa(s)</strong> como enviado desde tu correo.</p>`);
        if (ok) await finish(target, draft({ manual: true }));
      }
    });

    refresh();
    await loadTemplate();
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

  // Outlook on the web (the US mailboxes live in Microsoft 365) or the default mail app.
  // `bcc`: one message to several companies without showing their addresses to each other.
  const composeUrl = {
    web: (m) => 'https://outlook.office.com/mail/deeplink/compose?' + new URLSearchParams(
      { to: m.recipients.join(','), subject: m.subject, body: m.body }).toString().replace(/\+/g, '%20'),
    app: (m) => `mailto:${m.recipients.map(encodeURIComponent).join(',')}?subject=${encodeURIComponent(m.subject)}&body=${encodeURIComponent(m.body)}`,
    webBcc: (m) => 'https://outlook.office.com/mail/deeplink/compose?' + new URLSearchParams(
      { bcc: m.recipients.join(','), subject: m.subject, body: m.body }).toString().replace(/\+/g, '%20'),
    bcc: (m) => `mailto:?bcc=${m.recipients.map(encodeURIComponent).join(',')}&subject=${encodeURIComponent(m.subject)}&body=${encodeURIComponent(m.body)}`,
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

  // Companies can fix everything they sent in the participation form (CompanyPortalSerializer),
  // including the designated contact; status, stand and public summary are the organizers'.
  function companyDataForm(c) {
    return `
      <form id="company-form" class="card p-5 space-y-4">
        <h2 class="text-2xl">Datos generales</h2>
        ${isOrganizer ? '' : '<p class="text-sm text-gray-600">Revisa y, si hace falta, corrige los datos de tu empresa.</p>'}
        <div class="grid gap-4 sm:grid-cols-2">
          ${field('Nombre', 'name', c.name, { required: true })}
          ${field('CIF', 'cif', c.cif, { required: !isOrganizer })}
          ${selectField('Sector', 'sector', config.sectors, c.sector)}
          ${isOrganizer ? selectField('Estado', 'status', config.statuses, c.status) : ''}
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
          ${field('Calidad en la que firma', 'signer_capacity', c.signer_capacity)}
        </div>
        ${isOrganizer ? '' : `
        <h3 class="text-xl pt-2">Persona de contacto</h3>
        <p class="text-sm text-gray-600">Recibe los correos de la organización.</p>
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="sm:col-span-2">${field('Nombre', 'contact_name', c.contact_name, { required: true })}</div>
          ${field('Email', 'contact_email', c.contact_email, { type: 'email', required: true })}
          ${field('Teléfono', 'contact_phone', c.contact_phone)}
        </div>`}
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

  const ATTENDEE_ROLES = [['stand', 'Stand'], ['speaker', 'Ponente'], ['both', 'Stand y ponente']];
  const YES_NO = [['', '— Selecciona —'], ['false', 'No'], ['true', 'Sí']];

  async function renderAttendees(root) {
    const companyId = state.company.id;
    root.innerHTML = `
      <div class="space-y-6">
          <section class="card p-5">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <h2 class="text-2xl">Equipo que asistirá al evento</h2>
              <button type="button" class="btn btn-accent btn-sm" data-action="new">+ Añadir persona</button>
            </div>
            <p class="text-sm text-gray-600 mt-2" data-limit></p>
            <div class="overflow-x-auto mt-4" id="attendee-list"></div>
            <div class="mt-4" data-confirm-bar></div>
          </section>
          <form class="card p-5 space-y-4" id="attendee-form" hidden>
            <h2 class="text-2xl" data-form-title>Nueva persona</h2>
            <div class="grid gap-4 sm:grid-cols-2">
              ${ATTENDEE_FIELDS.map(([name, label, opts]) => field(label, name, '', opts)).join('')}
              ${selectField('Participación', 'role', ATTENDEE_ROLES, 'stand', 'required')}
            </div>
            <div class="grid gap-4 sm:grid-cols-2">
              ${selectField('¿Comerá en el evento?', 'eats_at_event', YES_NO, '', 'required')}
              <div data-when="eats">${selectField('¿Tiene alergias?', 'has_allergies', YES_NO, '', 'required')}</div>
            </div>
            <div data-when="allergies">${textareaField('Especifica las alergias', 'allergies', '', 2)}</div>
            <div class="flex gap-2"><button class="btn btn-primary">Guardar</button><button type="button" class="btn btn-ghost" data-action="cancel">Cancelar</button></div>
          </form>
      </div>`;

    const list = $('#attendee-list', root);
    const form = $('#attendee-form', root);
    const newButton = $('[data-action="new"]', root);
    const confirmBar = $('[data-confirm-bar]', root);
    let attendees = [];
    bindSectionConfirmBar(confirmBar, 'attendees', () => load(true));

    // Show «¿Tiene alergias?» only if they eat, and the text only if they have allergies.
    // Hidden controls are also disabled, so their `required` doesn't block the submit.
    function syncCatering() {
      const eats = form.elements.eats_at_event.value === 'true';
      const allergic = eats && form.elements.has_allergies.value === 'true';
      [['eats', eats, 'has_allergies'], ['allergies', allergic, 'allergies']].forEach(([key, show, name]) => {
        $(`[data-when="${key}"]`, form).hidden = !show;
        form.elements[name].disabled = !show;
      });
      form.elements.allergies.required = allergic;
    }
    form.elements.eats_at_event.addEventListener('change', syncCatering);
    form.elements.has_allergies.addEventListener('change', syncCatering);

    const roleLabel = (role) => (ATTENDEE_ROLES.find(([v]) => v === role) || [, role])[1];
    const cateringCell = (a) => {
      if (!a.eats_at_event) return '<span class="text-gray-500">No come</span>';
      if (!a.has_allergies) return 'Come · sin alergias';
      return `Come · <span class="badge badge-invited">Alergias: ${esc(a.allergies)}</span>`;
    };

    async function load(force = false) {
      if (!force && !form.hidden) return; // polling must not re-render under someone editing
      // The limit can be changed in the DB at any time: read it fresh along with the list.
      const [company, rows] = await Promise.all([api(`companies/${companyId}/`), api(`attendees/?company=${companyId}`)]);
      attendees = rows;
      state.company = company;
      // Confirmed by the company: read-only for it (organizers can still edit).
      const locked = !isOrganizer && Boolean(company.attendees_confirmed_at);
      const max = company.max_attendees;
      const full = attendees.length >= max;
      newButton.hidden = locked;
      newButton.disabled = full;
      newButton.title = full ? 'Se ha alcanzado el máximo de personas' : '';
      $('[data-limit]', root).innerHTML = `Cada empresa puede registrar como máximo <strong>${esc(max)} personas</strong>.
        ${full && !locked ? '<span class="text-rojo font-semibold">Has alcanzado el máximo: para añadir otra persona, borra una de la lista.</span>' : ''}`;
      confirmBar.innerHTML = attendees.length || company.attendees_confirmed_at ? sectionConfirmBar('attendees', company) : '';
      list.innerHTML = attendees.length ? `
        <table class="data-table">
          <thead><tr><th>Nombre</th><th>DNI</th><th>Cargo</th><th>Contacto</th><th>Participación</th><th>Comida</th><th></th></tr></thead>
          <tbody>${attendees.map((a) => `
            <tr>
              <td class="font-semibold">${esc(a.first_name)} ${esc(a.last_name)}</td>
              <td>${esc(a.dni)}</td>
              <td>${esc(a.position)}</td>
              <td class="text-sm break-all">${esc(a.email)}${a.phone ? `<br>${esc(a.phone)}` : ''}</td>
              <td class="text-sm">${esc(roleLabel(a.role))}</td>
              <td class="text-sm">${cateringCell(a)}</td>
              <td class="whitespace-nowrap text-right">${locked ? '' : `
                <button type="button" class="btn btn-ghost btn-sm" data-action="edit" data-id="${a.id}">Editar</button>
                <button type="button" class="btn btn-ghost btn-sm text-rojo" data-action="delete" data-id="${a.id}">Borrar</button>`}
              </td>
            </tr>`).join('')}</tbody>
        </table>
        <p class="text-sm text-gray-600 mt-3">${attendees.length} de ${esc(max)} persona(s) registrada(s).</p>`
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
        if (attendee) {
          [...ATTENDEE_FIELDS.map(([n]) => n), 'role', 'allergies'].forEach((n) => { form.elements[n].value = attendee[n] || ''; });
          form.elements.eats_at_event.value = String(attendee.eats_at_event);
          form.elements.has_allergies.value = attendee.eats_at_event ? String(attendee.has_allergies) : '';
        }
        syncCatering();
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
    const [c, doc] = await Promise.all([api(`companies/${state.company.id}/`), api(`companies/${state.company.id}/documentation/`)]);
    state.company = c;
    // Confirmed by the company: read-only for it (organizers can still upload).
    const locked = !isOrganizer && Boolean(c.materials_confirmed_at);
    const hasFiles = MATERIAL_GROUPS.some((group) => group.files.some(([name]) => doc[name]));

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
      } else if (fromOrganizer && !locked) {
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
          ${locked ? '' : `<div class="flex flex-col sm:flex-row gap-2 mt-3 sm:items-center">
            <label class="file-picker flex-1">
              <input type="file" name="${name}" accept="${accept}" required>
              <span class="file-picker-btn">📎 Seleccionar archivo</span>
              <span class="file-picker-name">Ningún archivo seleccionado</span>
            </label>
            <button class="btn btn-primary btn-sm">${url ? 'Reemplazar' : 'Subir'}</button>
          </div>`}
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
        <div data-confirm-bar>${hasFiles || c.materials_confirmed_at ? sectionConfirmBar('materials', c) : ''}</div>
      </div>`;

    bindSectionConfirmBar($('[data-confirm-bar]', root), 'materials', () => showTab('dossier'));

    root.querySelectorAll('[data-file]').forEach((form) => {
      const input = $('input[type=file]', form);
      if (!input) return; // locked: no upload controls
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
    else {
      const vista = new URLSearchParams(location.search).get('vista');
      showView(['registro', 'contactos'].includes(vista) ? vista : 'empresas');
    }
  } else {
    selectCompany(config.companyId);
  }
})();
