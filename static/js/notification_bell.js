/* Notification bell: load the list when opened; each item is a POST form
 * (marks read, then redirects to the post). Uses the page CSRF token. */
(function () {
  function token() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? (m.getAttribute('content') || '') : '';
  }
  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }
  function setCount(bell, n) {
    var b = bell.querySelector('[data-notif-count]');
    if (!b) return;
    if (n > 0) { b.textContent = n > 99 ? '99+' : String(n); b.hidden = false; }
    else { b.hidden = true; }
  }
  function render(bell, data) {
    var list = bell.querySelector('[data-notif-list]');
    if (!list) return;
    var items = (data && data.items) || [];
    setCount(bell, (data && data.unread) || 0);
    if (!items.length) { list.innerHTML = '<li class="notif-empty">Nothing new yet.</li>'; return; }
    var base = bell.getAttribute('data-open-base') || '/church/notifications';
    var csrf = esc(token());
    list.innerHTML = items.map(function (n) {
      var ico = n.pic_url
        ? '<img src="' + esc(n.pic_url) + '" alt="">'
        : '<i class="fa-solid ' + esc(n.icon || 'fa-bell') + '" aria-hidden="true"></i>';
      return '<li><form method="post" action="' + esc(base) + '/' + Number(n.id) + '/open">' +
        '<input type="hidden" name="csrf_token" value="' + csrf + '">' +
        '<button type="submit" class="notif-item' + (n.unread ? ' is-unread' : '') + '">' +
        '<span class="notif-ico">' + ico + '</span>' +
        '<span class="notif-text"><strong>' + esc(n.actor) + '</strong> ' + esc(n.text) +
        (n.body ? '<span class="notif-body">' + esc(n.body) + '</span>' : '') +
        '<span class="notif-when">' + esc(n.when) + '</span></span>' +
        '</button></form></li>';
    }).join('');
  }
  function load(bell) {
    var url = bell.getAttribute('data-feed-url');
    if (!url) return;
    fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) { if (data) render(bell, data); })
      .catch(function () {
        var list = bell.querySelector('[data-notif-list]');
        if (list) list.innerHTML = '<li class="notif-empty">Could not load notifications.</li>';
      });
  }
  function init() {
    document.querySelectorAll('details.notif-bell').forEach(function (bell) {
      if (bell.dataset.notifReady) return;
      bell.dataset.notifReady = '1';
      bell.addEventListener('toggle', function () { if (bell.open) load(bell); });
      document.addEventListener('click', function (e) {
        if (bell.open && !bell.contains(e.target)) bell.open = false;
      });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
