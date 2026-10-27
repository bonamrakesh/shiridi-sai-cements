/* Admin pages: live new-order alert, price entry, approve / reject / reopen. */
(function () {
  'use strict';

  const meta = document.querySelector('meta[name="csrf-token"]');
  const csrf = meta ? meta.content : '';
  const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });

  async function post(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify(body),
    });
    let data = {};
    try { data = await response.json(); } catch (e) { /* ignore */ }
    if (response.status === 401) { window.location.href = '/admin/login'; throw new Error('Please log in again.'); }
    if (!response.ok) { throw new Error(data.error || 'Something went wrong. Please try again.'); }
    return data;
  }

  /* ---------- Dashboard: watch for new bookings ---------- */
  const dash = document.getElementById('admin-dashboard');
  if (dash) {
    const known = Number(dash.dataset.latest || 0);
    const toast = document.getElementById('newToast');
    const baseTitle = document.title;

    setInterval(async () => {
      try {
        const response = await fetch('/api/admin/summary', { credentials: 'same-origin', cache: 'no-store' });
        if (!response.ok) { return; }
        const data = await response.json();
        if (data.latest_id > known) {
          if (toast) { toast.hidden = false; }
          document.title = '(' + data.pending + ' pending) ' + baseTitle;
        }
      } catch (e) { /* ignore */ }
    }, 10000);
  }

  /* ---------- Order page: prices and actions ---------- */
  const root = document.getElementById('admin-order');
  if (!root) { return; }

  const orderId = root.dataset.id;
  const inputs = Array.from(root.querySelectorAll('.price-table .price-input[data-item-id]'));
  const other = document.getElementById('otherCharges');
  const note = document.getElementById('adminNote');
  const message = document.getElementById('adminMsg');

  function recalc() {
    if (inputs.length === 0) { return; }
    let subtotal = 0;
    inputs.forEach((input) => {
      const price = parseFloat(input.value);
      const qty = parseFloat(input.dataset.qty);
      const cell = document.getElementById('amt-' + input.dataset.itemId);
      if (isFinite(price) && price >= 0) {
        const amount = Math.round(price * qty * 100) / 100;
        subtotal += amount;
        cell.textContent = money.format(amount);
      } else {
        cell.textContent = '—';
      }
    });
    const extra = other ? (parseFloat(other.value) || 0) : 0;
    document.getElementById('subtotalCell').textContent = money.format(subtotal);
    document.getElementById('totalCell').textContent = money.format(subtotal + (extra > 0 ? extra : 0));
  }

  inputs.forEach((input) => input.addEventListener('input', recalc));
  if (other) { other.addEventListener('input', recalc); }
  recalc();

  function show(text, isError) {
    message.textContent = text;
    message.hidden = false;
    message.className = isError ? 'form-error' : 'form-ok';
  }

  const confirmText = {
    approve: 'Approve these prices and send the bill to the customer?',
    reject: 'Reject this order? The customer will be told it could not be confirmed.',
    reopen: 'Reopen this order for editing? The customer will see the waiting message again.',
  };

  Array.from(root.querySelectorAll('[data-action]')).forEach((button) => {
    button.addEventListener('click', async () => {
      const action = button.dataset.action;
      if (confirmText[action] && !window.confirm(confirmText[action])) { return; }

      const prices = {};
      inputs.forEach((input) => { prices[input.dataset.itemId] = input.value; });
      const all = Array.from(root.querySelectorAll('[data-action]'));
      all.forEach((b) => { b.disabled = true; });
      try {
        const data = await post('/api/admin/orders/' + orderId, {
          action: action,
          prices: prices,
          other_charges: other ? other.value : '',
          admin_note: note ? note.value : '',
        });
        show(data.message || 'Done.', false);
        setTimeout(() => window.location.reload(), 900);
      } catch (err) {
        show(err.message, true);
        all.forEach((b) => { b.disabled = false; });
      }
    });
  });

  const printAdmin = document.getElementById('printAdminBill');
  if (printAdmin) { printAdmin.addEventListener('click', () => window.print()); }
})();
