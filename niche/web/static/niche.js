/* BrakeByWire / Niche — main JS
   Handles: thumbs feedback, mark-as-read, filter tabs, theme accent,
            detail panel, ticker pause-on-hover, search filtering.
   No framework — plain fetch() + DOM manipulation.
*/

(function () {
  'use strict';

  /* ── ACCENT COLOR ─────────────────────────────────────────────────────── */
  const ACCENT_COLORS = {
    red:    { hex: '#E63946', rgb: '230,57,70' },
    blue:   { hex: '#4361EE', rgb: '67,97,238' },
    amber:  { hex: '#F4A261', rgb: '244,162,97' },
    teal:   { hex: '#0d9488', rgb: '13,148,136' },
    purple: { hex: '#7c3aed', rgb: '124,58,237' },
  };

  function applyAccent(color) {
    const c = ACCENT_COLORS[color];
    if (!c) return;
    document.documentElement.style.setProperty('--accent', c.hex);
    document.documentElement.style.setProperty('--accent-rgb', c.rgb);
    document.documentElement.style.setProperty('--accent-dim', `rgba(${c.rgb},0.12)`);
  }

  // Apply saved theme from data attribute set by Flask template
  const savedTheme = document.documentElement.dataset.theme || 'red';
  applyAccent(savedTheme);

  /* ── THEME SWATCHES ───────────────────────────────────────────────────── */
  document.querySelectorAll('.theme-swatch').forEach(btn => {
    btn.addEventListener('click', function () {
      const color = this.dataset.color;
      applyAccent(color);
      document.querySelectorAll('.theme-swatch').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      // Persist via API
      fetch('/preferences/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({ color }),
      });
    });
  });

  /* ── CSRF HELPER ──────────────────────────────────────────────────────── */
  function getCsrf() {
    const el = document.querySelector('meta[name="csrf-token"]');
    return el ? el.content : '';
  }

  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf(),
      },
      body: JSON.stringify(body),
    }).then(r => r.json());
  }

  /* ── MARK AS READ ─────────────────────────────────────────────────────── */
  function markRead(itemId) {
    post('/api/read', { item_id: itemId });
    document.querySelectorAll(`.card[data-id="${itemId}"]`).forEach(card => {
      card.classList.add('is-read');
      const marker = card.querySelector('.card-read-marker');
      if (marker) marker.style.display = '';
    });
  }

  /* ── THUMBS ───────────────────────────────────────────────────────────── */
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('.thumb-btn');
    if (!btn) return;
    e.stopPropagation();
    const card = btn.closest('[data-id]');
    if (!card) return;
    const itemId = card.dataset.id;
    const dir = btn.dataset.dir; // "up" or "down"

    const isActive = btn.classList.contains('active-up') || btn.classList.contains('active-down');
    const signal = isActive ? null : dir;

    post('/api/feedback', { item_id: itemId, signal }).then(() => {
      const thumbs = card.querySelectorAll('.thumb-btn');
      thumbs.forEach(b => { b.classList.remove('active-up', 'active-down'); });
      if (signal) {
        btn.classList.add(dir === 'up' ? 'active-up' : 'active-down');
      }
    });
  });

  /* ── SAVE / BOOKMARK ──────────────────────────────────────────────────── */
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('.save-btn');
    if (!btn) return;
    e.stopPropagation();
    const itemId = btn.dataset.id;
    const saved = btn.classList.contains('saved');
    post('/api/save', { item_id: itemId, saved: !saved }).then(data => {
      if (data.saved !== undefined) {
        btn.classList.toggle('saved', data.saved);
        btn.title = data.saved ? 'Remove from saved' : 'Save for later';
      }
    });
  });

  /* ── DETAIL PANEL ─────────────────────────────────────────────────────── */
  const detailPanel = document.getElementById('detail-panel');
  const detailOverlay = document.getElementById('detail-overlay');

  function closeDetail() {
    if (detailPanel) {
      detailPanel.classList.remove('open');
      detailOverlay && detailOverlay.classList.remove('open');
    }
  }

  function openDetail(itemId) {
    if (!detailPanel) return;
    markRead(itemId);
    fetch(`/item/${itemId}`)
      .then(r => r.text())
      .then(html => {
        const content = detailPanel.querySelector('.detail-body');
        if (content) content.innerHTML = html;
        detailPanel.classList.add('open');
        detailOverlay && detailOverlay.classList.add('open');
      });
  }

  if (detailOverlay) {
    detailOverlay.addEventListener('click', closeDetail);
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeDetail();
  });

  /* ── CARD CLICK → DETAIL PANEL ───────────────────────────────────────── */
  document.addEventListener('click', function (e) {
    if (e.target.closest('.thumb-btn') || e.target.closest('.save-btn') || e.target.closest('a')) return;
    const card = e.target.closest('.card[data-id]');
    if (!card) return;
    openDetail(card.dataset.id);
  });

  /* ── FILTER TABS ──────────────────────────────────────────────────────── */
  document.querySelectorAll('.tab[data-filter]').forEach(tab => {
    tab.addEventListener('click', function () {
      const filter = this.dataset.filter;
      const date = this.dataset.date || '';

      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      this.classList.add('active');

      const url = new URL(window.location.href);
      url.searchParams.set('tab', filter);
      if (date) url.searchParams.set('date', date);
      window.history.pushState({}, '', url);

      // Show/hide clusters
      const clusters = document.querySelectorAll('.cluster-block');
      clusters.forEach(cl => {
        if (filter === 'ALL') {
          cl.style.display = '';
        } else {
          cl.style.display = cl.dataset.topic === filter ? '' : 'none';
        }
      });

      // Show/hide cards
      const cards = document.querySelectorAll('.card[data-topic]');
      cards.forEach(card => {
        if (filter === 'ALL') {
          card.style.display = '';
        } else {
          card.style.display = card.dataset.topic === filter ? '' : 'none';
        }
      });

      // Update meta count
      const visible = [...cards].filter(c => c.style.display !== 'none').length;
      const meta = document.querySelector('.tabs-meta');
      if (meta) {
        const base = meta.dataset.base || '';
        meta.textContent = base.replace(/\d+ ITEMS/, `${visible} ITEMS`);
      }
    });
  });

  /* ── LIVE SEARCH ──────────────────────────────────────────────────────── */
  const searchInput = document.getElementById('digest-search');
  if (searchInput) {
    searchInput.addEventListener('input', function () {
      const q = this.value.toLowerCase().trim();
      const cards = document.querySelectorAll('.card[data-id]');
      cards.forEach(card => {
        if (!q) { card.style.display = ''; return; }
        const text = card.textContent.toLowerCase();
        card.style.display = text.includes(q) ? '' : 'none';
      });
    });
  }

  /* ── PIPELINE RUN STATUS POLL ─────────────────────────────────────────── */
  function pollRunStatus(runId) {
    const statusEl = document.getElementById('run-status');
    if (!statusEl) return;

    const interval = setInterval(() => {
      fetch(`/admin/run-status/${runId}`)
        .then(r => r.json())
        .then(data => {
          statusEl.textContent = data.status === 'complete'
            ? `Done — ${data.items_in_digest} items in digest ($${(data.total_usd || 0).toFixed(3)})`
            : `Running… ${data.current_stage || ''}`;
          if (data.status === 'complete' || data.status === 'failed') {
            clearInterval(interval);
            statusEl.classList.add(data.status === 'complete' ? 'text-success' : 'text-danger');
          }
        })
        .catch(() => clearInterval(interval));
    }, 2000);
  }

  const runIdEl = document.querySelector('[data-run-id]');
  if (runIdEl && runIdEl.dataset.runId) {
    pollRunStatus(runIdEl.dataset.runId);
  }

  /* ── ADMIN CONFIRM ACTIONS ────────────────────────────────────────────── */
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', function (e) {
      if (!confirm(this.dataset.confirm)) e.preventDefault();
    });
  });

  /* ── PREFERENCES SLIDERS ──────────────────────────────────────────────── */
  document.querySelectorAll('.pref-slider').forEach(slider => {
    const valEl = slider.nextElementSibling;
    if (valEl && valEl.classList.contains('pref-slider-val')) {
      slider.addEventListener('input', function () {
        valEl.textContent = parseFloat(this.value).toFixed(1);
      });
    }
  });

})();
