// Sanctum Sanctorum — Members' Bookstore (vanilla ES module, no build step).
// All HTTP goes through `api()`, which normalises errors (incl. FastAPI 422 arrays
// and 501 "Not implemented") and surfaces them as non-blocking toasts.

/* =========================================================================
   Constants & small utilities
   ========================================================================= */

const TIERS = ['apprentice', 'adept', 'master', 'supreme'];
const TIER_DISCOUNT = { apprentice: 0, adept: 5, master: 10, supreme: 15 };
const TIER_LOAN_LIMIT = { apprentice: 1, adept: 3, master: 5, supreme: Infinity };
const VOLUME_DISCOUNT_QTY = 10;
const VOLUME_DISCOUNT_PERCENT = 5;
const LATE_FEE_PER_DAY_CENTS = 25;

const FIELD_LABELS = {
  title: 'Title', author: 'Author', isbn: 'ISBN', price_cents: 'Price', stock: 'Stock',
  restricted: 'Restricted', name: 'Name', email: 'Email', tier: 'Tier', member_id: 'Member',
  book_id: 'Book', items: 'Items', quantity: 'Quantity', q: 'Search', min_price: 'Min price',
  max_price: 'Max price', sort: 'Sort', limit: 'Limit', offset: 'Offset', status: 'Status',
};

const STORAGE_KEYS = { member: 'sanctum.memberId', cart: 'sanctum.cart' };

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

const moneyFmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const fmtMoney = (cents) => (Number.isFinite(cents) ? moneyFmt.format(cents / 100) : '—');

const dateFmt = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' });
const dayFmt = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeZone: 'UTC' });
function parseApiDate(iso) {
  if (!iso) return null;
  // API datetimes are naive UTC; make that explicit for the Date parser.
  const hasZone = /(Z|[+-]\d\d:?\d\d)$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}
function fmtDate(iso, { dateOnly = false } = {}) {
  const d = parseApiDate(iso);
  if (!d) return iso ? esc(iso) : '—';
  return dateOnly ? dayFmt.format(d) : `${dateFmt.format(d)} UTC`;
}

const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '');
const pluralize = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** "12.5" -> 1250. Returns null when the text is not a money amount. Empty -> undefined. */
function parseDollars(text) {
  const s = String(text ?? '').trim().replace(/^\$/, '').replace(/,/g, '');
  if (s === '') return undefined;
  const m = /^(-)?(\d*)(?:\.(\d{0,2}))?$/.exec(s);
  if (!m || (m[2] === '' && (m[3] === undefined || m[3] === ''))) return null;
  const cents = Number(m[2] || '0') * 100 + Number((m[3] || '').padEnd(2, '0') || '0');
  return m[1] ? -cents : cents;
}
const centsToInput = (cents) => (Number.isFinite(cents) ? (cents / 100).toFixed(2) : '');

function parseIntStrict(text) {
  const s = String(text ?? '').trim();
  if (s === '') return undefined;
  return /^-?\d+$/.test(s) ? Number(s) : null;
}

const store = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch { return fallback; }
  },
  set(key, value) {
    try {
      if (value === null || value === undefined) localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify(value));
    } catch { /* storage unavailable: state just won't persist */ }
  },
};

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function setBusy(button, busy) {
  if (!button) return;
  button.disabled = busy;
  if (busy) button.setAttribute('aria-busy', 'true');
  else button.removeAttribute('aria-busy');
}

/* =========================================================================
   Toasts (non-blocking notifications)
   ========================================================================= */

const recentToasts = new Map();

function toast({ type = 'info', title = '', message = '', items = [], timeout } = {}) {
  const key = `${type}|${title}|${message}|${items.join('|')}`;
  const now = Date.now();
  if (recentToasts.has(key) && now - recentToasts.get(key) < 4000) return; // de-duplicate bursts
  recentToasts.set(key, now);

  const region = $('#toasts');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `
    <div class="toast-body">
      ${title ? `<p class="toast-title">${esc(title)}</p>` : ''}
      ${message ? `<p class="toast-msg">${esc(message)}</p>` : ''}
      ${items.length ? `<ul class="toast-list">${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : ''}
    </div>
    <button type="button" class="toast-close" aria-label="Dismiss notification">&times;</button>`;

  const dismiss = () => {
    if (!el.isConnected) return;
    el.classList.add('leaving');
    setTimeout(() => el.remove(), 160);
  };
  el.querySelector('.toast-close').addEventListener('click', dismiss);

  const ms = timeout ?? (type === 'error' ? 9000 : type === 'warning' ? 7000 : 4500);
  let timer = setTimeout(dismiss, ms);
  const pause = () => clearTimeout(timer);
  const resume = () => { clearTimeout(timer); timer = setTimeout(dismiss, 2500); };
  el.addEventListener('mouseenter', pause);
  el.addEventListener('mouseleave', resume);
  el.addEventListener('focusin', pause);
  el.addEventListener('focusout', resume);

  region.appendChild(el);
  while (region.children.length > 5) region.firstElementChild.remove();
}

/* =========================================================================
   API helper
   ========================================================================= */

class ApiError extends Error {
  constructor(status, message, fields = [], body = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.fields = fields; // [{ field, msg }] for 422 validation errors
    this.body = body;
  }
}

function locToField(loc) {
  if (!Array.isArray(loc)) return '';
  const parts = loc.filter((p) => !['body', 'query', 'path', 'header'].includes(p));
  return parts.join('.');
}

function prettyField(field) {
  if (!field) return '';
  // items.0.quantity -> "Item 1 quantity"
  const m = /^items\.(\d+)\.(\w+)$/.exec(field);
  if (m) return `Item ${Number(m[1]) + 1} ${(FIELD_LABELS[m[2]] || m[2]).toLowerCase()}`;
  return FIELD_LABELS[field] || field;
}

const cleanMsg = (msg) => String(msg ?? '').replace(/^Value error,\s*/i, '');

function parseDetail(detail) {
  if (detail === undefined || detail === null) return { message: '', fields: [] };
  if (typeof detail === 'string') return { message: detail, fields: [] };
  if (Array.isArray(detail)) {
    const fields = detail.map((d) => (
      typeof d === 'object' && d !== null
        ? { field: locToField(d.loc), msg: cleanMsg(d.msg ?? JSON.stringify(d)) }
        : { field: '', msg: String(d) }
    ));
    const message = fields.map((f) => (f.field ? `${prettyField(f.field)}: ${f.msg}` : f.msg)).join('; ');
    return { message, fields };
  }
  if (typeof detail === 'object') return { message: detail.message || JSON.stringify(detail), fields: [] };
  return { message: String(detail), fields: [] };
}

/**
 * The single entry point for every HTTP call.
 * @param {string} path  relative path e.g. "/books"
 * @param {object} opts  { method, body, query, context, toast }
 *   context: short human label ("Adding book") used in error toasts.
 *   toast:   set false only for purely decorative lookups.
 */
async function api(path, { method = 'GET', body, query, context = '', toast: notify = true } = {}) {
  let url = path;
  if (query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== '') params.append(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  const init = { method, headers: { Accept: 'application/json' } };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(url, init);
  } catch {
    const err = new ApiError(0, 'Could not reach the server. Check that the API is running.');
    if (notify) notifyApiError(err, context);
    throw err;
  }

  let text = '';
  try { text = await res.text(); } catch { /* ignore */ }
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = null; }
  }

  if (!res.ok) {
    const parsed = parseDetail(data && typeof data === 'object' ? data.detail : undefined);
    const fallback = (!data && text && text.length < 300) ? text : (res.statusText || 'Unexpected error');
    const err = new ApiError(res.status, parsed.message || fallback, parsed.fields, data);
    if (notify) notifyApiError(err, context);
    throw err;
  }
  return data;
}

function notifyApiError(err, context) {
  const what = context || 'Request';
  if (err.status === 501) {
    toast({ type: 'warning', title: `${what}: not available yet (501)`, message: err.message });
  } else if (err.status === 422 && err.fields.length) {
    toast({
      type: 'error',
      title: `${what}: please check the input (422)`,
      items: err.fields.map((f) => (f.field ? `${prettyField(f.field)}: ${f.msg}` : f.msg)),
    });
  } else if (err.status === 0) {
    toast({ type: 'error', title: `${what}: network error`, message: err.message });
  } else {
    toast({ type: 'error', title: `${what} failed (${err.status})`, message: err.message });
  }
}

/** Inline message used in place of content when a load fails. */
function inlineErrorHTML(err, what = 'this data') {
  if (!(err instanceof ApiError)) {
    return `<div class="notice notice-error" role="status"><strong>Something went wrong.</strong> ${esc(err?.message || '')}</div>`;
  }
  if (err.status === 501) {
    return `<div class="notice notice-warning" role="status"><strong>This feature isn't available yet (501).</strong>
      <span>${esc(err.message)}</span></div>`;
  }
  if (err.status === 0) {
    return `<div class="notice notice-error" role="status"><strong>Can't reach the server.</strong> ${esc(err.message)}</div>`;
  }
  return `<div class="notice notice-error" role="status"><strong>Couldn't load ${esc(what)} (${err.status}).</strong>
    ${esc(err.message)}</div>`;
}

/* ---- form error helpers ---- */

function clearFormErrors(root) {
  $$('[aria-invalid="true"]', root).forEach((input) => {
    input.removeAttribute('aria-invalid');
    const ids = (input.getAttribute('aria-describedby') || '').split(' ').filter((id) => id && !id.endsWith('-error'));
    if (ids.length) input.setAttribute('aria-describedby', ids.join(' '));
    else input.removeAttribute('aria-describedby');
  });
  $$('.field-error', root).forEach((el) => el.remove());
  const summary = $('.form-errors', root);
  if (summary) { summary.hidden = true; summary.innerHTML = ''; }
}

function showFieldError(input, message) {
  input.setAttribute('aria-invalid', 'true');
  const id = `${input.id || input.name || 'field'}-error`;
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement('p');
    el.className = 'field-error';
    el.id = id;
    (input.closest('.field') || input.parentElement).appendChild(el);
  }
  el.textContent = message;
  const ids = new Set((input.getAttribute('aria-describedby') || '').split(' ').filter(Boolean));
  ids.add(id);
  input.setAttribute('aria-describedby', [...ids].join(' '));
}

function showFormSummary(form, html) {
  const summary = $('.form-errors', form);
  if (!summary) return;
  summary.innerHTML = html;
  summary.hidden = false;
}

/** Map an ApiError onto a form: 422 field messages next to inputs, anything else in the summary. */
function applyApiErrorToForm(form, err, { fieldMap = {} } = {}) {
  clearFormErrors(form);
  if (!(err instanceof ApiError)) { showFormSummary(form, esc(err?.message || 'Unexpected error')); return; }

  if (err.status === 422 && err.fields.length) {
    const unmatched = [];
    let firstInput = null;
    for (const f of err.fields) {
      const name = fieldMap[f.field] || f.field;
      const input = name ? form.querySelector(`[name="${CSS.escape(name)}"]`) : null;
      if (input) {
        showFieldError(input, f.msg);
        firstInput ??= input;
      } else {
        unmatched.push(f.field ? `${prettyField(f.field)}: ${f.msg}` : f.msg);
      }
    }
    if (unmatched.length) {
      showFormSummary(form, `<strong>Please fix the following:</strong><ul>${unmatched.map((m) => `<li>${esc(m)}</li>`).join('')}</ul>`);
    }
    firstInput?.focus();
    return;
  }
  if (err.status === 501) {
    showFormSummary(form, `<strong>This feature isn't available yet (501).</strong> ${esc(err.message)}`);
    return;
  }
  showFormSummary(form, `<strong>${err.status ? `Error ${err.status}:` : 'Error:'}</strong> ${esc(err.message)}`);
}

/* =========================================================================
   State
   ========================================================================= */

const state = {
  memberId: null,
  member: null,          // MemberOut or null when unknown/unverified
  stats: { data: null, error: null, loading: false },
  cart: [],              // [{ book_id, title, author, price_cents, stock, restricted, quantity }]
  books: new Map(),      // id -> BookOut | null (null = lookup failed)
  catalog: {
    q: '', restricted: '', min_price: '', max_price: '', sort: '', limit: 20, offset: 0,
    items: [], total: 0, error: null, seq: 0, loaded: false,
  },
  editingBookId: null,
  orders: { items: [], error: null, loading: false, seq: 0 },
  orderDetail: null,     // { order, heading }
  loans: { items: [], error: null, loading: false, seq: 0 },
  reports: { seq: 0 },
  activeTab: 'catalog',
};

/* =========================================================================
   Books cache (for titles in orders / loans)
   ========================================================================= */

const pendingBookLookups = new Set();

function bookLabel(id) {
  const b = state.books.get(id);
  return b ? b.title : `Book #${id}`;
}

async function ensureBooks(ids, rerender) {
  const missing = [...new Set(ids)].filter((id) => !state.books.has(id) && !pendingBookLookups.has(id));
  if (!missing.length) return;
  missing.forEach((id) => pendingBookLookups.add(id));
  await Promise.all(missing.map((id) => api(`/books/${id}`, { toast: false })
    .then((b) => state.books.set(id, b))
    .catch(() => state.books.set(id, null))
    .finally(() => pendingBookLookups.delete(id))));
  rerender();
}

/* =========================================================================
   Header
   ========================================================================= */

function renderHeader() {
  const chip = $('#header-member');
  if (!state.memberId) {
    chip.textContent = 'Sign in as member';
    chip.title = 'Choose a member to act as';
  } else if (state.member) {
    chip.innerHTML = `${esc(state.member.name)} <span class="tier-dot">· ${esc(cap(state.member.tier))}</span>`;
    chip.title = `Acting as ${state.member.name} (#${state.member.id})`;
  } else {
    chip.textContent = `Member #${state.memberId}`;
    chip.title = `Acting as member #${state.memberId}`;
  }
  const count = state.cart.reduce((n, i) => n + i.quantity, 0);
  $('#cart-count').textContent = String(count);
  $('#cart-count').setAttribute('aria-label', pluralize(count, 'item'));
}

async function checkHealth() {
  const el = $('#api-status');
  try {
    const data = await api('/health', { toast: false });
    const ok = data?.status === 'ok';
    el.dataset.state = ok ? 'ok' : 'down';
    $('.label', el).textContent = ok ? 'API online' : 'API degraded';
  } catch (err) {
    el.dataset.state = 'down';
    $('.label', el).textContent = err.status === 0 ? 'API unreachable' : `API error (${err.status})`;
    if (err.status === 0) notifyApiError(err, 'Health check');
  }
}

/* =========================================================================
   Tabs
   ========================================================================= */

const TAB_IDS = ['catalog', 'members', 'cart', 'loans', 'reports'];
const loaders = {
  catalog: () => loadCatalog(),
  members: () => { renderMemberCard(); loadStats(); },
  cart: () => { renderCart(); renderOrderDetail(); loadOrders(); },
  loans: () => loadLoans(),
  reports: () => loadReports(),
};

function activateTab(id, { focus = false, updateHash = true } = {}) {
  if (!TAB_IDS.includes(id)) id = 'catalog';
  state.activeTab = id;
  for (const tabId of TAB_IDS) {
    const tab = $(`#tab-${tabId}`);
    const panel = $(`#panel-${tabId}`);
    const selected = tabId === id;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    panel.hidden = !selected;
  }
  if (focus) $(`#tab-${id}`).focus();
  if (updateHash && location.hash !== `#${id}`) history.replaceState(null, '', `#${id}`);
  loaders[id]?.();
}

function initTabs() {
  const tablist = $('.tabs');
  tablist.addEventListener('click', (e) => {
    const tab = e.target.closest('[role="tab"]');
    if (tab) activateTab(tab.dataset.tab);
  });
  tablist.addEventListener('keydown', (e) => {
    const idx = TAB_IDS.indexOf(state.activeTab);
    let next = null;
    if (e.key === 'ArrowRight') next = TAB_IDS[(idx + 1) % TAB_IDS.length];
    else if (e.key === 'ArrowLeft') next = TAB_IDS[(idx - 1 + TAB_IDS.length) % TAB_IDS.length];
    else if (e.key === 'Home') next = TAB_IDS[0];
    else if (e.key === 'End') next = TAB_IDS[TAB_IDS.length - 1];
    if (next) { e.preventDefault(); activateTab(next, { focus: true }); }
  });
  window.addEventListener('hashchange', () => {
    const id = location.hash.slice(1);
    if (TAB_IDS.includes(id) && id !== state.activeTab) activateTab(id, { updateHash: false });
  });
}

function requireMember(actionLabel) {
  if (state.memberId) return true;
  toast({
    type: 'info',
    title: 'Select a member first',
    message: `Sign in or create a member on the Members tab to ${actionLabel}.`,
  });
  return false;
}

/* =========================================================================
   Catalog
   ========================================================================= */

async function loadCatalog() {
  const c = state.catalog;
  const seq = ++c.seq;
  const table = $('#books-table');
  table.setAttribute('aria-busy', 'true');
  try {
    const data = await api('/books', {
      query: {
        q: c.q.trim(), restricted: c.restricted, min_price: c.min_price, max_price: c.max_price,
        sort: c.sort, limit: c.limit, offset: c.offset,
      },
      context: 'Loading catalog',
    });
    if (seq !== c.seq) return;
    c.items = Array.isArray(data?.items) ? data.items : [];
    c.total = Number.isFinite(data?.total) ? data.total : c.items.length;
    if (Number.isFinite(data?.offset)) c.offset = data.offset;
    c.items.forEach((b) => state.books.set(b.id, b));
    c.error = null;
    c.loaded = true;

    // Landed past the last page (e.g. after stock edits / filters): step back.
    if (!c.items.length && c.offset > 0 && c.total > 0) {
      c.offset = Math.max(0, (Math.ceil(c.total / c.limit) - 1) * c.limit);
      loadCatalog();
      return;
    }
  } catch (err) {
    if (seq !== c.seq) return;
    c.items = [];
    c.total = 0;
    c.error = err;
  } finally {
    if (seq === c.seq) table.removeAttribute('aria-busy');
  }
  renderCatalog();
}

function stockHTML(stock) {
  if (!Number.isFinite(stock)) return '—';
  if (stock === 0) return '<span class="stock-out">Out of stock</span>';
  if (stock <= 2) return `<span class="stock-low">${stock}</span>`;
  return String(stock);
}

function bookRowHTML(b) {
  const editing = state.editingBookId === b.id;
  const outOfStock = b.stock === 0;
  const restrictedBadge = b.restricted
    ? '<span class="badge badge-restricted" title="Available to Master and Supreme members">Restricted</span>'
    : '';
  const titleCell = `<div class="book-cell"><span class="book-title">${esc(b.title)}</span>${restrictedBadge}</div>`;

  if (editing) {
    return `<tr data-book-id="${b.id}" class="editing">
      <td>${titleCell}</td>
      <td>${esc(b.author)}</td>
      <td class="mono">${esc(b.isbn)}</td>
      <td class="num">
        <label class="sr-only" for="edit-price-${b.id}">Price in USD for ${esc(b.title)}</label>
        <input class="edit-input" id="edit-price-${b.id}" name="price_cents" type="text" inputmode="decimal" value="${esc(centsToInput(b.price_cents))}">
      </td>
      <td class="num">
        <label class="sr-only" for="edit-stock-${b.id}">Stock for ${esc(b.title)}</label>
        <input class="edit-input" id="edit-stock-${b.id}" name="stock" type="number" step="1" value="${esc(b.stock)}">
      </td>
      <td class="actions"><div class="btn-group">
        <button type="button" class="btn btn-primary btn-sm" data-action="save-book" data-id="${b.id}">Save</button>
        <button type="button" class="btn btn-ghost btn-sm" data-action="cancel-edit">Cancel</button>
      </div></td>
    </tr>`;
  }

  return `<tr data-book-id="${b.id}">
    <td>${titleCell}</td>
    <td>${esc(b.author)}</td>
    <td class="mono">${esc(b.isbn)}</td>
    <td class="num">${fmtMoney(b.price_cents)}</td>
    <td class="num">${stockHTML(b.stock)}</td>
    <td class="actions"><div class="btn-group">
      <button type="button" class="btn btn-ghost btn-sm" data-action="edit-book" data-id="${b.id}" aria-label="Edit price and stock of ${esc(b.title)}">Edit</button>
      <button type="button" class="btn btn-secondary btn-sm" data-action="borrow" data-id="${b.id}" ${outOfStock ? 'disabled title="Out of stock"' : ''} aria-label="Borrow ${esc(b.title)}">Borrow</button>
      <button type="button" class="btn btn-accent btn-sm" data-action="add-to-cart" data-id="${b.id}" ${outOfStock ? 'disabled title="Out of stock"' : ''} aria-label="Add ${esc(b.title)} to cart">Add to cart</button>
    </div></td>
  </tr>`;
}

function renderCatalog() {
  const c = state.catalog;
  const tbody = $('#books-body');
  if (c.error) {
    tbody.innerHTML = `<tr><td colspan="6">${inlineErrorHTML(c.error, 'the catalog')}</td></tr>`;
  } else if (!c.items.length) {
    const filtered = c.q || c.restricted || c.min_price !== '' || c.max_price !== '';
    tbody.innerHTML = `<tr><td colspan="6" class="empty">${filtered ? 'No books match these filters.' : 'The catalog is empty. Add the first book above.'}</td></tr>`;
  } else {
    tbody.innerHTML = c.items.map(bookRowHTML).join('');
  }

  const info = $('#page-info');
  const prev = $('[data-action="page-prev"]');
  const next = $('[data-action="page-next"]');
  if (c.error || !c.items.length) {
    info.textContent = c.error ? '' : '0 books';
    prev.disabled = c.error ? true : c.offset <= 0;
    next.disabled = true;
  } else {
    const from = c.offset + 1;
    const to = c.offset + c.items.length;
    const pages = Math.max(1, Math.ceil(c.total / c.limit));
    const page = Math.floor(c.offset / c.limit) + 1;
    info.textContent = `Showing ${from}–${to} of ${c.total} · Page ${page} of ${pages}`;
    prev.disabled = c.offset <= 0;
    next.disabled = c.offset + c.limit >= c.total;
  }
}

function initCatalog() {
  const form = $('#catalog-filters');
  const c = state.catalog;

  const readFilters = () => {
    clearFormErrors(form);
    let valid = true;
    const prices = {};
    for (const name of ['min_price', 'max_price']) {
      const input = form.elements[name];
      const cents = parseDollars(input.value);
      if (cents === null || (cents !== undefined && cents < 0)) {
        showFieldError(input, 'Enter an amount like 9.99');
        valid = false;
      } else {
        prices[name] = cents === undefined ? '' : cents;
      }
    }
    if (!valid) return false;
    c.q = form.elements.q.value;
    c.restricted = form.elements.restricted.value;
    c.min_price = prices.min_price;
    c.max_price = prices.max_price;
    c.sort = form.elements.sort.value;
    c.limit = Number(form.elements.limit.value) || 20;
    c.offset = 0;
    return true;
  };
  const apply = () => { if (readFilters()) { state.editingBookId = null; loadCatalog(); } };
  const applyDebounced = debounce(apply, 300);

  form.addEventListener('submit', (e) => { e.preventDefault(); apply(); });
  form.addEventListener('input', (e) => {
    if (e.target.matches('input')) applyDebounced();
  });
  form.addEventListener('change', (e) => {
    if (e.target.matches('select')) apply();
  });
  form.addEventListener('reset', () => setTimeout(apply, 0));

  // Add book
  const toggle = $('#toggle-add-book');
  const card = $('#add-book-card');
  const addForm = $('#add-book-form');
  const setOpen = (open) => {
    card.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.textContent = open ? 'Close form' : 'Add book';
    if (open) $('#nb-title').focus();
  };
  toggle.addEventListener('click', () => setOpen(card.hidden));
  document.addEventListener('click', (e) => {
    if (e.target.closest('[data-action="close-add-book"]')) { clearFormErrors(addForm); setOpen(false); toggle.focus(); }
  });

  addForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearFormErrors(addForm);
    const els = addForm.elements;
    const price = parseDollars(els.price_cents.value);
    const stock = parseIntStrict(els.stock.value);
    let invalid = false;
    if (price === null || price === undefined) { showFieldError(els.price_cents, 'Enter a price like 12.99'); invalid = true; }
    if (stock === null || stock === undefined) { showFieldError(els.stock, 'Enter a whole number'); invalid = true; }
    if (invalid) { addForm.querySelector('[aria-invalid="true"]').focus(); return; }

    const body = {
      title: els.title.value,
      author: els.author.value,
      isbn: els.isbn.value,
      price_cents: price,
      stock,
      restricted: els.restricted.checked,
    };
    const submit = addForm.querySelector('[type="submit"]');
    setBusy(submit, true);
    try {
      const book = await api('/books', { method: 'POST', body, context: 'Adding book' });
      state.books.set(book.id, book);
      toast({ type: 'success', title: 'Book added', message: `“${book.title}” (ISBN ${book.isbn}) is now in the catalog.` });
      addForm.reset();
      els.stock.value = '1';
      setOpen(false);
      loadCatalog();
    } catch (err) {
      applyApiErrorToForm(addForm, err);
    } finally {
      setBusy(submit, false);
    }
  });

  // Inline edit keyboard shortcuts
  $('#books-body').addEventListener('keydown', (e) => {
    if (!e.target.matches('.edit-input')) return;
    if (e.key === 'Enter') { e.preventDefault(); saveBookEdit(Number(e.target.closest('tr').dataset.bookId)); }
    if (e.key === 'Escape') { e.preventDefault(); cancelBookEdit(); }
  });
}

function startBookEdit(id) {
  state.editingBookId = id;
  renderCatalog();
  $(`#edit-price-${id}`)?.focus();
}

function cancelBookEdit() {
  const id = state.editingBookId;
  state.editingBookId = null;
  renderCatalog();
  $(`[data-action="edit-book"][data-id="${id}"]`)?.focus();
}

async function saveBookEdit(id) {
  const row = $(`tr[data-book-id="${id}"]`);
  const book = state.books.get(id);
  if (!row || !book) return;
  clearFormErrors(row);
  const priceInput = row.querySelector('[name="price_cents"]');
  const stockInput = row.querySelector('[name="stock"]');
  const price = parseDollars(priceInput.value);
  const stock = parseIntStrict(stockInput.value);
  if (price === null || price === undefined) { showFieldError(priceInput, 'e.g. 12.99'); priceInput.focus(); return; }
  if (stock === null || stock === undefined) { showFieldError(stockInput, 'Whole number'); stockInput.focus(); return; }

  const patch = {};
  if (price !== book.price_cents) patch.price_cents = price;
  if (stock !== book.stock) patch.stock = stock;
  if (!Object.keys(patch).length) { cancelBookEdit(); return; }

  const saveBtn = row.querySelector('[data-action="save-book"]');
  setBusy(saveBtn, true);
  try {
    const updated = await api(`/books/${id}`, { method: 'PATCH', body: patch, context: 'Updating book' });
    state.books.set(id, updated);
    state.catalog.items = state.catalog.items.map((b) => (b.id === id ? updated : b));
    // keep cart snapshot in sync with latest known price/stock
    state.cart.forEach((item) => {
      if (item.book_id === id) { item.price_cents = updated.price_cents; item.stock = updated.stock; }
    });
    saveCart();
    state.editingBookId = null;
    renderCatalog();
    $(`[data-action="edit-book"][data-id="${id}"]`)?.focus();
    toast({ type: 'success', title: 'Book updated', message: `“${updated.title}”: ${fmtMoney(updated.price_cents)}, stock ${updated.stock}.` });
  } catch (err) {
    setBusy(saveBtn, false);
    if (err.status === 422 && err.fields.length) {
      for (const f of err.fields) {
        const input = row.querySelector(`[name="${CSS.escape(f.field)}"]`);
        if (input) showFieldError(input, f.msg);
      }
      row.querySelector('[aria-invalid="true"]')?.focus();
    }
  }
}

/* =========================================================================
   Cart
   ========================================================================= */

function loadCart() {
  const raw = store.get(STORAGE_KEYS.cart, []);
  state.cart = Array.isArray(raw)
    ? raw.filter((i) => i && Number.isInteger(i.book_id) && Number.isInteger(i.quantity) && i.quantity > 0)
    : [];
}
function saveCart() { store.set(STORAGE_KEYS.cart, state.cart); renderHeader(); }

function addToCart(id) {
  if (!requireMember('add books to the cart')) return;
  const book = state.books.get(id);
  if (!book) return;
  const existing = state.cart.find((i) => i.book_id === id);
  const currentQty = existing ? existing.quantity : 0;
  if (Number.isFinite(book.stock) && currentQty + 1 > book.stock) {
    toast({ type: 'warning', title: 'Not enough stock', message: `Only ${book.stock} ${book.stock === 1 ? 'copy' : 'copies'} of “${book.title}” available.` });
    return;
  }
  if (existing) {
    existing.quantity += 1;
    Object.assign(existing, { title: book.title, author: book.author, price_cents: book.price_cents, stock: book.stock, restricted: book.restricted });
  } else {
    state.cart.push({
      book_id: book.id, title: book.title, author: book.author, price_cents: book.price_cents,
      stock: book.stock, restricted: book.restricted, quantity: 1,
    });
  }
  saveCart();
  toast({ type: 'success', title: 'Added to cart', message: `“${book.title}” × ${currentQty + 1}` });
  if (book.restricted && state.member && TIERS.indexOf(state.member.tier) < TIERS.indexOf('master')) {
    toast({ type: 'info', title: 'Restricted title', message: 'Checkout will require Master tier or above.' });
  }
}

function cartEstimate() {
  const subtotal = state.cart.reduce((s, i) => s + i.price_cents * i.quantity, 0);
  const qty = state.cart.reduce((s, i) => s + i.quantity, 0);
  const tier = state.member?.tier;
  const tierPct = tier in TIER_DISCOUNT ? TIER_DISCOUNT[tier] : null;
  const volumePct = qty >= VOLUME_DISCOUNT_QTY ? VOLUME_DISCOUNT_PERCENT : 0;
  const pct = (tierPct ?? 0) + volumePct;
  const discount = Math.floor((subtotal * pct) / 100);
  return { subtotal, qty, pct, discount, total: subtotal - discount, tierKnown: tierPct !== null, volumePct };
}

function renderCart() {
  const el = $('#cart-body');
  if (!state.cart.length) {
    el.innerHTML = `<div class="empty-state"><p>Your cart is empty.</p>
      <button type="button" class="btn btn-secondary" data-action="goto" data-tab="catalog">Browse the catalog</button></div>`;
    return;
  }
  const est = cartEstimate();
  const rows = state.cart.map((i) => `
    <tr data-cart-id="${i.book_id}">
      <td><div class="book-cell"><span class="book-title">${esc(i.title)}</span>
        <span class="cell-sub">${esc(i.author || '')}</span>
        ${i.restricted ? '<span class="badge badge-restricted">Restricted</span>' : ''}</div></td>
      <td class="num">${fmtMoney(i.price_cents)}</td>
      <td class="num">
        <label class="sr-only" for="qty-${i.book_id}">Quantity of ${esc(i.title)}</label>
        <input class="qty-input" id="qty-${i.book_id}" type="number" min="1" step="1" value="${i.quantity}" data-action="cart-qty" data-id="${i.book_id}">
      </td>
      <td class="num">${fmtMoney(i.price_cents * i.quantity)}</td>
      <td class="actions"><button type="button" class="btn btn-ghost btn-sm" data-action="cart-remove" data-id="${i.book_id}" aria-label="Remove ${esc(i.title)} from cart">Remove</button></td>
    </tr>`).join('');

  const noMember = !state.memberId;
  el.innerHTML = `
    <div class="table-wrap">
      <table class="table">
        <caption class="sr-only">Cart items</caption>
        <thead><tr><th scope="col">Book</th><th scope="col" class="num">Unit price</th><th scope="col" class="num">Qty</th><th scope="col" class="num">Line total</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="cart-footer">
      <p class="hint">Estimate based on current prices${est.tierKnown ? ` and ${esc(cap(state.member.tier))} tier discount` : ''}.<br>Final pricing is calculated by the store at checkout.</p>
      <dl class="summary">
        <div><dt>Subtotal (${pluralize(est.qty, 'item')})</dt><dd>${fmtMoney(est.subtotal)}</dd></div>
        <div><dt>Est. discount (${est.pct}%${est.volumePct ? ', incl. volume' : ''})</dt><dd class="discount">−${fmtMoney(est.discount)}</dd></div>
        <div class="total"><dt>Est. total</dt><dd>${fmtMoney(est.total)}</dd></div>
      </dl>
    </div>
    <div class="checkout-row">
      <button type="button" class="btn btn-ghost" data-action="cart-clear">Clear cart</button>
      ${noMember ? '<span class="hint">Select a member to check out.</span>' : ''}
      <button type="button" class="btn btn-primary" data-action="checkout" ${noMember ? 'disabled' : ''}>Place order${state.member ? ` as ${esc(state.member.name)}` : state.memberId ? ` as member #${state.memberId}` : ''}</button>
    </div>`;
}

async function checkout(button) {
  if (!requireMember('check out') || !state.cart.length) return;
  const body = {
    member_id: state.memberId,
    items: state.cart.map((i) => ({ book_id: i.book_id, quantity: i.quantity })),
  };
  setBusy(button, true);
  try {
    const order = await api('/orders', { method: 'POST', body, context: 'Checkout' });
    state.cart = [];
    saveCart();
    renderCart();
    state.orderDetail = { order, heading: 'Order placed' };
    renderOrderDetail();
    toast({ type: 'success', title: `Order #${order.id} placed`, message: `Total ${fmtMoney(order.total_cents)} — awaiting payment.` });
    $('#order-detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    loadOrders();
    state.catalog.loaded = false; // stock changed
  } catch {
    setBusy(button, false); // cart kept intact so the member can adjust and retry
  }
}

/* =========================================================================
   Orders
   ========================================================================= */

function orderBreakdownHTML(order, heading) {
  const items = Array.isArray(order.items) ? order.items : [];
  const rows = items.map((it) => `
    <tr>
      <td>${esc(bookLabel(it.book_id))}</td>
      <td class="num">${esc(it.quantity)}</td>
      <td class="num">${fmtMoney(it.unit_price_cents)}</td>
      <td class="num">${fmtMoney(it.line_total_cents)}</td>
    </tr>`).join('');
  const pending = order.status === 'pending';
  return `
    <div class="order-detail-head">
      <div>
        <h2>${esc(heading || 'Order')} · #${esc(order.id)} <span class="badge badge-${esc(order.status)}">${esc(order.status)}</span></h2>
        <p class="hint">Placed ${fmtDate(order.created_at)}</p>
      </div>
      <button type="button" class="btn btn-ghost btn-sm" data-action="close-order-detail">Close</button>
    </div>
    <div class="table-wrap">
      <table class="table">
        <caption class="sr-only">Items in order ${esc(order.id)}</caption>
        <thead><tr><th scope="col">Book</th><th scope="col" class="num">Qty</th><th scope="col" class="num">Unit price</th><th scope="col" class="num">Line total</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4" class="empty">No items.</td></tr>'}</tbody>
      </table>
    </div>
    <dl class="summary">
      <div><dt>Subtotal</dt><dd>${fmtMoney(order.subtotal_cents)}</dd></div>
      <div><dt>Discount (${esc(order.discount_percent ?? 0)}%)</dt><dd class="discount">−${fmtMoney(order.discount_cents)}</dd></div>
      <div class="total"><dt>Total</dt><dd>${fmtMoney(order.total_cents)}</dd></div>
    </dl>
    ${pending ? `<div class="checkout-row">
      <button type="button" class="btn btn-danger" data-action="order-cancel" data-id="${order.id}">Cancel order</button>
      <button type="button" class="btn btn-primary" data-action="order-pay" data-id="${order.id}">Pay ${fmtMoney(order.total_cents)}</button>
    </div>` : ''}`;
}

function renderOrderDetail() {
  const el = $('#order-detail');
  const d = state.orderDetail;
  if (!d) { el.hidden = true; el.innerHTML = ''; return; }
  el.hidden = false;
  el.innerHTML = orderBreakdownHTML(d.order, d.heading);
  ensureBooks((d.order.items || []).map((i) => i.book_id), renderOrderDetail);
}

async function loadOrders() {
  const o = state.orders;
  const el = $('#orders-body');
  if (!state.memberId) {
    el.innerHTML = '<div class="empty-state"><p>Select a member to see their orders.</p><button type="button" class="btn btn-secondary" data-action="goto" data-tab="members">Choose member</button></div>';
    return;
  }
  const seq = ++o.seq;
  const memberId = state.memberId;
  if (!o.items.length && !o.error) el.innerHTML = '<div class="empty-state"><p>Loading orders…</p></div>';
  try {
    const data = await api(`/members/${memberId}/orders`, { context: 'Loading orders' });
    if (seq !== o.seq) return;
    o.items = Array.isArray(data) ? data : [];
    o.error = null;
  } catch (err) {
    if (seq !== o.seq) return;
    o.items = [];
    o.error = err;
  }
  renderOrders();
}

function renderOrders() {
  const o = state.orders;
  const el = $('#orders-body');
  if (o.error) { el.innerHTML = inlineErrorHTML(o.error, 'orders'); return; }
  if (!o.items.length) { el.innerHTML = '<div class="empty-state"><p>No orders yet.</p></div>'; return; }
  const rows = [...o.items].reverse().map((ord) => {
    const qty = (ord.items || []).reduce((s, i) => s + (i.quantity || 0), 0);
    const pending = ord.status === 'pending';
    return `<tr>
      <td><span class="mono">#${esc(ord.id)}</span></td>
      <td>${fmtDate(ord.created_at)}</td>
      <td class="num">${qty}</td>
      <td class="num">${fmtMoney(ord.subtotal_cents)}</td>
      <td class="num discount">${ord.discount_cents ? `−${fmtMoney(ord.discount_cents)} <span class="cell-sub">(${esc(ord.discount_percent)}%)</span>` : '—'}</td>
      <td class="num"><strong>${fmtMoney(ord.total_cents)}</strong></td>
      <td><span class="badge badge-${esc(ord.status)}">${esc(ord.status)}</span></td>
      <td class="actions"><div class="btn-group">
        <button type="button" class="btn btn-ghost btn-sm" data-action="order-view" data-id="${ord.id}" aria-label="View order ${esc(ord.id)}">View</button>
        ${pending ? `<button type="button" class="btn btn-danger btn-sm" data-action="order-cancel" data-id="${ord.id}" aria-label="Cancel order ${esc(ord.id)}">Cancel</button>
        <button type="button" class="btn btn-primary btn-sm" data-action="order-pay" data-id="${ord.id}" aria-label="Pay order ${esc(ord.id)}">Pay</button>` : ''}
      </div></td>
    </tr>`;
  }).join('');
  el.innerHTML = `<div class="table-wrap"><table class="table">
    <caption class="sr-only">Orders for the selected member, newest first</caption>
    <thead><tr><th scope="col">Order</th><th scope="col">Placed</th><th scope="col" class="num">Items</th><th scope="col" class="num">Subtotal</th><th scope="col" class="num">Discount</th><th scope="col" class="num">Total</th><th scope="col">Status</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function upsertOrder(order) {
  const idx = state.orders.items.findIndex((x) => x.id === order.id);
  if (idx >= 0) state.orders.items[idx] = order;
  if (state.orderDetail?.order.id === order.id) state.orderDetail.order = order;
}

async function payOrder(id, button) {
  setBusy(button, true);
  try {
    const order = await api(`/orders/${id}/pay`, { method: 'POST', context: `Paying order #${id}` });
    upsertOrder(order);
    toast({ type: 'success', title: `Order #${id} paid`, message: `Charged ${fmtMoney(order.total_cents)}.` });
    renderOrderDetail();
    loadOrders();
  } catch (err) {
    setBusy(button, false);
    if (err.status === 409) loadOrders(); // status changed elsewhere; refresh
  }
}

const pendingConfirms = new WeakMap();
async function cancelOrder(id, button) {
  // Two-step confirm without blocking dialogs.
  if (!button.classList.contains('confirming')) {
    button.classList.add('confirming');
    button.dataset.label = button.textContent;
    button.textContent = 'Confirm cancel';
    pendingConfirms.set(button, setTimeout(() => {
      if (!button.isConnected) return;
      button.classList.remove('confirming');
      button.textContent = button.dataset.label;
    }, 4000));
    return;
  }
  clearTimeout(pendingConfirms.get(button));
  setBusy(button, true);
  try {
    const order = await api(`/orders/${id}/cancel`, { method: 'POST', context: `Cancelling order #${id}` });
    upsertOrder(order);
    toast({ type: 'success', title: `Order #${id} cancelled`, message: 'Reserved stock has been released.' });
    state.catalog.loaded = false;
    renderOrderDetail();
    loadOrders();
  } catch (err) {
    setBusy(button, false);
    button.classList.remove('confirming');
    button.textContent = button.dataset.label || 'Cancel';
    if (err.status === 409) loadOrders();
  }
}

async function viewOrder(id, button) {
  const cached = state.orders.items.find((x) => x.id === id);
  if (cached) {
    state.orderDetail = { order: cached, heading: 'Order' };
    renderOrderDetail();
    $('#order-detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  // Refresh from the source of truth.
  setBusy(button, true);
  try {
    const order = await api(`/orders/${id}`, { context: `Loading order #${id}` });
    upsertOrder(order);
    state.orderDetail = { order, heading: 'Order' };
    renderOrderDetail();
    if (!cached) $('#order-detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch { /* cached copy (if any) stays visible */ } finally {
    if (button.isConnected) setBusy(button, false);
  }
}

/* =========================================================================
   Members
   ========================================================================= */

function initials(name) {
  return String(name || '?').trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() || '').join('') || '?';
}

function renderMemberCard() {
  const el = $('#member-card');
  if (!state.memberId) {
    el.innerHTML = `<h2 class="card-title">Current member</h2>
      <div class="empty-state"><p>No member selected.</p><p class="hint">Sign in with a member ID or create a new member.</p></div>`;
    return;
  }
  const m = state.member;
  const tier = m?.tier;
  const limit = tier in TIER_LOAN_LIMIT ? TIER_LOAN_LIMIT[tier] : null;
  const head = m
    ? `<div class="member-head">
        <div class="avatar" aria-hidden="true">${esc(initials(m.name))}</div>
        <div>
          <div class="member-name">${esc(m.name)}</div>
          <div class="member-meta">
            <span class="badge badge-tier">${esc(cap(m.tier))}</span>
            <span>${esc(m.email)}</span><span aria-hidden="true">·</span><span>ID ${esc(m.id)}</span>
          </div>
          <div class="member-meta">Member since ${fmtDate(m.created_at, { dateOnly: true })}</div>
        </div>
      </div>
      <dl class="perks">
        <div><dt>Order discount</dt><dd>${tier in TIER_DISCOUNT ? `${TIER_DISCOUNT[tier]}%` : '—'} <span class="cell-sub">+5% on 10+ items</span></dd></div>
        <div><dt>Loan limit</dt><dd>${limit === null ? '—' : limit === Infinity ? 'Unlimited' : pluralize(limit, 'book')}</dd></div>
        <div><dt>Restricted titles</dt><dd>${TIERS.indexOf(tier) >= TIERS.indexOf('master') ? 'Allowed' : 'Master tier required'}</dd></div>
        <div><dt>Late fee</dt><dd>${fmtMoney(LATE_FEE_PER_DAY_CENTS)}/day <span class="cell-sub">(capped at price)</span></dd></div>
      </dl>`
    : `<div class="member-head">
        <div class="avatar" aria-hidden="true">#</div>
        <div><div class="member-name">Member #${esc(state.memberId)}</div>
        <div class="member-meta">Profile details could not be loaded.</div></div>
      </div>`;

  el.innerHTML = `<h2 class="card-title">Current member</h2>
    ${head}
    <p class="section-label" id="stats-label">Activity</p>
    <div id="member-stats">${statsHTML()}</div>
    <div class="member-actions">
      <button type="button" class="btn btn-secondary btn-sm" data-action="refresh-member">Refresh</button>
      <button type="button" class="btn btn-ghost btn-sm" data-action="sign-out">Sign out</button>
    </div>`;
}

function statsHTML() {
  const s = state.stats;
  if (s.error) return inlineErrorHTML(s.error, 'member stats');
  if (!s.data) return `<p class="hint">${s.loading ? 'Loading stats…' : 'No stats loaded.'}</p>`;
  const d = s.data;
  const stat = (label, value, warn = false) => `<div class="stat${warn ? ' warn' : ''}"><dt>${label}</dt><dd>${value}</dd></div>`;
  return `<dl class="stats" aria-labelledby="stats-label">
    ${stat('Orders paid', esc(d.orders_paid ?? 0))}
    ${stat('Total spent', fmtMoney(d.total_spent_cents ?? 0))}
    ${stat('Active loans', esc(d.active_loans ?? 0))}
    ${stat('Overdue loans', esc(d.overdue_loans ?? 0), (d.overdue_loans ?? 0) > 0)}
    ${stat('Late fees paid', fmtMoney(d.late_fees_cents ?? 0))}
  </dl>`;
}

async function loadStats() {
  if (!state.memberId) return;
  const memberId = state.memberId;
  state.stats = { data: state.stats.data, error: null, loading: true };
  const target = $('#member-stats');
  if (target && !state.stats.data) target.innerHTML = statsHTML();
  try {
    const data = await api(`/members/${memberId}/stats`, { context: 'Loading member stats' });
    if (memberId !== state.memberId) return;
    state.stats = { data, error: null, loading: false };
  } catch (err) {
    if (memberId !== state.memberId) return;
    state.stats = { data: null, error: err, loading: false };
  }
  const el = $('#member-stats');
  if (el) el.innerHTML = statsHTML();
}

function setMember(id, member = null) {
  const changed = id !== state.memberId;
  state.memberId = id;
  state.member = member;
  store.set(STORAGE_KEYS.member, id);
  if (changed) {
    state.stats = { data: null, error: null, loading: false };
    state.orders = { items: [], error: null, loading: false, seq: state.orders.seq + 1 };
    state.loans = { items: [], error: null, loading: false, seq: state.loans.seq + 1 };
    state.orderDetail = null;
  }
  renderHeader();
  renderMemberCard();
  if (!$('#panel-cart').hidden) { renderCart(); renderOrderDetail(); }
}

/** Fetch a member by id. Returns the member, or null when the lookup isn't possible (non-404 error). Throws on 404. */
async function fetchMember(id, context) {
  try {
    return await api(`/members/${id}`, { context });
  } catch (err) {
    if (err.status === 404) throw err;
    return null;
  }
}

async function restoreMember() {
  const saved = store.get(STORAGE_KEYS.member, null);
  if (!Number.isInteger(saved) || saved < 1) return;
  state.memberId = saved;
  renderHeader();
  try {
    const member = await fetchMember(saved, 'Loading saved member');
    if (state.memberId !== saved) return;
    state.member = member;
  } catch {
    if (state.memberId !== saved) return;
    toast({ type: 'info', title: 'Signed out', message: `Saved member #${saved} no longer exists.` });
    state.memberId = null;
    state.member = null;
    store.set(STORAGE_KEYS.member, null);
  }
  renderHeader();
  if (!$('#panel-members').hidden) { renderMemberCard(); loadStats(); }
  if (!$('#panel-cart').hidden) { renderCart(); loadOrders(); }
  if (!$('#panel-loans').hidden) loadLoans();
}

function initMembers() {
  const signin = $('#signin-form');
  signin.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearFormErrors(signin);
    const input = signin.elements.member_id;
    const id = parseIntStrict(input.value);
    if (!id || id < 1) { showFieldError(input, 'Enter a positive member ID'); input.focus(); return; }
    const btn = signin.querySelector('[type="submit"]');
    setBusy(btn, true);
    try {
      const member = await api(`/members/${id}`, { context: 'Signing in' });
      setMember(member.id, member);
      signin.reset();
      toast({ type: 'success', title: `Signed in as ${member.name}`, message: `${cap(member.tier)} member #${member.id}` });
      loadStats();
    } catch (err) {
      if (err.status === 404) {
        clearFormErrors(signin);
        showFieldError(input, `No member with ID ${id}.`);
        input.focus();
      } else if (err.status === 501 || err.status >= 500 || err.status === 0) {
        // Can't verify right now — let the user act as this id anyway so other features stay usable.
        setMember(id, null);
        signin.reset();
        showFormSummary(signin, `<strong>Couldn't verify member #${esc(id)}${err.status ? ` (${err.status})` : ''}.</strong> Acting as this ID anyway.`);
        $('.form-errors', signin).className = 'form-errors notice notice-warning';
        setTimeout(() => { $('.form-errors', signin).className = 'form-errors notice notice-error'; clearFormErrors(signin); }, 6000);
        loadStats();
      } else {
        applyApiErrorToForm(signin, err, { fieldMap: { member_id: 'member_id' } });
      }
    } finally {
      setBusy(btn, false);
    }
  });

  const create = $('#create-member-form');
  create.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearFormErrors(create);
    const els = create.elements;
    const body = { name: els.name.value, email: els.email.value, tier: els.tier.value };
    const btn = create.querySelector('[type="submit"]');
    setBusy(btn, true);
    try {
      const member = await api('/members', { method: 'POST', body, context: 'Creating member' });
      setMember(member.id, member);
      create.reset();
      toast({ type: 'success', title: 'Member created', message: `${member.name} (#${member.id}) is now signed in.` });
      loadStats();
    } catch (err) {
      applyApiErrorToForm(create, err);
      if (err.status === 409) showFieldError(els.email, err.message || 'Email already in use');
    } finally {
      setBusy(btn, false);
    }
  });
}

async function refreshMember() {
  if (!state.memberId) return;
  const id = state.memberId;
  try {
    const member = await fetchMember(id, 'Refreshing member');
    if (id !== state.memberId) return;
    if (member) state.member = member;
    renderHeader();
    renderMemberCard();
  } catch {
    toast({ type: 'info', title: 'Member not found', message: `Member #${id} no longer exists.` });
    setMember(null);
    return;
  }
  loadStats();
}

/* =========================================================================
   Loans
   ========================================================================= */

async function borrowBook(id, button) {
  if (!requireMember('borrow books')) return;
  const book = state.books.get(id);
  setBusy(button, true);
  try {
    const loan = await api('/loans', { method: 'POST', body: { member_id: state.memberId, book_id: id }, context: 'Borrowing' });
    toast({ type: 'success', title: 'Book borrowed', message: `“${book?.title ?? `Book #${id}`}” is due ${fmtDate(loan.due_at, { dateOnly: true })}.` });
    loadCatalog();
  } catch {
    if (button.isConnected) setBusy(button, false);
  }
}

async function loadLoans() {
  const l = state.loans;
  const el = $('#loans-body');
  if (!state.memberId) {
    el.innerHTML = '<div class="empty-state"><p>Select a member to see their loans.</p><button type="button" class="btn btn-secondary" data-action="goto" data-tab="members">Choose member</button></div>';
    return;
  }
  const seq = ++l.seq;
  const status = $('#loan-status').value;
  if (!l.items.length && !l.error) el.innerHTML = '<div class="empty-state"><p>Loading loans…</p></div>';
  try {
    const data = await api(`/members/${state.memberId}/loans`, { query: { status }, context: 'Loading loans' });
    if (seq !== l.seq) return;
    l.items = Array.isArray(data) ? data : [];
    l.error = null;
  } catch (err) {
    if (seq !== l.seq) return;
    l.items = [];
    l.error = err;
  }
  renderLoans();
  ensureBooks(l.items.map((x) => x.book_id), renderLoans);
}

function renderLoans() {
  const l = state.loans;
  const el = $('#loans-body');
  if (!state.memberId) return;
  if (l.error) { el.innerHTML = inlineErrorHTML(l.error, 'loans'); return; }
  if (!l.items.length) {
    const status = $('#loan-status').value;
    el.innerHTML = `<div class="empty-state"><p>${status ? `No ${esc(status)} loans.` : 'No loans yet. Borrow a book from the catalog.'}</p></div>`;
    return;
  }
  const rows = [...l.items].reverse().map((loan) => {
    const returned = loan.status === 'returned' || !!loan.returned_at;
    const overdue = loan.status === 'overdue';
    return `<tr>
      <td><span class="mono">#${esc(loan.id)}</span></td>
      <td><span class="book-title">${esc(bookLabel(loan.book_id))}</span></td>
      <td>${fmtDate(loan.borrowed_at)}</td>
      <td class="${overdue ? 'overdue-text' : ''}">${fmtDate(loan.due_at)}</td>
      <td>${loan.returned_at ? fmtDate(loan.returned_at) : '—'}</td>
      <td><span class="badge badge-${esc(loan.status)}">${esc(loan.status)}</span></td>
      <td class="num">${returned ? fmtMoney(loan.late_fee_cents ?? 0) : '—'}</td>
      <td class="actions">${returned ? '' : `<button type="button" class="btn ${overdue ? 'btn-primary' : 'btn-secondary'} btn-sm" data-action="loan-return" data-id="${loan.id}" aria-label="Return ${esc(bookLabel(loan.book_id))}">Return</button>`}</td>
    </tr>`;
  }).join('');
  el.innerHTML = `<div class="table-wrap"><table class="table">
    <caption class="sr-only">Loans for the selected member, newest first</caption>
    <thead><tr><th scope="col">Loan</th><th scope="col">Book</th><th scope="col">Borrowed</th><th scope="col">Due</th><th scope="col">Returned</th><th scope="col">Status</th><th scope="col" class="num">Late fee</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

async function returnLoan(id, button) {
  setBusy(button, true);
  try {
    const loan = await api(`/loans/${id}/return`, { method: 'POST', context: `Returning loan #${id}` });
    const fee = loan.late_fee_cents ?? 0;
    toast({
      type: fee > 0 ? 'warning' : 'success',
      title: `Returned “${bookLabel(loan.book_id)}”`,
      message: fee > 0 ? `Late fee charged: ${fmtMoney(fee)}.` : 'Returned on time — no late fee.',
      timeout: fee > 0 ? 9000 : undefined,
    });
    state.catalog.loaded = false;
    loadLoans();
  } catch (err) {
    if (button.isConnected) setBusy(button, false);
    if (err.status === 409) loadLoans();
  }
}

/* =========================================================================
   Reports
   ========================================================================= */

async function loadReports() {
  const r = state.reports;
  const seq = ++r.seq;
  const el = $('#reports-body');
  const limit = $('#report-limit').value;
  el.innerHTML = '<div class="empty-state"><p>Loading report…</p></div>';
  try {
    const data = await api('/reports/top-books', { query: { limit }, context: 'Loading top books' });
    if (seq !== r.seq) return;
    const rows = Array.isArray(data) ? data : [];
    if (!rows.length) {
      el.innerHTML = '<div class="empty-state"><p>No paid orders yet — nothing to rank.</p></div>';
      return;
    }
    const max = Math.max(...rows.map((x) => x.copies_sold || 0), 1);
    el.innerHTML = `<div class="table-wrap"><table class="table">
      <caption class="sr-only">Top books by copies sold in paid orders</caption>
      <thead><tr><th scope="col" class="num">Rank</th><th scope="col">Title</th><th scope="col">Book ID</th><th scope="col" class="num">Copies sold</th></tr></thead>
      <tbody>${rows.map((row, i) => `<tr>
        <td class="num">${i + 1}</td>
        <td><span class="book-title">${esc(row.title)}</span></td>
        <td class="mono">#${esc(row.book_id)}</td>
        <td class="num"><strong>${esc(row.copies_sold)}</strong>
          <span class="sr-only">copies</span>
          <div aria-hidden="true" style="height:4px;margin-top:4px;margin-left:auto;border-radius:2px;background:var(--amber-500);width:${Math.round(((row.copies_sold || 0) / max) * 100)}%;max-width:120px"></div>
        </td>
      </tr>`).join('')}</tbody></table></div>`;
  } catch (err) {
    if (seq !== r.seq) return;
    el.innerHTML = inlineErrorHTML(err, 'the report');
  }
}

/* =========================================================================
   Global event delegation
   ========================================================================= */

function initActions() {
  document.addEventListener('click', (e) => {
    const target = e.target.closest('[data-action]');
    if (!target || target.disabled) return;
    const id = target.dataset.id !== undefined ? Number(target.dataset.id) : undefined;

    switch (target.dataset.action) {
      case 'goto': activateTab(target.dataset.tab, { focus: false }); $(`#panel-${target.dataset.tab}`)?.focus(); break;
      case 'page-prev':
        state.catalog.offset = Math.max(0, state.catalog.offset - state.catalog.limit);
        state.editingBookId = null; loadCatalog(); break;
      case 'page-next':
        state.catalog.offset += state.catalog.limit;
        state.editingBookId = null; loadCatalog(); break;
      case 'edit-book': startBookEdit(id); break;
      case 'cancel-edit': cancelBookEdit(); break;
      case 'save-book': saveBookEdit(id); break;
      case 'add-to-cart': addToCart(id); break;
      case 'borrow': borrowBook(id, target); break;
      case 'cart-remove':
        state.cart = state.cart.filter((i) => i.book_id !== id);
        saveCart(); renderCart(); break;
      case 'cart-clear': state.cart = []; saveCart(); renderCart(); break;
      case 'checkout': checkout(target); break;
      case 'order-view': viewOrder(id, target); break;
      case 'order-pay': payOrder(id, target); break;
      case 'order-cancel': cancelOrder(id, target); break;
      case 'close-order-detail': state.orderDetail = null; renderOrderDetail(); break;
      case 'refresh-orders': loadOrders(); break;
      case 'refresh-loans': loadLoans(); break;
      case 'refresh-reports': loadReports(); break;
      case 'refresh-member': refreshMember(); break;
      case 'sign-out':
        setMember(null);
        toast({ type: 'info', title: 'Signed out' });
        break;
      default: break;
    }
  });

  document.addEventListener('change', (e) => {
    const input = e.target.closest('[data-action="cart-qty"]');
    if (!input) return;
    const item = state.cart.find((i) => i.book_id === Number(input.dataset.id));
    if (!item) return;
    let qty = parseIntStrict(input.value);
    if (!qty || qty < 1) qty = 1;
    if (Number.isFinite(item.stock) && qty > item.stock) {
      toast({ type: 'warning', title: 'Limited stock', message: `Only ${item.stock} of “${item.title}” were in stock when added; checkout may fail.` });
    }
    item.quantity = qty;
    saveCart();
    renderCart();
    $(`#qty-${item.book_id}`)?.focus();
  });

  $('#loan-status').addEventListener('change', () => { state.loans.items = []; loadLoans(); });
  $('#report-limit').addEventListener('change', loadReports);
}

/* =========================================================================
   Boot
   ========================================================================= */

function boot() {
  loadCart();
  renderHeader();
  initTabs();
  initActions();
  initCatalog();
  initMembers();

  const initial = location.hash.slice(1);
  activateTab(TAB_IDS.includes(initial) ? initial : 'catalog', { updateHash: false });
  checkHealth();
  restoreMember();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
