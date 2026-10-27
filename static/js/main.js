/* Customer page: choose cement or iron, build the order, generate the bill. */
(function () {
  'use strict';

  const dataEl = document.getElementById('catalog-data');
  if (!dataEl) { return; }

  const CATALOG = JSON.parse(dataEl.textContent);
  const CART_KEY = 'ssc_cart';
  const UNIT_WORD = { Bags: 'bags', Pieces: 'pieces', Tons: 'tons' };

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  // Small DOM builder. Text is always set with textContent (never innerHTML).
  function h(tag, props, kids) {
    const node = document.createElement(tag);
    Object.keys(props || {}).forEach((key) => {
      if (key === 'text') { node.textContent = props[key]; }
      else if (key === 'class') { node.className = props[key]; }
      else { node.setAttribute(key, props[key]); }
    });
    (kids || []).forEach((kid) => { if (kid) { node.appendChild(kid); } });
    return node;
  }

  /* ---------- Cart ---------- */
  let cart = [];
  try {
    const saved = JSON.parse(sessionStorage.getItem(CART_KEY) || '[]');
    if (Array.isArray(saved)) { cart = saved; }
  } catch (e) { cart = []; }

  function saveCart() {
    try { sessionStorage.setItem(CART_KEY, JSON.stringify(cart)); } catch (e) { /* ignore */ }
  }

  function parseQty(raw, unit) {
    const value = String(raw).trim();
    if (unit === 'Tons') {
      if (!/^\d{1,4}(\.\d{1,3})?$/.test(value)) { return null; }
      const n = parseFloat(value);
      return n > 0 && n <= 1000 ? String(n) : null;
    }
    if (!/^\d{1,6}$/.test(value)) { return null; }
    const n = parseInt(value, 10);
    return n >= 1 && n <= 100000 ? String(n) : null;
  }

  function addToCart(entry) {
    const existing = cart.find((c) => c.category === entry.category && c.name === entry.name && c.unit === entry.unit);
    if (!existing) {
      cart.push(entry);
      return true;
    }
    const total = entry.unit === 'Tons'
      ? Math.round((parseFloat(existing.quantity) + parseFloat(entry.quantity)) * 1000) / 1000
      : parseInt(existing.quantity, 10) + parseInt(entry.quantity, 10);
    const merged = parseQty(String(total), entry.unit);
    if (merged === null) { return false; }
    existing.quantity = merged;
    return true;
  }

  function renderCart() {
    const list = $('#cartList');
    list.replaceChildren();
    cart.forEach((item, index) => {
      const label = h('span', { text: item.name }, [
        h('small', { text: item.quantity + ' ' + (UNIT_WORD[item.unit] || item.unit) }),
      ]);
      const remove = h('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Remove ' + item.name, text: '×' });
      remove.addEventListener('click', () => {
        cart.splice(index, 1);
        saveCart();
        renderCart();
      });
      const spec = CATALOG[item.category];
      const photo = spec && spec.images && spec.images[item.name];
      const left = h('div', { class: 'cart-item' }, [
        photo ? h('img', { class: 'cart-thumb', src: photo, alt: '' }) : null,
        label,
      ]);
      list.appendChild(h('li', {}, [left, remove]));
    });
    $('#cartCount').textContent = String(cart.length);
    $('#cartEmpty').hidden = cart.length > 0;
    $('#submitBtn').disabled = cart.length === 0;
    if (cart.length > 0) { $('#orderArea').hidden = false; }
  }

  /* ---------- Product window ---------- */
  function badgeText(category, name) {
    if (category === 'iron') {
      const size = name.match(/(\d+)\s*mm/i);
      if (size) { return size[1] + 'mm'; }
    }
    return name.split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  }

  function productCard(category, spec, name, index) {
    const unitSelect = h('select', { 'aria-label': 'Unit for ' + name });
    spec.units.forEach((u) => unitSelect.appendChild(h('option', { value: u, text: u })));

    const qtyLabel = h('span', {});
    const qtyInput = h('input', { class: 'qty-input', autocomplete: 'off', maxlength: '9' });
    const message = h('p', { class: 'product-msg', role: 'status' });

    function syncUnit() {
      const unit = unitSelect.value;
      qtyLabel.textContent = 'Quantity (' + (UNIT_WORD[unit] || unit) + ')';
      qtyInput.setAttribute('inputmode', unit === 'Tons' ? 'decimal' : 'numeric');
      qtyInput.setAttribute('placeholder', unit === 'Tons' ? 'e.g. 1.5' : 'e.g. 50');
      qtyInput.value = '';
      message.textContent = '';
    }
    unitSelect.addEventListener('change', syncUnit);

    const addBtn = h('button', { type: 'button', class: 'btn btn-primary btn-block', text: 'Add to order' });
    function add() {
      const unit = unitSelect.value;
      const quantity = parseQty(qtyInput.value, unit);
      message.className = 'product-msg';
      if (quantity === null) {
        message.textContent = unit === 'Tons'
          ? 'Enter tons as a number, for example 1.5'
          : 'Enter a whole number, for example 50';
        qtyInput.focus();
        return;
      }
      if (!addToCart({ category: category, name: name, unit: unit, quantity: quantity })) {
        message.textContent = 'That quantity is too large.';
        return;
      }
      saveCart();
      renderCart();
      qtyInput.value = '';
      message.className = 'product-msg ok';
      message.textContent = 'Added to your order';
      setTimeout(() => { if (message.className.indexOf('ok') !== -1) { message.textContent = ''; } }, 2200);
    }
    addBtn.addEventListener('click', add);
    qtyInput.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') { ev.preventDefault(); add(); }
    });

    const photoUrl = spec.images && spec.images[name];
    const card = h('div', { class: 'product' }, [
      photoUrl ? h('img', { class: 'product-img', src: photoUrl, alt: name, loading: 'lazy' }) : null,
      h('div', { class: 'product-top' }, [
        photoUrl ? null : h('span', { class: 'badge b' + (index % 3), text: badgeText(category, name) }),
        h('h3', { text: name }),
      ]),
      spec.units.length > 1 ? h('label', { class: 'field' }, [h('span', { text: 'Unit' }), unitSelect]) : null,
      h('label', { class: 'field' }, [qtyLabel, qtyInput]),
      addBtn,
      message,
    ]);
    syncUnit();
    return card;
  }

  function openCategory(category) {
    const spec = CATALOG[category];
    if (!spec) { return; }
    $$('[data-cat]').forEach((btn) => {
      const on = btn.dataset.cat === category;
      btn.classList.toggle('active', on);
      if (btn.classList.contains('nav-btn')) { btn.setAttribute('aria-pressed', String(on)); }
    });
    $('#panelTitle').textContent = spec.title + ': choose the type and quantity';
    const grid = $('#productGrid');
    grid.replaceChildren();
    spec.items.forEach((name, i) => grid.appendChild(productCard(category, spec, name, i)));
    $('#productPanel').hidden = false;
    $('#orderArea').hidden = false;
    $('#orderArea').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  $$('[data-cat]').forEach((btn) => btn.addEventListener('click', () => openCategory(btn.dataset.cat)));
  $('#closePanel').addEventListener('click', () => {
    $('#productPanel').hidden = true;
    $$('[data-cat]').forEach((btn) => {
      btn.classList.remove('active');
      if (btn.classList.contains('nav-btn')) { btn.setAttribute('aria-pressed', 'false'); }
    });
    if (cart.length === 0) { $('#orderArea').hidden = true; }
  });

  /* ---------- Generate bill ---------- */
  const form = $('#orderForm');
  const formError = $('#formError');

  function showError(text) {
    formError.textContent = text;
    formError.hidden = false;
  }

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    formError.hidden = true;
    if (cart.length === 0) { showError('Please add at least one item to your order.'); return; }

    const payload = {
      name: form.elements.name.value,
      phone: form.elements.phone.value,
      address: form.elements.address.value,
      note: form.elements.note.value,
      items: cart,
    };
    if (payload.name.trim().length < 2) { showError('Please enter your name.'); form.elements.name.focus(); return; }
    if (!/^(\+?91|0)?[6-9]\d{9}$/.test(payload.phone.replace(/[\s-]/g, ''))) {
      showError('Please enter a valid 10-digit mobile number.');
      form.elements.phone.focus();
      return;
    }
    if (payload.address.trim().length < 5) { showError('Please enter your delivery address.'); form.elements.address.focus(); return; }

    const button = $('#submitBtn');
    button.disabled = true;
    button.textContent = 'Generating bill...';
    try {
      const response = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      let data = {};
      try { data = await response.json(); } catch (e) { /* ignore */ }
      if (!response.ok) { throw new Error(data.error || 'Something went wrong. Please try again.'); }
      try { localStorage.setItem('ssc_last_order', JSON.stringify({ order_no: data.order_no, token: data.token })); } catch (e) { /* ignore */ }
      cart = [];
      saveCart();
      window.location.href = data.url;
    } catch (err) {
      showError(err.message || 'Could not reach the server. Please check your internet and try again.');
      button.disabled = false;
      button.textContent = 'Generate bill';
    }
  });

  /* ---------- Returning visitor ---------- */
  try {
    const last = JSON.parse(localStorage.getItem('ssc_last_order') || 'null');
    if (last && last.token && last.order_no) {
      $('#lastOrderLink').href = '/order/' + encodeURIComponent(last.token);
      $('#lastOrderText').textContent = last.order_no;
      $('#lastOrder').hidden = false;
    }
  } catch (e) { /* ignore */ }

  renderCart();
})();
