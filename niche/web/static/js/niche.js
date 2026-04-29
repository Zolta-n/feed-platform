'use strict';

// ── CSRF ──────────────────────────────────────────────
function getCsrf() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

// ── JSON POST helper ──────────────────────────────────
async function postJSON(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
    body: JSON.stringify(data),
  });
  if (!res.ok) return null;
  return res.json().catch(() => null);
}

// ── Toast notification ────────────────────────────────
function showToast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ── Thumbs feedback ───────────────────────────────────
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.thumb-btn[data-signal]');
  if (!btn) return;
  const ok = await postJSON('/api/feedback', { item_id: btn.dataset.itemId, signal: btn.dataset.signal });
  if (ok) {
    btn.closest('.thumbs')?.querySelectorAll('.thumb-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }
});

// ── Mark-as-read ──────────────────────────────────────
document.addEventListener('click', async (e) => {
  const link = e.target.closest('.item-link[data-item-id]');
  if (!link) return;
  const data = await postJSON('/api/read', { item_id: link.dataset.itemId });
  if (data?.ok) link.closest('.card')?.classList.add('read');
});

// ── Save toggle ───────────────────────────────────────
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.save-btn[data-item-id]');
  if (!btn) return;
  const data = await postJSON('/api/save', { item_id: btn.dataset.itemId });
  if (data === null) return;
  const saved = data.saved;
  btn.classList.toggle('saved', saved);
  const svgPath = btn.querySelector('svg path');
  if (svgPath) svgPath.setAttribute('fill', saved ? 'currentColor' : 'none');
  btn.title = saved ? 'Unsave' : 'Save for later';
  showToast(saved ? 'Saved for later' : 'Removed from saved');
});

// ── Share — copy link ─────────────────────────────────
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.share-btn[data-item-id]');
  if (!btn) return;
  const data = await postJSON(`/api/share/${btn.dataset.itemId}`, {});
  if (!data?.url) { showToast('Could not create share link'); return; }
  try {
    await navigator.clipboard.writeText(data.url);
    showToast('Link copied to clipboard ✓');
  } catch {
    prompt('Share this link:', data.url);
  }
});

// ── Filter tabs ───────────────────────────────────────
const filterTabContainer = document.getElementById('filter-tabs');
if (filterTabContainer) {
  filterTabContainer.addEventListener('click', (e) => {
    const tab = e.target.closest('.filter-tab');
    if (!tab) return;
    const topic = tab.dataset.topic;
    filterTabContainer.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('.card[data-topic]').forEach(card => {
      card.style.display = (topic === 'all' || card.dataset.topic === topic) ? '' : 'none';
    });
    document.querySelectorAll('.cluster-section').forEach(section => {
      const visibleCards = [...section.querySelectorAll('.card')].filter(c => c.style.display !== 'none');
      section.style.display = visibleCards.length ? '' : 'none';
      // Mark solo card so CSS can make it full-width
      const grid = section.querySelector('.cards-grid');
      if (grid) grid.classList.toggle('has-solo', visibleCards.length === 1);
    });
  });
}

// ── Tweaks panel ──────────────────────────────────────
(function () {
  const panel    = document.getElementById('tweaks-panel');
  const backdrop = document.getElementById('tweaks-backdrop');
  const openBtn  = document.getElementById('tweaks-open');
  const closeBtn = document.getElementById('tweaks-close');
  if (!panel) return;

  function openPanel() {
    panel.classList.add('open');
    backdrop.classList.add('open');
  }
  function closePanel() {
    panel.classList.remove('open');
    backdrop.classList.remove('open');
  }

  openBtn?.addEventListener('click', openPanel);
  closeBtn?.addEventListener('click', closePanel);
  backdrop?.addEventListener('click', closePanel);

  // Density toggle
  const savedDensity = localStorage.getItem('density') || 'comfortable';
  if (savedDensity === 'compact') document.body.classList.add('compact');
  panel.querySelectorAll('.tweaks-toggle[data-density]').forEach(btn => {
    if (btn.dataset.density === savedDensity) btn.classList.add('active');
    btn.addEventListener('click', () => {
      const d = btn.dataset.density;
      localStorage.setItem('density', d);
      document.body.classList.toggle('compact', d === 'compact');
      panel.querySelectorAll('.tweaks-toggle[data-density]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // Ticker toggle
  const tickerToggle = document.getElementById('ticker-toggle');
  const tickerWrap   = document.getElementById('breaking-ticker');
  if (tickerToggle && tickerWrap) {
    const tickerHidden = localStorage.getItem('ticker') === 'hidden';
    if (tickerHidden) {
      tickerWrap.style.display = 'none';
      tickerToggle.checked = false;
    }
    tickerToggle.addEventListener('change', () => {
      const show = tickerToggle.checked;
      tickerWrap.style.display = show ? '' : 'none';
      localStorage.setItem('ticker', show ? 'visible' : 'hidden');
    });
  }

  // Accent color buttons (tweaks panel)
  panel.querySelectorAll('.tweaks-color-btn[data-hex]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const hex   = btn.dataset.hex;
      const color = btn.dataset.color;

      // Live CSS update
      document.documentElement.style.setProperty('--accent', hex);
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      document.documentElement.style.setProperty('--accent-rgb', `${r},${g},${b}`);
      panel.querySelectorAll('.tweaks-color-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      // Persist via AJAX
      const res = await fetch('/preferences/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({ theme_color: color }),
      });
      if (res.ok) showToast('Theme updated');
    });
  });
})();

// ── Theme swatches (preferences page) ────────────────
const swatchContainer = document.getElementById('theme-swatches');
if (swatchContainer) {
  swatchContainer.addEventListener('click', async (e) => {
    const swatch = e.target.closest('.swatch[data-hex]');
    if (!swatch) return;
    const hex   = swatch.dataset.hex;
    const color = swatch.dataset.color;

    document.documentElement.style.setProperty('--accent', hex);
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    document.documentElement.style.setProperty('--accent-rgb', `${r},${g},${b}`);
    swatchContainer.querySelectorAll('.swatch').forEach(s => s.classList.remove('active'));
    swatch.classList.add('active');

    const res = await fetch('/preferences/theme', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({ theme_color: color }),
    });
    if (res.ok) showToast('Theme updated');
  });
}
