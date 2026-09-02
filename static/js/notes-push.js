/* Optional Web Push for Notes. Needs HTTPS or localhost. Never includes note text. */
(function () {
  var script = document.currentScript;
  var vapid = (script && script.getAttribute('data-vapid')) || '';
  var btn = document.getElementById('note-push-btn');
  var status = document.getElementById('note-push-status');
  function say(msg) {
    if (status) status.textContent = msg || '';
  }
  function urlBase64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var raw = atob(base64);
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }
  function csrf() {
    var el = document.querySelector('meta[name="csrf-token"]');
    if (el) return el.getAttribute('content') || '';
    var inp = document.querySelector('input[name="csrf_token"]');
    return inp ? inp.value : '';
  }
  async function subscribe() {
    var reg = await navigator.serviceWorker.ready;
    var sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapid)
    });
    var res = await fetch('/church/push/subscribe', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf(),
        'X-Requested-With': 'fetch'
      },
      body: JSON.stringify(sub.toJSON())
    });
    if (!res.ok) throw new Error('save failed');
    say('Phone alerts are on for this device.');
    if (btn) btn.hidden = true;
  }
  if (!btn) return;
  if (!vapid || !('serviceWorker' in navigator) || !('PushManager' in window)) {
    say('Phone alerts need an installed app on HTTPS.');
    return;
  }
  if (!(window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
    say('Phone alerts need HTTPS (or localhost). Email alerts still work.');
    return;
  }
  btn.hidden = false;
  btn.addEventListener('click', function () {
    Notification.requestPermission().then(function (perm) {
      if (perm !== 'granted') {
        say('Permission was not granted.');
        return;
      }
      subscribe().catch(function () {
        say('Could not turn on phone alerts.');
      });
    });
  });
})();
