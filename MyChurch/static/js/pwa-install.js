/**
 * Install-to-home / desktop app prompt for MyVineOS (self-host + Cloud).
 * Remembers Not now / Don't ask again per church URL + device.
 * Cloud: each /{slug}/ is its own install (scope + id from data-pwa-*).
 */
(function () {
  const root = document.documentElement;
  if (root.getAttribute("data-pwa-off") === "1") return;

  const HOST = (location.hostname || "").toLowerCase();
  const SCOPE = (root.getAttribute("data-pwa-scope") || "/").trim() || "/";
  const APP = (root.getAttribute("data-pwa-name") || "").trim() || "MyVineOS";
  const CHOICE_URL = root.getAttribute("data-pwa-choice") || (SCOPE.replace(/\/?$/, "/") + "pwa/choice");
  const SW_URL = root.getAttribute("data-pwa-sw") || (SCOPE.replace(/\/?$/, "/") + "sw.js");
  const SNOOZE_MS = 14 * 24 * 60 * 60 * 1000;
  const FINAL = { installed: 1, never: 1, dismissed: 1, no: 1, yes: 1 };

  function surface() {
    const coarse = window.matchMedia("(pointer: coarse)").matches;
    const narrow =
      Math.min(window.innerWidth || 900, (window.screen && window.screen.width) || 900) < 768;
    return coarse || narrow ? "phone" : "desktop";
  }

  function storageKey() {
    return "pwaChoice:" + HOST + ":" + SCOPE + ":" + surface();
  }

  function cookieName() {
    return "pwa_" + surface() + "_" + SCOPE.replace(/[^a-z0-9]+/gi, "_").slice(0, 24);
  }

  function sessionKey() {
    return "pwaShown:" + HOST + ":" + SCOPE + ":" + surface();
  }

  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: window-controls-overlay)").matches ||
      window.matchMedia("(display-mode: minimal-ui)").matches ||
      window.navigator.standalone === true
    );
  }

  function needsManualHint() {
    const ua = navigator.userAgent || "";
    const iOS = /iphone|ipad|ipod/i.test(ua);
    const safari = /safari/i.test(ua) && !/chrome|crios|android|edg|fxios/i.test(ua);
    return iOS || safari;
  }

  function parseChoice(raw) {
    const v = String(raw || "").trim().toLowerCase();
    if (!v) return "";
    if (FINAL[v]) return v === "yes" ? "installed" : v === "no" || v === "dismissed" ? "never" : v;
    if (v.indexOf("snooze:") === 0) {
      const ts = parseInt(v.slice(7), 10);
      if (Number.isFinite(ts) && Date.now() < ts) return v;
      return "";
    }
    return "";
  }

  function alreadyDecided(choice) {
    return !!parseChoice(choice);
  }

  function readLocalChoice() {
    try {
      const v = parseChoice(localStorage.getItem(storageKey()));
      if (v) return v;
    } catch (e) {}
    try {
      const m = document.cookie.match(new RegExp("(?:^|; )" + cookieName() + "=([^;]*)"));
      if (m) return parseChoice(decodeURIComponent(m[1]));
    } catch (e) {}
    return "";
  }

  function writeLocalChoice(choice) {
    try {
      localStorage.setItem(storageKey(), choice);
    } catch (e) {}
    try {
      const secure = location.protocol === "https:" ? ";Secure" : "";
      document.cookie =
        cookieName() +
        "=" +
        encodeURIComponent(choice) +
        ";path=" +
        SCOPE +
        ";max-age=31536000;SameSite=Lax" +
        secure;
    } catch (e) {}
  }

  function persistChoice(choice) {
    writeLocalChoice(choice);
    fetch(CHOICE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ surface: surface(), choice: choice, scope: SCOPE }),
    }).catch(function () {});
  }

  function markShownThisVisit() {
    try {
      sessionStorage.setItem(sessionKey(), "1");
    } catch (e) {}
  }

  function shownThisVisit() {
    try {
      return sessionStorage.getItem(sessionKey()) === "1";
    } catch (e) {
      return false;
    }
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    if (!(window.isSecureContext || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
      return;
    }
    window.addEventListener("load", function () {
      navigator.serviceWorker.register(SW_URL, { scope: SCOPE }).catch(function () {});
    });
  }

  let deferredPrompt = null;

  function hideBanner() {
    const el = document.getElementById("myvine-pwa-install");
    if (el) el.remove();
  }

  function showBanner(mode) {
    if (document.getElementById("myvine-pwa-install")) return;
    const phone = surface() === "phone";
    const title = phone ? "Add " + APP + " to your home screen" : "Install " + APP + " as an app";
    const hint =
      mode === "prompt"
        ? phone
          ? "Opens like an app — no browser chrome."
          : "Opens in its own window — no browser tabs."
        : phone
          ? "Safari: Share → Add to Home Screen. Chrome: menu → Install app."
          : "Chrome or Edge: use the install icon in the address bar. Safari: File → Add to Dock.";
    const wrap = document.createElement("div");
    wrap.id = "myvine-pwa-install";
    wrap.setAttribute("role", "dialog");
    wrap.innerHTML =
      '<div class="myvine-pwa-card">' +
        '<div class="myvine-pwa-copy">' +
          "<strong>" + title + "</strong>" +
          "<span>" + hint + "</span>" +
        "</div>" +
        '<div class="myvine-pwa-actions">' +
          (mode === "prompt" ? '<button type="button" class="myvine-pwa-go" id="myvine-pwa-go">Install</button>' : "") +
          '<button type="button" class="myvine-pwa-skip" id="myvine-pwa-skip">Not now</button>' +
          '<button type="button" class="myvine-pwa-never" id="myvine-pwa-never">No thanks</button>' +
        "</div>" +
      "</div>";
    if (!document.getElementById("myvine-pwa-style")) {
      const style = document.createElement("style");
      style.id = "myvine-pwa-style";
      style.textContent =
        "#myvine-pwa-install{position:fixed;right:1rem;bottom:4.5rem;z-index:1080;max-width:22rem;font-family:system-ui,-apple-system,sans-serif}" +
        ".myvine-pwa-card{background:#141a21;color:#e9ecef;border:1px solid rgba(0,255,255,.35);border-radius:12px;padding:.85rem 1rem;box-shadow:0 10px 30px rgba(0,0,0,.45);display:flex;flex-direction:column;gap:.65rem}" +
        ".myvine-pwa-copy{display:flex;flex-direction:column;gap:.25rem;font-size:.88rem;line-height:1.35}" +
        ".myvine-pwa-copy strong{color:#7ef9ff}" +
        ".myvine-pwa-copy span{color:#adb5bd;font-size:.8rem}" +
        ".myvine-pwa-actions{display:flex;flex-wrap:wrap;gap:.45rem;justify-content:flex-end}" +
        ".myvine-pwa-go,.myvine-pwa-skip,.myvine-pwa-never{border-radius:8px;padding:.4rem .75rem;font-size:.85rem;font-weight:600;cursor:pointer}" +
        ".myvine-pwa-go{border:0;background:#00b8c4;color:#041416}" +
        ".myvine-pwa-skip{border:1px solid #495057;background:transparent;color:#ced4da}" +
        ".myvine-pwa-never{border:0;background:transparent;color:#868e96;text-decoration:underline;font-weight:500}";
      document.head.appendChild(style);
    }
    document.body.appendChild(wrap);
    markShownThisVisit();
    document.getElementById("myvine-pwa-skip").addEventListener("click", function () {
      persistChoice("snooze:" + (Date.now() + SNOOZE_MS));
      hideBanner();
    });
    document.getElementById("myvine-pwa-never").addEventListener("click", function () {
      persistChoice("never");
      hideBanner();
    });
    const go = document.getElementById("myvine-pwa-go");
    if (go) {
      go.addEventListener("click", async function () {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        try {
          const { outcome } = await deferredPrompt.userChoice;
          persistChoice(outcome === "accepted" ? "installed" : "snooze:" + (Date.now() + SNOOZE_MS));
        } catch (e) {
          persistChoice("snooze:" + (Date.now() + SNOOZE_MS));
        }
        deferredPrompt = null;
        hideBanner();
      });
    }
  }

  function maybeShow(mode) {
    if (isStandalone() || alreadyDecided(readLocalChoice()) || shownThisVisit()) return;
    showBanner(mode);
  }

  function markInstalled() {
    persistChoice("installed");
    hideBanner();
  }

  function setupInstallPrompt() {
    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault();
      deferredPrompt = e;
      document.body.dataset.canInstall = "true";
      maybeShow("prompt");
    });

    window.MyVineInstall = async function () {
      if (!deferredPrompt) return false;
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      deferredPrompt = null;
      persistChoice(outcome === "accepted" ? "installed" : "snooze:" + (Date.now() + SNOOZE_MS));
      hideBanner();
      return outcome === "accepted";
    };

    window.addEventListener("appinstalled", function () {
      deferredPrompt = null;
      markInstalled();
    });

    if (navigator.getInstalledRelatedApps) {
      navigator.getInstalledRelatedApps().then(function (apps) {
        if (apps && apps.length) markInstalled();
      }).catch(function () {});
    }

    window.addEventListener("load", function () {
      setTimeout(function () {
        if (isStandalone() || alreadyDecided(readLocalChoice()) || shownThisVisit()) return;
        if (deferredPrompt || document.getElementById("myvine-pwa-install")) return;
        if (needsManualHint()) maybeShow("hint");
      }, 1800);
    });
  }

  function boot() {
    registerServiceWorker();
    if (isStandalone()) {
      document.documentElement.classList.add("standalone");
      if (document.body) document.body.classList.add("standalone");
      writeLocalChoice("installed");
      persistChoice("installed");
      return;
    }
    if (alreadyDecided(readLocalChoice())) return;

    const start = function () {
      if (alreadyDecided(readLocalChoice())) return;
      setupInstallPrompt();
    };

    fetch(CHOICE_URL + (CHOICE_URL.indexOf("?") >= 0 ? "&" : "?") + "surface=" + encodeURIComponent(surface()), {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then(function (r) {
        return r.ok ? r.json() : {};
      })
      .then(function (data) {
        const c = parseChoice(data && data.choice);
        if (alreadyDecided(c)) {
          writeLocalChoice(c);
          return;
        }
        start();
      })
      .catch(start);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
