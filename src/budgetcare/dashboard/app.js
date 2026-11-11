/**
 * Budget Care Monitoring Dashboard — Client Application
 * Handles polling, Chart.js rendering, tab switching, and table filtering.
 */

let moodChartInstance = null;
let outboxChartInstance = null;
let cachedGoals = [];

const MOOD_META = {
  4: { label: 'Ecstatic (100%)', emoji: '😄', color: '#10b981' },
  3: { label: 'Happy (75-99%)', emoji: '🙂', color: '#6366f1' },
  2: { label: 'Hungry (50-74%)', emoji: '😐', color: '#f59e0b' },
  1: { label: 'Starving (<50%)', emoji: '🥺', color: '#ef4444' }
};

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.getElementById(`tab-btn-${tabId}`);
  if (activeBtn) activeBtn.classList.add('active');

  ['overview', 'devops', 'goals', 'analytics'].forEach(id => {
    const el = document.getElementById(`tab-content-${id}`);
    if (el) el.classList.toggle('hidden', id !== tabId);
  });
}

async function fetchStats() {
  const refreshIcon = document.getElementById('refresh-icon');
  if (refreshIcon) refreshIcon.classList.add('animate-spin');

  try {
    const res = await fetch('/api/dashboard/stats');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    renderDashboard(data);
  } catch (err) {
    console.error('Failed to fetch dashboard stats:', err);
    const hbText = document.getElementById('heartbeat-text');
    if (hbText) hbText.textContent = 'API Error';
    const hbDot = document.getElementById('heartbeat-dot');
    if (hbDot) hbDot.className = 'w-2.5 h-2.5 rounded-full bg-red-500';
  } finally {
    if (refreshIcon) refreshIcon.classList.remove('animate-spin');
  }
}

function renderDashboard(data) {
  const lastUpdatedEl = document.getElementById('last-updated-ts');
  if (lastUpdatedEl) lastUpdatedEl.textContent = data.meta.server_time;

  // 1. Cron Heartbeat Pill
  const hbDot = document.getElementById('heartbeat-dot');
  const hbText = document.getElementById('heartbeat-text');
  const hbPill = document.getElementById('heartbeat-pill');
  if (data.devops && data.devops.last_tick) {
    const secAgo = data.devops.seconds_since_last_tick ?? 999;
    if (data.devops.is_cron_healthy) {
      hbDot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500';
      hbText.textContent = `Cron Healthy (${secAgo}s ago)`;
      hbPill.className = 'flex items-center space-x-2 text-xs px-3 py-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400';
    } else {
      hbDot.className = 'w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse';
      hbText.textContent = `Cron Delayed (${secAgo}s ago)`;
      hbPill.className = 'flex items-center space-x-2 text-xs px-3 py-1.5 rounded-full border border-red-500/30 bg-red-500/10 text-red-400';
    }
  } else {
    hbDot.className = 'w-2.5 h-2.5 rounded-full bg-amber-500';
    hbText.textContent = 'No tick recorded yet';
  }

  // 2. Overview Stats Cards
  const ov = data.overview;
  document.getElementById('stat-total-saved').textContent = ov.total_saved_formatted;
  document.getElementById('stat-target-pool').textContent = ov.active_target_formatted;
  document.getElementById('stat-ontime-rate').textContent = ov.on_time_feeding_rate + '%';
  document.getElementById('stat-fed-vs-missed').textContent = `${ov.fed_periods} fed / ${ov.missed_periods} missed`;
  document.getElementById('stat-active-users').textContent = ov.active_users;
  document.getElementById('stat-users-breakdown').textContent = `${ov.total_users} total (${ov.blocked_users} blocked)`;
  document.getElementById('stat-graduated-goals').textContent = ov.graduated_goals;
  document.getElementById('stat-active-goals').textContent = `${ov.active_goals} active (${ov.expired_goals || ov.closed_goals || 0} expired)`;

  // 3. Habit Bars
  document.getElementById('free-food-pct').textContent = ov.free_food_ratio + '%';
  document.getElementById('free-food-bar').style.width = Math.min(100, ov.free_food_ratio) + '%';

  const an = data.analytics;
  document.getElementById('d7-retention-val').textContent = an.retention_d7_rate + '%';
  document.getElementById('d7-retention-bar').style.width = Math.min(100, an.retention_d7_rate) + '%';
  document.getElementById('d21-retention-val').textContent = an.retention_d21_rate + '%';
  document.getElementById('d21-retention-bar').style.width = Math.min(100, an.retention_d21_rate) + '%';

  // 4. Render Mood Chart
  renderMoodChart(ov.mood_counts);

  // 5. Render Outbox Chart
  renderOutboxChart(data.devops.outbox);

  // 6. DevOps Tab
  renderDevopsTab(data.devops);

  // 7. Goals Explorer Tab
  cachedGoals = data.recent_goals || [];
  renderGoalsTable(cachedGoals);

  // 8. Analytics Tab
  renderAnalyticsTab(an);
}

function renderMoodChart(moodCounts) {
  const labels = ['Ecstatic 😄', 'Happy 🙂', 'Hungry 😐', 'Starving 🥺'];
  const counts = [moodCounts[4] || 0, moodCounts[3] || 0, moodCounts[2] || 0, moodCounts[1] || 0];
  const colors = ['#10b981', '#6366f1', '#f59e0b', '#ef4444'];

  const ctx = document.getElementById('moodChart').getContext('2d');
  if (moodChartInstance) moodChartInstance.destroy();

  moodChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: counts,
        backgroundColor: colors,
        borderColor: '#0f172a',
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      cutout: '68%'
    }
  });

  // Legend
  const legendEl = document.getElementById('mood-legend');
  legendEl.innerHTML = labels.map((l, i) => `
    <div class="flex items-center space-x-2 bg-slate-950 p-2 rounded border border-slate-800/80">
      <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${colors[i]}"></span>
      <span class="flex-1 text-slate-300">${l}</span>
      <span class="font-bold text-white">${counts[i]}</span>
    </div>
  `).join('');
}

function renderOutboxChart(outbox) {
  const labels = ['Sent', 'Pending', 'Sending', 'Failed', 'Cancelled'];
  const counts = [outbox.sent || 0, outbox.pending || 0, outbox.sending || 0, outbox.failed || 0, outbox.cancelled || 0];
  const colors = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#64748b'];

  const ctx = document.getElementById('outboxChart').getContext('2d');
  if (outboxChartInstance) outboxChartInstance.destroy();

  outboxChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: counts,
        backgroundColor: colors,
        borderColor: '#0f172a',
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      cutout: '68%'
    }
  });

  const legendEl = document.getElementById('outbox-legend');
  legendEl.innerHTML = labels.map((l, i) => `
    <div class="bg-slate-950 p-1.5 rounded border border-slate-800/80">
      <div class="text-[10px] text-slate-400">${l}</div>
      <div class="font-bold text-white text-xs">${counts[i]}</div>
    </div>
  `).join('');
}

function renderDevopsTab(devops) {
  const lt = devops.last_tick;
  const badge = document.getElementById('tick-health-badge');
  if (lt) {
    badge.textContent = devops.is_cron_healthy ? 'HEALTHY' : 'DELAYED';
    badge.className = devops.is_cron_healthy ? 'text-xs px-2 py-0.5 rounded font-medium bg-emerald-500/20 text-emerald-400' : 'text-xs px-2 py-0.5 rounded font-medium bg-red-500/20 text-red-400';
    document.getElementById('tick-last-time').textContent = lt.started_at;
    document.getElementById('tick-last-dur').textContent = lt.duration_ms + ' ms';
    document.getElementById('tick-last-err').textContent = lt.error || 'None';
  } else {
    badge.textContent = 'NO DATA';
  }
  document.getElementById('stale-claims-val').textContent = devops.outbox.stale_claims || 0;

  // Locks
  const locksEl = document.getElementById('locks-container');
  if (devops.locks && devops.locks.length > 0) {
    locksEl.innerHTML = devops.locks.map(l => `
      <div class="bg-slate-950 p-2.5 rounded border border-slate-800 flex justify-between items-center">
        <div>
          <span class="font-bold text-indigo-400">${l.name}</span>
          <span class="text-slate-400">by ${l.locked_by || 'system'}</span>
        </div>
        <div class="text-right">
          <span class="${l.is_expired ? 'text-slate-500' : 'text-emerald-400'} font-medium block">
            ${l.is_expired ? 'Expired' : 'Active Lease'}
          </span>
          <span class="text-[10px] text-slate-500 font-mono">Until: ${l.locked_until || '-'}</span>
        </div>
      </div>
    `).join('');
  } else {
    locksEl.innerHTML = '<p class="text-slate-500 italic py-2">No active lease locks held.</p>';
  }

  // Recent Ticks Table
  const tbody = document.getElementById('ticks-table-body');
  if (devops.recent_ticks && devops.recent_ticks.length > 0) {
    tbody.innerHTML = devops.recent_ticks.map(tr => `
      <tr class="hover:bg-slate-800/40 transition">
        <td class="px-4 py-2.5 font-bold text-slate-300">#${tr.id}</td>
        <td class="px-4 py-2.5">${tr.started_at}</td>
        <td class="px-4 py-2.5 text-slate-200">${tr.duration_ms} ms</td>
        <td class="px-4 py-2.5">${tr.periods_closed}</td>
        <td class="px-4 py-2.5 ${tr.periods_missed > 0 ? 'text-amber-400 font-bold' : ''}">${tr.periods_missed}</td>
        <td class="px-4 py-2.5 ${tr.goals_graduated > 0 ? 'text-emerald-400 font-bold' : ''}">${tr.goals_graduated}</td>
        <td class="px-4 py-2.5">${tr.notifications_sent}</td>
        <td class="px-4 py-2.5">
          ${tr.error ? '<span class="text-red-400 bg-red-500/10 px-2 py-0.5 rounded text-[10px]">Error</span>' : '<span class="text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded text-[10px]">Success</span>'}
        </td>
      </tr>
    `).join('');
  } else {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center py-6 text-slate-500">No cron runs recorded yet.</td></tr>';
  }
}

function renderGoalsTable(goals) {
  const tbody = document.getElementById('goals-table-body');
  if (!goals || goals.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-6 text-slate-500">No active goals found.</td></tr>';
    return;
  }

  tbody.innerHTML = goals.map(g => {
    const mood = MOOD_META[g.mood_tier] || MOOD_META[4];
    return `
      <tr class="hover:bg-slate-800/40 transition">
        <td class="px-4 py-3 font-medium text-white flex items-center space-x-2">
          <span class="text-lg">${g.pet_emoji}</span>
          <div>
            <div class="font-bold text-slate-100">${g.pet_name}</div>
            <div class="text-[11px] text-slate-400 capitalize">${g.species}</div>
          </div>
        </td>
        <td class="px-4 py-3">
          <div class="font-medium text-slate-200">${g.name}</div>
          <div class="text-[11px] text-slate-400">User #${g.user_id}</div>
        </td>
        <td class="px-4 py-3 capitalize text-slate-300 font-mono">${g.frequency}</td>
        <td class="px-4 py-3">
          <div class="flex items-center space-x-2">
            <div class="w-16 bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div class="bg-indigo-500 h-1.5 rounded-full" style="width: ${g.progress_pct}%"></div>
            </div>
            <span class="font-bold text-white">${g.progress_pct}%</span>
          </div>
          <div class="text-[10px] text-slate-400 mt-0.5">${g.deposited_formatted} / ${g.target_formatted}</div>
        </td>
        <td class="px-4 py-3 font-bold ${g.condition_pct >= 75 ? 'text-emerald-400' : (g.condition_pct >= 50 ? 'text-amber-400' : 'text-red-400')}">
          ${g.condition_pct}%
        </td>
        <td class="px-4 py-3">
          <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
            <span>${mood.emoji}</span>
            <span class="text-[11px] text-slate-300">${mood.label.split(' ')[0]}</span>
          </span>
        </td>
        <td class="px-4 py-3 text-slate-400 font-mono text-[11px]">${g.created_at}</td>
      </tr>
    `;
  }).join('');
}

function filterGoalsTable() {
  const query = (document.getElementById('goals-search').value || '').toLowerCase();
  const filtered = cachedGoals.filter(g =>
    g.name.toLowerCase().includes(query) ||
    g.pet_name.toLowerCase().includes(query) ||
    g.species.toLowerCase().includes(query)
  );
  renderGoalsTable(filtered);
}

function renderAnalyticsTab(an) {
  document.getElementById('analytics-deposits-count').textContent = an.deposits_count;
  document.getElementById('analytics-freefood-count').textContent = an.free_food_count;
  const total = an.deposits_count + an.free_food_count;
  const ratio = total > 0 ? Math.round((an.free_food_count * 100) / total) : 0;
  document.getElementById('analytics-freefood-ratio').textContent = `${ratio}% of all feeds`;

  document.getElementById('analytics-d7-count').textContent = `${an.retained_d7} users (${an.retention_d7_rate}%)`;
  document.getElementById('analytics-d21-count').textContent = `${an.retained_d21} users (${an.retention_d21_rate}%)`;

  // Variant cards
  const varContainer = document.getElementById('variants-container');
  const vars = an.variants || {};
  const keys = Object.keys(vars);
  if (keys.length === 0) {
    varContainer.innerHTML = '<p class="text-slate-500 italic">No variant data recorded.</p>';
    return;
  }

  varContainer.innerHTML = keys.map(k => {
    const v = vars[k];
    const isPet = k === 'pet';
    return `
      <div class="bg-slate-950 p-4 rounded-xl border ${isPet ? 'border-indigo-500/30' : 'border-slate-800'} space-y-3">
        <div class="flex justify-between items-center">
          <span class="text-sm font-bold uppercase tracking-wider ${isPet ? 'text-indigo-400' : 'text-slate-300'}">
            ${isPet ? '🐾 Pet Companion Variant' : '📄 Plain Text Variant'}
          </span>
          <span class="text-xs bg-slate-800 px-2 py-0.5 rounded text-slate-300">${v.total_users} Users</span>
        </div>
        <div class="grid grid-cols-2 gap-2 text-xs pt-1">
          <div class="bg-slate-900 p-2 rounded">
            <div class="text-slate-400">Total Goals</div>
            <div class="text-base font-bold text-white mt-0.5">${v.total_goals}</div>
          </div>
          <div class="bg-slate-900 p-2 rounded">
            <div class="text-slate-400">Graduation Rate</div>
            <div class="text-base font-bold text-emerald-400 mt-0.5">${v.grad_rate}%</div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// Auto-refresh timer (30s)
setInterval(() => {
  const toggle = document.getElementById('auto-refresh-toggle');
  if (toggle && toggle.checked) {
    fetchStats();
  }
}, 30000);

// Initial Load
document.addEventListener('DOMContentLoaded', () => {
  fetchStats();
});
