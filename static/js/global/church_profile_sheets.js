// Mobile profile overlays: wall stays; About / photos / Sunday slide over it.
(function () {
  const root = document.querySelector('.profile-shell');
  if (!root) return;

  function sheetEl(id) {
    return document.getElementById('profile-sheet-' + id);
  }

  function closeSheets() {
    root.querySelectorAll('.profile-sheet').forEach((el) => {
      el.hidden = true;
    });
    document.body.classList.remove('profile-sheet-open');
    root.querySelectorAll('.profile-mobile-tabs [data-sheet]').forEach((btn) => {
      btn.classList.remove('is-on');
    });
    const wallBtn = root.querySelector('.profile-mobile-tabs [data-close-sheet]');
    wallBtn?.classList.add('is-on');
  }

  function openSheet(id) {
    const el = sheetEl(id);
    if (!el) return;
    root.querySelectorAll('.profile-sheet').forEach((s) => { s.hidden = true; });
    el.hidden = false;
    document.body.classList.add('profile-sheet-open');
    root.querySelectorAll('.profile-mobile-tabs button').forEach((btn) => {
      btn.classList.toggle('is-on', btn.getAttribute('data-sheet') === id);
    });
    el.querySelector('.profile-sheet-x')?.focus();
  }

  root.addEventListener('click', (e) => {
    const opener = e.target.closest('[data-sheet]');
    if (opener && opener.getAttribute('data-sheet')) {
      e.preventDefault();
      openSheet(opener.getAttribute('data-sheet'));
      return;
    }
    if (e.target.closest('[data-close-sheet]')) {
      e.preventDefault();
      closeSheets();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSheets();
  });
})();

(function () {
  function closeFamilyPops(except) {
    document.querySelectorAll('details.family-add-pop[open]').forEach((d) => {
      if (d !== except) d.removeAttribute('open');
    });
  }
  document.addEventListener('click', (e) => {
    const pop = e.target.closest('details.family-add-pop');
    if (!pop) closeFamilyPops(null);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeFamilyPops(null);
  });
})();
