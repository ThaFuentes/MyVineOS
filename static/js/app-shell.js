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
      const link = e.target.closest('a');
      if (!link || !link.href) return;

      // Instant visual active state (feels native)
      nav.querySelectorAll('a').forEach(a => a.classList.remove('active'));
      link.classList.add('active');

      // Small haptic-like scale (if supported)
      link.style.transition = 'transform 60ms ease';
      link.style.transform = 'scale(0.92)';
      setTimeout(() => {
        link.style.transform = '';
      }, 120);
    }, { passive: true });

    // On page load, ensure the server-rendered active state is crisp
    // (server already does class based on endpoint, this just reinforces)
    // Also do a path-based fallback for pages where endpoint matching is imperfect (more native app tab feel)
    const currentPath = window.location.pathname;
    nav.querySelectorAll('a').forEach(a => {
      const href = a.getAttribute('href') || '';
      if (href && currentPath.startsWith(href) && href !== '/') {
        a.classList.add('active');
      } else if (href === '/' && currentPath === '/') {
        a.classList.add('active');
      }
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
      window.navigator.standalone === true ||
      document.referrer.includes('android-app://');

    if (isStandalone) {
      document.body.classList.add('standalone', 'phone-app');
      document.documentElement.classList.add('standalone');
    }

    // Also tag narrow phones for any extra tweaks
    if (window.innerWidth < 768) {
      document.body.classList.add('phone-app');
    }
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
    enhanceTopNav();
    enhanceNavGroups();
    detectStandalone();
    addThemeColorMetaIfMissing();
    setupInstallPrompt();

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
