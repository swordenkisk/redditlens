/* RedditLens — app.js */
'use strict';

// ── Toast ──────────────────────────────────────────────────────
window.showToast = function(msg, dur=2500) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove('show'), dur);
};

// ── Score color helper ─────────────────────────────────────────
function scoreColor(n) {
  if (n >= 60) return 'var(--pain)';
  if (n >= 30) return 'var(--urgency)';
  return 'var(--t3)';
}

// ── Render opportunity card ────────────────────────────────────
function renderCard(r) {
  const col = scoreColor(r.opportunity_score);
  const pain = r.pain_points?.length || 0;
  const wtp  = r.wtp_signals?.length  || 0;
  const gap  = r.gaps?.length          || 0;
  const sigs = r.signal_count || 0;

  const chips = [
    pain     ? `<span class="sig-chip sig-pain">💔 ${pain} pain</span>` : '',
    wtp      ? `<span class="sig-chip sig-wtp">💰 ${wtp} WTP</span>` : '',
    gap      ? `<span class="sig-chip sig-gap">🔍 ${gap} gap</span>` : '',
  ].filter(Boolean).join('');

  return `
<div class="opp-card fade" style="--score-color:${col}">
  <div class="opp-top">
    <div>
      <div class="opp-sub">r/${r.subreddit}</div>
      <div class="opp-title">${esc(r.post_title?.slice(0,90) || '')}</div>
    </div>
    <div class="opp-score">${Math.round(r.opportunity_score)}</div>
  </div>
  <div class="opp-meta">
    <span>👍 ${r.score}</span>
    <span>💬 ${r.num_comments}</span>
    <span>📡 ${sigs} signals</span>
  </div>
  <div class="opp-summary">${esc(r.summary || '')}</div>
  <div class="opp-signals">${chips}</div>
  <div class="opp-actions">
    <a href="/report/${r.id}" class="btn btn-ghost btn-sm">Details</a>
    <a href="${r.url}" target="_blank" class="btn btn-ghost btn-sm">Reddit ↗</a>
    <a href="/api/export/${r.id}/md" class="btn btn-ghost btn-sm">Export</a>
  </div>
</div>`;
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Render full post result ────────────────────────────────────
function renderPostResult(r) {
  const col = scoreColor(r.opportunity_score);
  const signals = (r.signals || []).slice(0, 25);

  let html = `
<div class="detail-grid">
  <div class="detail-sidebar">
    <div class="side-block">
      <div class="side-hdr">Opportunity Score</div>
      <div class="side-body">
        <div class="score-display">
          <div class="score-big" style="color:${col}">${Math.round(r.opportunity_score)}</div>
          <div class="score-sub">/100</div>
        </div>
        <div class="score-bar"><div class="score-fill" style="width:${r.opportunity_score}%;background:${col}"></div></div>
      </div>
    </div>
    <div class="side-block">
      <div class="side-hdr">Stats</div>
      <div class="side-body">
        <div class="side-row"><span class="sr-k">subreddit</span><span class="sr-v orange">r/${r.subreddit}</span></div>
        <div class="side-row"><span class="sr-k">upvotes</span><span class="sr-v">${r.score}</span></div>
        <div class="side-row"><span class="sr-k">comments</span><span class="sr-v">${r.num_comments}</span></div>
        <div class="side-row"><span class="sr-k">signals</span><span class="sr-v orange">${r.signal_count}</span></div>
        ${r.audience_profile ? `<div class="side-row"><span class="sr-k">audience</span><span class="sr-v green" style="font-size:10px">${esc(r.audience_profile)}</span></div>` : ''}
      </div>
    </div>
    <div class="side-block">
      <div class="side-hdr">Actions</div>
      <div class="side-body" style="display:flex;flex-direction:column;gap:6px">
        <a href="${r.url}" target="_blank" class="btn btn-acc">Open Reddit ↗</a>
        <a href="/report/${r.id}" class="btn btn-ghost">Full Report</a>
        <a href="/api/export/${r.id}/md" class="btn btn-ghost">Export Markdown</a>
        <a href="/api/export/${r.id}/json" class="btn btn-ghost">Export JSON</a>
      </div>
    </div>
  </div>
  <div>
    <h2 style="font-family:var(--sans);font-size:20px;font-weight:700;margin-bottom:8px;line-height:1.3">${esc(r.post_title)}</h2>
    <p style="font-size:12px;color:var(--t2);margin-bottom:20px">${esc(r.summary || '')}</p>`;

  if (r.pain_points?.length) {
    html += `<div class="result-panel" style="margin-bottom:14px">
      <div class="result-hdr"><span class="result-hdr-title">💔 Pain Points</span></div>
      <div class="result-body"><div class="signal-list">
        ${r.pain_points.slice(0,6).map(p=>`<div class="signal-item pain">${esc(p)}</div>`).join('')}
      </div></div></div>`;
  }
  if (r.wtp_signals?.length) {
    html += `<div class="result-panel" style="margin-bottom:14px">
      <div class="result-hdr"><span class="result-hdr-title">💰 Willingness to Pay</span></div>
      <div class="result-body"><div class="signal-list">
        ${r.wtp_signals.slice(0,4).map(w=>`<div class="signal-item wtp">${esc(w)}</div>`).join('')}
      </div></div></div>`;
  }
  if (r.top_keywords?.length) {
    html += `<div class="result-panel" style="margin-bottom:14px">
      <div class="result-hdr"><span class="result-hdr-title">🏷️ Keywords</span></div>
      <div class="result-body"><div class="kw-cloud">
        ${r.top_keywords.slice(0,12).map(([k,v])=>`<span class="kw-pill">${esc(k)} <span style="color:var(--t3)">×${v}</span></span>`).join('')}
      </div></div></div>`;
  }
  if (signals.length) {
    html += `<div class="result-panel">
      <div class="result-hdr"><span class="result-hdr-title">📡 All Signals (${signals.length})</span></div>
      <div class="result-body"><div class="signal-list">
        ${signals.map(s=>`<div class="signal-item ${s.category}">
          <span class="sig-chip sig-${s.category}" style="display:inline-block;margin-bottom:5px">${s.emoji} ${s.category}</span>
          ${esc(s.context?.slice(0,200)||'')}
          <div class="signal-meta">${s.source} · score: ${s.score}</div>
        </div>`).join('')}
      </div></div></div>`;
  }
  html += '</div></div>';
  return html;
}

// ── Scan page logic ────────────────────────────────────────────
window.startScan = async function() {
  const sub   = document.getElementById('sub-input')?.value.trim().replace(/^r\//,'');
  const sort  = document.getElementById('sort-sel')?.value  || 'hot';
  const limit = document.getElementById('limit-sel')?.value || '25';
  const fetchC= document.getElementById('fetch-cmts')?.checked ?? true;
  if (!sub) { showToast('Enter a subreddit name'); return; }

  const btn = document.getElementById('scan-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Scanning...';
  document.getElementById('scan-progress')?.classList.remove('hidden');
  document.getElementById('scan-results')?.classList.add('hidden');
  document.getElementById('scan-status').textContent = `Scanning r/${sub}...`;

  // Animate progress bar
  let prog = 30;
  const interval = setInterval(() => {
    prog = Math.min(prog + 5, 85);
    const bar = document.getElementById('scan-bar');
    if (bar) bar.style.width = prog + '%';
  }, 800);

  try {
    const r = await fetch('/api/analyze/subreddit', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({subreddit:sub, sort, limit:+limit, fetch_comments:fetchC}),
    });
    const data = await r.json();
    clearInterval(interval);
    document.getElementById('scan-bar').style.width = '100%';

    if (data.error) { showToast('Error: ' + data.error); return; }

    const grid  = document.getElementById('results-grid');
    const title = document.getElementById('results-title');
    grid.innerHTML  = (data.reports||[]).map(renderCard).join('');
    title.textContent = `r/${sub} — ${data.total_found} opportunities found`;
    document.getElementById('scan-results').classList.remove('hidden');
    document.getElementById('scan-progress').classList.add('hidden');
  } catch(e) {
    clearInterval(interval);
    showToast('Error: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ Start Scan';
  }
};

// ── Post analysis logic ────────────────────────────────────────
window.analyzePost = async function() {
  const url   = document.getElementById('post-url')?.value.trim();
  const limit = document.getElementById('comment-limit')?.value || '100';
  if (!url) { showToast('Enter a Reddit URL'); return; }

  const loading = document.getElementById('post-loading');
  const result  = document.getElementById('post-result');
  loading?.classList.remove('hidden');
  result?.classList.add('hidden');

  try {
    const r = await fetch('/api/analyze/post', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({url, comment_limit:+limit}),
    });
    const data = await r.json();
    if (data.error) { showToast('Error: ' + data.error); return; }
    if (result) {
      result.innerHTML = renderPostResult(data);
      result.classList.remove('hidden');
    }
  } catch(e) {
    showToast('Error: ' + e.message);
  } finally {
    loading?.classList.add('hidden');
  }
};

// ── Batch scan logic ───────────────────────────────────────────
window.startBatch = async function() {
  const raw    = document.getElementById('batch-subs')?.value || '';
  const subs   = raw.split('\n').map(s=>s.trim().replace(/^r\//,'')).filter(Boolean);
  const sort   = document.getElementById('batch-sort')?.value  || 'hot';
  const limit  = document.getElementById('batch-limit')?.value || '10';
  const thresh = document.getElementById('batch-thresh')?.value || '15';

  if (!subs.length) { showToast('Enter at least one subreddit'); return; }
  if (subs.length > 10) { showToast('Max 10 subreddits'); return; }

  const btn = document.getElementById('batch-btn');
  btn.disabled = true; btn.textContent = '⏳ Scanning...';
  document.getElementById('batch-loading')?.classList.remove('hidden');
  document.getElementById('batch-status').textContent = `Scanning ${subs.length} subreddits...`;

  let prog = 15;
  const interval = setInterval(() => {
    prog = Math.min(prog + 3, 80);
    const bar = document.getElementById('batch-bar');
    if (bar) bar.style.width = prog + '%';
  }, 1000);

  try {
    const r = await fetch('/api/batch', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({subreddits:subs, sort, posts_per_sub:+limit, min_score:+thresh}),
    });
    const data = await r.json();
    clearInterval(interval);
    document.getElementById('batch-bar').style.width = '100%';
    if (data.error) { showToast('Error: ' + data.error); return; }

    document.getElementById('batch-grid').innerHTML = (data.reports||[]).map(renderCard).join('');
    document.getElementById('batch-title').textContent = `${data.total_found} opportunities across ${data.scanned_subs} subreddits`;
    document.getElementById('batch-results')?.classList.remove('hidden');
    document.getElementById('batch-loading')?.classList.add('hidden');
  } catch(e) {
    clearInterval(interval);
    showToast('Error: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '🔍 Start Batch Scan';
  }
};

// ── URL param auto-fill ────────────────────────────────────────
const params = new URLSearchParams(window.location.search);
const sub = params.get('sub');
if (sub) {
  const el = document.getElementById('sub-input');
  if (el) {
    el.value = sub;
    setTimeout(window.startScan, 300);
  }
}
const postUrl = params.get('url');
if (postUrl) {
  const el = document.getElementById('post-url');
  if (el) {
    el.value = decodeURIComponent(postUrl);
    setTimeout(window.analyzePost, 300);
  }
}
