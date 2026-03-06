/**
 * Reusable UI components: badges, gauges, toasts, modals, cards.
 */

const UI = {
    // --- Status badge ---
    badge(status) {
        const cls = `badge badge-${status}`;
        return `<span class="${cls}">${status}</span>`;
    },

    // --- Circular gauge ---
    gauge(percent, label, color = 'var(--accent)') {
        const r = 34;
        const circ = 2 * Math.PI * r;
        const offset = circ - (percent / 100) * circ;
        return `
        <div class="gauge-container">
            <div class="gauge-circle">
                <svg width="80" height="80" viewBox="0 0 80 80">
                    <circle class="gauge-bg" cx="40" cy="40" r="${r}"/>
                    <circle class="gauge-fill" cx="40" cy="40" r="${r}"
                        stroke="${color}"
                        stroke-dasharray="${circ}"
                        stroke-dashoffset="${offset}"/>
                </svg>
                <div class="gauge-value">${Math.round(percent)}%</div>
            </div>
            <div class="gauge-label">${label}</div>
        </div>`;
    },

    // --- Stat card (with optional id for patching) ---
    statCard(label, value, sub = '', color = 'var(--text-primary)', id = '') {
        const idAttr = id ? ` id="${id}"` : '';
        return `
        <div class="stat-card"${idAttr}>
            <div class="stat-card-label">${label}</div>
            <div class="stat-card-value" style="color:${color}">${value}</div>
            ${sub ? `<div class="stat-card-sub">${sub}</div>` : ''}
        </div>`;
    },

    /** Patch an existing stat card's value and sub-text without rebuilding */
    patchStatCard(id, value, sub) {
        const el = document.getElementById(id);
        if (!el) return;
        const valEl = el.querySelector('.stat-card-value');
        if (valEl) valEl.textContent = value;
        if (sub !== undefined) {
            const subEl = el.querySelector('.stat-card-sub');
            if (subEl) subEl.textContent = sub;
        }
    },

    // --- Toast notifications ---
    toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateX(40px)';
            el.style.transition = '0.3s ease';
            setTimeout(() => el.remove(), 300);
        }, 3500);
    },

    // --- Modal ---
    openModal(title, bodyHTML, wide = false) {
        const overlay = document.getElementById('modal-overlay');
        const modal = document.getElementById('modal');
        const titleEl = document.getElementById('modal-title');
        const bodyEl = document.getElementById('modal-body');

        titleEl.textContent = title;
        bodyEl.innerHTML = bodyHTML;
        modal.className = wide ? 'modal modal-wide' : 'modal';
        overlay.classList.add('active');
    },

    closeModal() {
        document.getElementById('modal-overlay').classList.remove('active');
    },

    // --- Copy to clipboard ---
    async copyText(text) {
        try {
            await navigator.clipboard.writeText(text);
            UI.toast('Copied to clipboard', 'success');
        } catch {
            UI.toast('Failed to copy', 'error');
        }
    },

    // --- Format bytes ---
    formatBytes(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
    },

    // --- Format duration ---
    formatUptime(seconds) {
        const d = Math.floor(seconds / 86400);
        const h = Math.floor((seconds % 86400) / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (d > 0) return `${d}d ${h}h`;
        if (h > 0) return `${h}h ${m}m`;
        return `${m}m`;
    },

    // --- Empty state ---
    emptyState(message, btnLabel = null, btnOnClick = null) {
        return `
        <div class="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
            </svg>
            <p>${message}</p>
            ${btnLabel ? `<button class="btn btn-primary" onclick="${btnOnClick}">${btnLabel}</button>` : ''}
        </div>`;
    },

    // --- Loading ---
    loading() {
        return `<div class="empty-state"><p>Loading…</p></div>`;
    },

    // --- Log viewer with search & delete ---
    logViewer(lines, configId = null) {
        const searchId = 'log-search-' + (configId || 'generic');
        const containerId = 'log-lines-' + (configId || 'generic');
        const header = `
        <div class="log-toolbar">
            <input type="text" class="form-input log-search-input" id="${searchId}" placeholder="Search logs…"
                oninput="UI._filterLogs('${searchId}','${containerId}')" />
            ${configId ? `
            <button class="btn btn-sm btn-danger" onclick="UI._clearLogs(${configId})">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:12px;height:12px;margin-right:4px">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                </svg>
                Clear All
            </button>` : ''}
        </div>`;

        const colored = lines.map((l, i) => {
            let cls = '';
            if (l.includes('[error]') || l.includes('[unhealthy]')) cls = 'log-line-error';
            else if (l.includes('[restart]') || l.includes('[exit]')) cls = 'log-line-warn';
            else if (l.includes('[start]') || l.includes('[info]')) cls = 'log-line-info';
            return `<div class="log-line${cls ? ' ' + cls : ''}" data-idx="${i}">${esc(l)}</div>`;
        }).join('');

        return `${header}<div class="log-viewer" id="${containerId}">${colored || '<div class="log-line" style="color:var(--text-muted)">No logs available</div>'}</div>`;
    },

    _filterLogs(searchId, containerId) {
        const query = document.getElementById(searchId).value.toLowerCase();
        const container = document.getElementById(containerId);
        if (!container) return;
        const lines = container.querySelectorAll('.log-line');
        lines.forEach(el => {
            el.style.display = el.textContent.toLowerCase().includes(query) ? '' : 'none';
        });
    },

    async _clearLogs(configId) {
        if (!confirm('Delete all logs for this configuration?')) return;
        try {
            const res = await fetch(`/api/configurations/${configId}/logs`, { method: 'DELETE' });
            if (res.ok) {
                UI.toast('Logs cleared', 'success');
                UI.closeModal();
            } else {
                UI.toast('Failed to clear logs', 'error');
            }
        } catch (err) {
            UI.toast(`Error: ${err.message}`, 'error');
        }
    },

    // --- Scroll helpers ---
    _saveScroll() {
        const main = document.getElementById('main-content');
        return main ? main.scrollTop : 0;
    },

    _restoreScroll(pos) {
        const main = document.getElementById('main-content');
        if (main) main.scrollTop = pos;
    },

    // --- Mobile sidebar toggle ---
    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (sidebar) sidebar.classList.toggle('sidebar-open');
        if (overlay) overlay.classList.toggle('active');
    },

    closeSidebar() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (sidebar) sidebar.classList.remove('sidebar-open');
        if (overlay) overlay.classList.remove('active');
    },
};

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
