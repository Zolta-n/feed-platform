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
  btn.childNodes.forEach(n => { if (n.nodeType === 3) n.textContent = saved ? 'Saved' : 'Save'; });
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
      const visible = [...section.querySelectorAll('.card')].some(c => c.style.display !== 'none');
      section.style.display = visible ? '' : 'none';
    });
  });
}

// ── Theme swatches ────────────────────────────────────
const swatchContainer = document.getElementById('theme-swatches');
if (swatchContainer) {
  swatchContainer.addEventListener('click', async (e) => {
    const swatch = e.target.closest('.swatch[data-hex]');
    if (!swatch) return;
    const hex = swatch.dataset.hex;
    const color = swatch.dataset.color;
    // Update CSS live
    document.documentElement.style.setProperty('--accent', hex);
    // Parse rgb
    const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
    document.documentElement.style.setProperty('--accent-rgb', `${r},${g},${b}`);
    // Update active state
    swatchContainer.querySelectorAll('.swatch').forEach(s => s.classList.remove('active'));
    swatch.classList.add('active');
    // Persist via preferences form (set hidden input if present, or POST directly)
    const form = swatch.closest('form') || document.querySelector('form#prefs-form');
    if (form) {
      let inp = form.querySelector('input[name="theme_color"]');
      if (!inp) {
        inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'theme_color';
        form.appendChild(inp);
      }
      inp.value = color;
    }
  });
}
