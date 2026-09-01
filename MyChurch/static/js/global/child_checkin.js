/* Child Check-In kiosk — search, multi-select, check-in, print labels */

(function () {
  'use strict';

  var root = document.getElementById('cci-kiosk');
  if (!root) return;

  var searchUrl = root.dataset.searchUrl;
  var checkinUrl = root.dataset.checkinUrl;
  var labelsUrl = root.dataset.labelsUrl;
  var rooms = [];
  try {
    rooms = JSON.parse(root.dataset.rooms || '[]');
  } catch (e) {
    rooms = [];
  }

  var input = document.getElementById('cci-search');
  var resultsEl = document.getElementById('cci-results');
  var selected = {}; // id -> {child, classroom_id}
  var timer = null;
  var lastResults = [];

  function csrf() {
    var el = document.querySelector('input[name="csrf_token"]');
    return el ? el.value : '';
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function roomOptions(selectedId) {
    var html = '<option value="">Room…</option>';
    rooms.forEach(function (r) {
      html +=
        '<option value="' +
        r.id +
        '"' +
        (String(selectedId) === String(r.id) ? ' selected' : '') +
        '>' +
        escapeHtml(r.name) +
        (r.live_count != null ? ' (' + r.live_count + ')' : '') +
        '</option>';
    });
    return html;
  }

  function renderResults(list) {
    lastResults = list || [];
    if (!lastResults.length) {
      resultsEl.innerHTML =
        '<div class="glass-panel" style="padding:1rem;text-align:center;opacity:0.7;">No matches — try last name, family PIN, or phone digits.</div>';
      return;
    }
    var html = '';
    lastResults.forEach(function (c) {
      var isSel = !!selected[c.id];
      var isIn = c.already_in;
      html +=
        '<div class="cci-kid-card' +
        (isSel ? ' is-selected' : '') +
        (isIn ? ' is-in' : '') +
        '" data-id="' +
        c.id +
        '">' +
        '<input type="checkbox" class="cci-kid-check" ' +
        (isSel ? 'checked' : '') +
        (isIn ? ' disabled' : '') +
        '>' +
        '<div class="cci-kid-meta">' +
        '<strong>' +
        escapeHtml(c.display_name) +
        '</strong>' +
        '<span>' +
        escapeHtml(c.age_label || '') +
        (c.guardians && c.guardians.length
          ? ' · ' +
            escapeHtml(
              c.guardians
                .map(function (g) {
                  return g.display;
                })
                .slice(0, 2)
                .join(', ')
            )
          : '') +
        '</span>' +
        (c.allergies ? '<div class="cci-allergy">⚠ ' + escapeHtml(c.allergies) + '</div>' : '') +
        (isIn
          ? '<div style="font-size:0.8rem;color:#86efac;margin-top:0.2rem;">Already in ' +
            escapeHtml(c.active_room || 'a room') +
            ' · code ' +
            escapeHtml(c.active_code || '') +
            '</div>'
          : '') +
        '</div>' +
        (isIn
          ? ''
          : '<select class="form-input cci-room-select" data-room-for="' +
            c.id +
            '">' +
            roomOptions(selected[c.id] ? selected[c.id].classroom_id : c.default_classroom_id) +
            '</select>') +
        '</div>';
    });
    resultsEl.innerHTML = html;
  }

  function doSearch(q) {
    if (!q) {
      resultsEl.innerHTML = '';
      return;
    }
    resultsEl.innerHTML =
      '<div class="glass-panel" style="padding:1rem;text-align:center;opacity:0.6;">Searching…</div>';
    fetch(searchUrl + '?q=' + encodeURIComponent(q), {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        renderResults(data.results || []);
      })
      .catch(function () {
        resultsEl.innerHTML =
          '<div class="glass-panel" style="padding:1rem;color:#fca5a5;">Search failed. Try again.</div>';
      });
  }

  if (input) {
    input.addEventListener('input', function () {
      clearTimeout(timer);
      var q = input.value.trim();
      timer = setTimeout(function () {
        doSearch(q);
      }, 220);
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        clearTimeout(timer);
        doSearch(input.value.trim());
      }
    });
  }

  resultsEl.addEventListener('click', function (e) {
    var card = e.target.closest('.cci-kid-card');
    if (!card || card.classList.contains('is-in')) return;
    if (e.target.tagName === 'SELECT') return;
    var id = parseInt(card.getAttribute('data-id'), 10);
    var child = lastResults.find(function (c) {
      return c.id === id;
    });
    if (!child) return;
    if (selected[id]) {
      delete selected[id];
    } else {
      var sel = card.querySelector('select');
      selected[id] = {
        child: child,
        classroom_id: sel ? sel.value : child.default_classroom_id,
      };
    }
    renderResults(lastResults);
    updateBar();
  });

  resultsEl.addEventListener('change', function (e) {
    if (e.target.matches('select[data-room-for]')) {
      var id = parseInt(e.target.getAttribute('data-room-for'), 10);
      if (selected[id]) selected[id].classroom_id = e.target.value;
      else {
        var child = lastResults.find(function (c) {
          return c.id === id;
        });
        if (child) {
          selected[id] = { child: child, classroom_id: e.target.value };
          renderResults(lastResults);
        }
      }
      updateBar();
    }
  });

  var bar = document.getElementById('cci-bar');
  var barCount = document.getElementById('cci-bar-count');
  var checkinBtn = document.getElementById('cci-checkin-btn');
  var successEl = document.getElementById('cci-success');

  function updateBar() {
    var n = Object.keys(selected).length;
    if (barCount) barCount.textContent = n ? n + ' selected' : 'Select kids to check in';
    if (checkinBtn) checkinBtn.disabled = n === 0;
    if (bar) bar.style.display = n ? 'flex' : 'none';
  }

  if (checkinBtn) {
    checkinBtn.addEventListener('click', function () {
      var ids = Object.keys(selected);
      if (!ids.length) return;
      checkinBtn.disabled = true;
      checkinBtn.textContent = 'Checking in…';
      var classrooms = {};
      ids.forEach(function (id) {
        classrooms[id] = selected[id].classroom_id || null;
      });
      var guardianName = (document.getElementById('cci-guardian-name') || {}).value || '';
      fetch(checkinUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-CSRFToken': csrf(),
        },
        body: JSON.stringify({
          child_ids: ids.map(Number),
          classrooms: classrooms,
          guardian_name: guardianName,
          event_label: (document.getElementById('cci-event') || {}).value || '',
          csrf_token: csrf(),
        }),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          checkinBtn.textContent = 'Check in & print labels';
          checkinBtn.disabled = false;
          if (!data.checkins || !data.checkins.length) {
            alert((data.errors && data.errors.join('\n')) || 'Check-in failed.');
            return;
          }
          selected = {};
          updateBar();
          showSuccess(data.checkins, data.errors);
          if (input) {
            input.value = '';
            resultsEl.innerHTML = '';
          }
        })
        .catch(function () {
          checkinBtn.textContent = 'Check in & print labels';
          checkinBtn.disabled = false;
          alert('Network error during check-in.');
        });
    });
  }

  function showSuccess(checkins, errors) {
    if (!successEl) return;
    var ids = checkins.map(function (c) {
      return c.id;
    });
    var html =
      '<div class="glass-panel" style="padding:1.1rem;margin-bottom:1rem;">' +
      '<h2 style="margin:0 0 0.5rem;color:var(--primary);">✓ Checked in</h2>' +
      '<p style="margin:0 0 0.75rem;opacity:0.8;">Give parents the code on each label. Print now or save for the room board.</p>' +
      '<div class="cci-success-grid">';
    checkins.forEach(function (c) {
      html +=
        '<div class="cci-code-card glass-panel">' +
        '<div class="name">' +
        escapeHtml(c.display_name) +
        '</div>' +
        '<div style="opacity:0.75;font-size:0.85rem;">' +
        escapeHtml(c.classroom_name || 'Room') +
        '</div>' +
        '<div class="code">' +
        escapeHtml(c.pickup_code) +
        '</div>' +
        '<div style="font-size:0.75rem;opacity:0.65;">PICKUP CODE</div>' +
        '</div>';
    });
    html +=
      '</div><div style="display:flex;flex-wrap:wrap;gap:0.5rem;margin-top:1rem;justify-content:center;">' +
      '<a class="btn btn-primary" href="' +
      labelsUrl +
      '?ids=' +
      ids.join(',') +
      '" target="_blank" rel="noopener">Print labels</a>' +
      '<button type="button" class="btn btn-secondary" id="cci-done">Done — next family</button>' +
      '</div>';
    if (errors && errors.length) {
      html +=
        '<p style="color:#fca5a5;margin-top:0.75rem;font-size:0.85rem;">' +
        escapeHtml(errors.join(' · ')) +
        '</p>';
    }
    html += '</div>';
    successEl.innerHTML = html;
    successEl.hidden = false;
    successEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    var done = document.getElementById('cci-done');
    if (done) {
      done.addEventListener('click', function () {
        successEl.hidden = true;
        successEl.innerHTML = '';
        if (input) input.focus();
      });
    }
  }

  // PIN pad
  document.querySelectorAll('[data-pin]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!input) return;
      var v = btn.getAttribute('data-pin');
      if (v === 'clear') input.value = '';
      else if (v === 'back') input.value = input.value.slice(0, -1);
      else input.value += v;
      input.dispatchEvent(new Event('input'));
      input.focus();
    });
  });

  updateBar();
  if (input) input.focus();
})();
