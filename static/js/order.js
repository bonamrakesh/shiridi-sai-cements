/* Customer bill page: watches for the admin's decision and notifies the customer. */
(function () {
  'use strict';

  const root = document.getElementById('order-root');
  if (!root) { return; }

  const token = root.dataset.token;
  const status = root.dataset.status;

  try {
    localStorage.setItem('ssc_last_order', JSON.stringify({ order_no: root.dataset.orderNo, token: token }));
  } catch (e) { /* ignore */ }

  const printBtn = document.getElementById('printBtn');
  if (printBtn) { printBtn.addEventListener('click', () => window.print()); }

  if (status !== 'pending') { return; }

  // Optional device notification
  const notifyBtn = document.getElementById('notifyBtn');
  if (notifyBtn && 'Notification' in window && Notification.permission === 'default') {
    notifyBtn.hidden = false;
    notifyBtn.addEventListener('click', () => {
      Notification.requestPermission().then(() => { notifyBtn.hidden = true; });
    });
  }

  let finished = false;

  async function check() {
    if (finished) { return; }
    try {
      const response = await fetch('/api/order/' + encodeURIComponent(token) + '/status', { cache: 'no-store' });
      if (!response.ok) { return; }
      const data = await response.json();
      if (data.status && data.status !== 'pending') {
        finished = true;
        const ready = data.status === 'approved';
        document.title = ready ? 'Your bill is ready' : document.title;
        if ('Notification' in window && Notification.permission === 'granted') {
          try {
            new Notification('Shiridi Sai Cements', {
              body: ready ? 'Your bill is ready. Prices have been calculated.' : 'There is an update on your booking.',
            });
          } catch (e) { /* ignore */ }
        }
        window.location.reload();
      }
    } catch (e) { /* network hiccup, try again on the next tick */ }
  }

  setInterval(check, 6000);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') { check(); }
  });
})();
