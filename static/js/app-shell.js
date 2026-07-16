/**
 * MyVine OS - Minimal App Shell JS
 * Makes the experience feel more like a native phone app / webapp.
 * - Better bottom nav tap feedback + instant active state (no full reload flash)
 * - Detects if launched as standalone PWA / installed app
 * - Adds body.standalone + body.phone-app classes
 * - Safe area + viewport helpers
 * - Optional lightweight beforeinstallprompt support
 */
(function() {
  function enhanceBottomNav() {
    const nav = document.querySelector('.bottom-nav');
    if (!nav) return;

    nav.addEventListener('click', function(e) {
      const link = e.target.closest('a.bottom-nav-item, a[data-nav-direct]');
      if (!link || !link.href) return;

      // Instant visual active state (feels native)
      nav.querySelectorAll('a.bottom-nav-item, a[data-nav-direct]').forEach(a => a.classList.remove('active'));
      link.classList.add('active');

      // Small haptic-like scale (if supported)
      link.style.transition = 'transform 60ms ease';
      link.style.transform = 'scale(0.92)';
      setTimeout(() => {
        link.style.transform = '';
      }, 120);
    }, { passive: true });
  }

  /**
   * Mobile bottom-nav sheets: Community / Office / My Stuff / More
   * open a full list of links so nothing is desktop-only.
   */
  function enhanceNavSheets() {
    const triggers = document.querySelectorAll('[data-nav-sheet]');
    if (!triggers.length) return;

    const backdrop = document.getElementById('nav-sheet-backdrop');
    let openSheet = null;
    let openTrigger = null;

    function closeSheet() {
      if (openSheet) {
        openSheet.classList.remove('is-open');
        // allow animation then hide
        const sheet = openSheet;
        setTimeout(() => {
          if (!sheet.classList.contains('is-open')) {
            sheet.hidden = true;
            sheet.setAttribute('hidden', '');
          }
        }, 220);
      }
      if (openTrigger) {
        openTrigger.classList.remove('is-open');
        openTrigger.setAttribute('aria-expanded', 'false');
      }
      if (backdrop) {
        backdrop.hidden = true;
        backdrop.setAttribute('hidden', '');
        backdrop.setAttribute('aria-hidden', 'true');
      }
      document.body.classList.remove('nav-sheet-open');
      openSheet = null;
      openTrigger = null;
    }

    function openSheetFor(trigger) {
      const id = trigger.getAttribute('data-nav-sheet');
      if (!id) return;
      const sheet = document.getElementById('nav-sheet-' + id);
      if (!sheet) return;

      // Close any other open sheet first
      if (openSheet && openSheet !== sheet) {
        openSheet.classList.remove('is-open');
        openSheet.hidden = true;
        openSheet.setAttribute('hidden', '');
      }
      if (openTrigger && openTrigger !== trigger) {
        openTrigger.classList.remove('is-open');
        openTrigger.setAttribute('aria-expanded', 'false');
      }

      sheet.hidden = false;
      sheet.removeAttribute('hidden');
      // force reflow for transition
      void sheet.offsetWidth;
      sheet.classList.add('is-open');
      trigger.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
      if (backdrop) {
        backdrop.hidden = false;
        backdrop.removeAttribute('hidden');
        backdrop.setAttribute('aria-hidden', 'false');
      }
      document.body.classList.add('nav-sheet-open');
      openSheet = sheet;
      openTrigger = trigger;
    }

    triggers.forEach((trigger) => {
      trigger.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const isOpen = trigger.classList.contains('is-open');
        if (isOpen) closeSheet();
        else openSheetFor(trigger);
      });
    });

    document.querySelectorAll('[data-nav-sheet-close]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        closeSheet();
      });
    });

    if (backdrop) {
      backdrop.addEventListener('click', closeSheet);
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeSheet();
    });

    // Close when navigating via a sheet link
    document.querySelectorAll('.nav-sheet-link').forEach((link) => {
      link.addEventListener('click', () => {
        // leave open briefly for tap feedback, then navigate
      });
    });
  }

  function enhanceTopNav() {
    const nav = document.querySelector('.top-nav');
    if (!nav) return;
    const currentPath = window.location.pathname;
    nav.querySelectorAll('a').forEach(a => {
      const href = a.getAttribute('href') || '';
      if (href && href !== '#' && currentPath.startsWith(href)) {
        a.classList.add('active');
      }
    });
  }

  function enhanceNavGroups() {
    const groups = document.querySelectorAll('.nav-group');
    if (!groups.length) return;

    groups.forEach(group => {
      const toggle = group.querySelector('.nav-group-toggle');
      if (!toggle) return;

      toggle.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = group.classList.contains('open');
        groups.forEach(g => {
          g.classList.remove('open');
          const t = g.querySelector('.nav-group-toggle');
          if (t) t.setAttribute('aria-expanded', 'false');
        });
        if (!isOpen) {
          group.classList.add('open');
          toggle.setAttribute('aria-expanded', 'true');
        }
      });
    });

    document.addEventListener('click', () => {
      groups.forEach(group => {
        group.classList.remove('open');
        const toggle = group.querySelector('.nav-group-toggle');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
      });
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        groups.forEach(group => {
          group.classList.remove('open');
          const toggle = group.querySelector('.nav-group-toggle');
          if (toggle) toggle.setAttribute('aria-expanded', 'false');
        });
      }
    });
  }

  function detectStandalone() {
    const isStandalone = 
      window.matchMedia('(display-mode: standalone)').matches ||
      window.matchMedia('(display-mode: minimal-ui)').matches ||
      window.navigator.standalone === true ||
      document.referrer.includes('android-app://');

    const isNarrow = window.innerWidth < 768;

    if (isStandalone) {
      document.body.classList.add('standalone');
      document.documentElement.classList.add('standalone');
      // Desktop installed app vs phone installed app (cleaner chrome rules)
      if (isNarrow) {
        document.body.classList.add('phone-app', 'standalone-phone');
      } else {
        document.body.classList.add('standalone-desktop');
      }
    } else if (isNarrow) {
      document.body.classList.add('phone-app');
    }
  }

  /**
   * Register a security-conscious service worker.
   * Caches only /static/* assets — never HTML, never POSTs, never API JSON.
   * Safe with multi-device logins (cookies still per-device; cache is public CSS/JS only).
   */
  function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    // Only on secure contexts (https or localhost)
    if (!(window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
      return;
    }
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' })
        .then((reg) => {
          // Quiet update check
          try { reg.update(); } catch (e) { /* ignore */ }
        })
        .catch(() => {
          // Non-fatal — app still works without SW
        });
    });
  }

  function addThemeColorMetaIfMissing() {
    // Already injected in templates, but safe guard
    if (!document.querySelector('meta[name="theme-color"]')) {
      const m = document.createElement('meta');
      m.name = 'theme-color';
      m.content = '#00ffff';
      document.head.appendChild(m);
    }
  }

  // Very light beforeinstallprompt helper (shows nothing intrusive by default,
  // but marks the page so you can trigger a custom banner later if desired)
  let deferredPrompt;
  function setupInstallPrompt() {
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredPrompt = e;
      document.body.dataset.canInstall = 'true';
      // You can listen for this in console or add a small UI later:
      // console.log('[MyVine] App can be installed');
    });

    // Example: expose a global you can call from console or a button
    window.MyVineInstall = async function() {
      if (!deferredPrompt) return false;
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      deferredPrompt = null;
      return outcome === 'accepted';
    };
  }

  // Boot
  function init() {
    enhanceBottomNav();
    enhanceNavSheets();
    enhanceTopNav();
    enhanceNavGroups();
    detectStandalone();
    addThemeColorMetaIfMissing();
    setupInstallPrompt();
    registerServiceWorker();

    // Make sure safe-area padding is respected even if CSS vars lag
    if (window.visualViewport) {
      document.documentElement.style.setProperty('--safe-bottom', (window.visualViewport.height ? 'env(safe-area-inset-bottom)' : '0px'));
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
