'use strict';

// --- CSRF token from meta tag ---
function getCsrf() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

// --- JSON POST helper ---
async function postJSON(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
    body: JSON.stringify(data),
  });
  return res.ok;
}

// --- Thumbs feedback ---
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.thumb-btn[data-signal]');
  if (!btn) return;
  const itemId = btn.dataset.itemId;
  const signal = btn.dataset.signal;
  const ok = await postJSON('/api/feedback', { item_id: itemId, signal });
  if (ok) {
    const group = btn.closest('.thumbs');
    group?.querySelectorAll('.thumb-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }
});

// --- Mark-as-read on item link click ---
document.addEventListener('click', async (e) => {
  const link = e.target.closest('.item-link[data-item-id]');
  if (!link) return;
  const itemId = link.dataset.itemId;
  postJSON('/api/read', { item_id: itemId }).then(ok => {
    if (ok) {
      const card = link.closest('.card');
      card?.classList.add('read');
    }
  });
});

// --- Filter tabs ---
const filterTabContainer = document.getElementById('filter-tabs');
if (filterTabContainer) {
  filterTabContainer.addEventListener('click', (e) => {
    const tab = e.target.closest('.filter-tab');
    if (!tab) return;
    const topic = tab.dataset.topic;

    filterTabContainer.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');

    document.querySelectorAll('.card[data-topic]').forEach(card => {
      if (topic === 'all' || card.dataset.topic === topic) {
        card.style.display = '';
      } else {
        card.style.display = 'none';
      }
    });

    // Also hide cluster headers that have no visible items
    document.querySelectorAll('.cluster-header').forEach(header => {
      let next = header.nextElementSibling;
      let hasVisible = false;
      while (next && !next.classList.contains('cluster-header')) {
        if (next.classList.contains('card') && next.style.display !== 'none') {
          hasVisible = true;
          break;
        }
        next = next.nextElementSibling;
      }
      header.style.display = hasVisible ? '' : 'none';
    });
  });
}
