/**
 * Dashboard page — system overview, best configs & resolvers.
 * Uses differential DOM updates for performance.
 */

const DashboardPage = {
    _cpuHistory: [],
    _ramHistory: [],
    _timeLabels: [],
    _maxPoints: 30,
    _rendered: false,
    _chart: null,

    async render() {
        this._rendered = false;
        await this._fetchAndBuild(true);
    },

    /** Called by auto-refresh — updates only changed values, no full rebuild. */
    async refresh() {
        if (!this._rendered) {
            await this.render();
            return;
        }
        await this._fetchAndBuild(false);
    },

    destroy() {
        this._rendered = false;
        this._chart = null;
    },

    async _fetchAndBuild(fullRender) {
        const container = document.getElementById('page-container');
        if (fullRender) container.innerHTML = UI.loading();

        try {
            const res = await fetch('/api/system/dashboard');
            if (!res.ok) throw new Error('Failed to load dashboard');
            const data = await res.json();

            const [cfgRes, resRes] = await Promise.all([
                fetch('/api/configurations/'),
                fetch('/api/resolvers/'),
            ]);
            const configs = await cfgRes.json();
            const resolvers = await resRes.json();

            const sys = data.system;

            // Update history
            this._cpuHistory.push(sys.cpu_percent);
            this._ramHistory.push(sys.memory_percent);
            this._timeLabels.push(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
            if (this._cpuHistory.length > this._maxPoints) {
                this._cpuHistory.shift();
                this._ramHistory.shift();
                this._timeLabels.shift();
            }

            // Sort configs by health: healthy first
            const sortedConfigs = [...configs].sort((a, b) => {
                const order = { healthy: 0, unknown: 1, unhealthy: 2 };
                return (order[a.health] || 1) - (order[b.health] || 1);
            });
            const sortedResolvers = [...resolvers].sort((a, b) => b.success_rate - a.success_rate);

            if (fullRender) {
                this._buildFullDOM(container, sys, data, sortedConfigs, sortedResolvers);
                this._rendered = true;
            } else {
                this._patchDOM(sys, data, sortedConfigs, sortedResolvers);
            }

            // Update chart (reuse existing or create)
            this._updateChart();

        } catch (err) {
            container.innerHTML = `<div class="empty-state"><p>Error loading dashboard: ${err.message}</p></div>`;
            this._rendered = false;
        }
    },

    _buildFullDOM(container, sys, data, sortedConfigs, sortedResolvers) {
        container.innerHTML = `
            <div class="page-header">
                <h1>Dashboard</h1>
                <p>System overview and tunnel status</p>
            </div>

            <!-- System gauges -->
            <div class="stat-grid" id="dash-gauges">
                <div class="stat-card" style="display:flex;align-items:center;gap:16px;" id="dash-cpu-gauge">
                    ${UI.gauge(sys.cpu_percent, 'CPU', sys.cpu_percent > 80 ? 'var(--red)' : 'var(--accent)')}
                </div>
                <div class="stat-card" style="display:flex;align-items:center;gap:16px;" id="dash-ram-gauge">
                    ${UI.gauge(sys.memory_percent, 'RAM', sys.memory_percent > 85 ? 'var(--red)' : 'var(--cyan)')}
                </div>
                ${UI.statCard('Uptime', UI.formatUptime(sys.uptime_seconds), `Load: ${sys.load_avg_1.toFixed(2)}`, 'var(--text-primary)', 'dash-uptime')}
                ${UI.statCard('Network ↑', (sys.net_sent_rate_kbps).toFixed(1) + ' KB/s', UI.formatBytes(sys.net_sent_bytes) + ' total', 'var(--purple)', 'dash-net-up')}
                ${UI.statCard('Network ↓', (sys.net_recv_rate_kbps).toFixed(1) + ' KB/s', UI.formatBytes(sys.net_recv_bytes) + ' total', 'var(--blue)', 'dash-net-down')}
                ${UI.statCard('Disk', sys.disk_percent.toFixed(1) + '%', sys.disk_used_gb.toFixed(1) + ' / ' + sys.disk_total_gb.toFixed(1) + ' GB', 'var(--text-primary)', 'dash-disk')}
            </div>

            <!-- System chart -->
            <div class="chart-container">
                <div class="chart-title">System Usage</div>
                <div class="chart-wrapper">
                    <canvas id="dashboard-system-chart"></canvas>
                </div>
            </div>

            <!-- Summary stats -->
            <div class="stat-grid" style="margin-bottom:24px;" id="dash-summary">
                ${UI.statCard('Configurations', data.total_configurations,
            `${data.running_configurations} running · ${data.healthy_configurations} healthy`, 'var(--accent-light)', 'dash-configs')}
                ${UI.statCard('Resolvers', data.total_resolvers,
                `${data.active_resolvers} active · ${data.dead_resolvers} dead`, 'var(--cyan)', 'dash-resolvers')}
                ${UI.statCard('HAProxy', data.haproxy_running ? 'Active' : 'Inactive', '',
                    data.haproxy_running ? 'var(--green)' : 'var(--text-muted)', 'dash-haproxy')}
            </div>

            <!-- Best configs -->
            <div class="section" id="dash-top-configs">
                <div class="section-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83"/><circle cx="12" cy="12" r="3"/>
                    </svg>
                    Top Configurations
                </div>
                ${sortedConfigs.length === 0
                ? UI.emptyState('No configurations yet', '+ Add Configuration', 'location.hash="#/configurations"')
                : `<div class="card-grid">${sortedConfigs.slice(0, 4).map(c => this._configCard(c)).join('')}</div>`
            }
            </div>

            <!-- Best resolvers -->
            <div class="section" id="dash-top-resolvers">
                <div class="section-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
                    </svg>
                    Top Resolvers
                </div>
                ${sortedResolvers.length === 0
                ? UI.emptyState('No resolvers yet', '+ Add Resolver', 'location.hash="#/resolvers"')
                : `<div class="card-grid">${sortedResolvers.slice(0, 4).map(r => this._resolverCard(r)).join('')}</div>`
            }
            </div>
        `;
    },

    /** Patch only the dynamic values instead of rebuilding the entire DOM */
    _patchDOM(sys, data, sortedConfigs, sortedResolvers) {
        // CPU gauge
        const cpuEl = document.getElementById('dash-cpu-gauge');
        if (cpuEl) cpuEl.innerHTML = UI.gauge(sys.cpu_percent, 'CPU', sys.cpu_percent > 80 ? 'var(--red)' : 'var(--accent)');

        // RAM gauge
        const ramEl = document.getElementById('dash-ram-gauge');
        if (ramEl) ramEl.innerHTML = UI.gauge(sys.memory_percent, 'RAM', sys.memory_percent > 85 ? 'var(--red)' : 'var(--cyan)');

        // Stat cards — update just values
        UI.patchStatCard('dash-uptime', UI.formatUptime(sys.uptime_seconds), `Load: ${sys.load_avg_1.toFixed(2)}`);
        UI.patchStatCard('dash-net-up', (sys.net_sent_rate_kbps).toFixed(1) + ' KB/s', UI.formatBytes(sys.net_sent_bytes) + ' total');
        UI.patchStatCard('dash-net-down', (sys.net_recv_rate_kbps).toFixed(1) + ' KB/s', UI.formatBytes(sys.net_recv_bytes) + ' total');
        UI.patchStatCard('dash-disk', sys.disk_percent.toFixed(1) + '%', sys.disk_used_gb.toFixed(1) + ' / ' + sys.disk_total_gb.toFixed(1) + ' GB');

        // Summary cards
        UI.patchStatCard('dash-configs', data.total_configurations, `${data.running_configurations} running · ${data.healthy_configurations} healthy`);
        UI.patchStatCard('dash-resolvers', data.total_resolvers, `${data.active_resolvers} active · ${data.dead_resolvers} dead`);
        UI.patchStatCard('dash-haproxy', data.haproxy_running ? 'Active' : 'Inactive');

        // Top configs
        const cfgSection = document.getElementById('dash-top-configs');
        if (cfgSection) {
            const gridEl = cfgSection.querySelector('.card-grid');
            if (gridEl) {
                gridEl.innerHTML = sortedConfigs.slice(0, 4).map(c => this._configCard(c)).join('');
            }
        }

        // Top resolvers
        const resSection = document.getElementById('dash-top-resolvers');
        if (resSection) {
            const gridEl = resSection.querySelector('.card-grid');
            if (gridEl) {
                gridEl.innerHTML = sortedResolvers.slice(0, 4).map(r => this._resolverCard(r)).join('');
            }
        }
    },

    /** Update chart data in-place (no destroy/recreate) */
    _updateChart() {
        const existing = Charts._instances['dashboard-sys'];
        if (existing) {
            // Update existing chart data in place
            existing.data.labels = [...this._timeLabels];
            existing.data.datasets[0].data = [...this._cpuHistory];
            existing.data.datasets[1].data = [...this._ramHistory];
            existing.update('none'); // skip animation for performance
        } else {
            Charts.systemChart(
                'dashboard-system-chart', 'dashboard-sys',
                this._cpuHistory, this._ramHistory, this._timeLabels
            );
        }
    },

    _configCard(c) {
        return `
        <div class="card" onclick="ConfigurationsPage.showDetail(${c.id})">
            <div class="card-header">
                <div>
                    <div class="card-title">${esc(c.name)}</div>
                    <div class="card-subtitle">${c.transport_type.toUpperCase()} · ${c.backend_type}</div>
                </div>
                <div style="display:flex;gap:6px;">
                    ${UI.badge(c.status)}
                    ${UI.badge(c.health)}
                </div>
            </div>
            ${c.socks_port ? `
            <div class="card-listen" style="border-left:3px solid var(--green);">
                <span>🧦 SOCKS5 → ${c.socks_address}:${c.socks_port}</span>
                <button class="copy-btn" onclick="event.stopPropagation();UI.copyText('${c.socks_address}:${c.socks_port}')">Copy</button>
            </div>` : ''}
            <div class="card-listen">
                <span>🔗 Tunnel → ${c.listen_address}:${c.listen_port}</span>
                <button class="copy-btn" onclick="event.stopPropagation();UI.copyText('${c.listen_address}:${c.listen_port}')">Copy</button>
            </div>
        </div>`;
    },

    _resolverCard(r) {
        return `
        <div class="card" onclick="ResolversPage.showDetail(${r.id})">
            <div class="card-header">
                <div>
                    <div class="card-title">${esc(r.name)}</div>
                    <div class="card-subtitle">${r.resolver_type.toUpperCase()}</div>
                </div>
                ${UI.badge(r.status)}
            </div>
            <div class="card-body">
                <div class="card-stat">
                    <span class="card-stat-label">Latency</span>
                    <span class="card-stat-value">${r.last_latency_ms != null ? r.last_latency_ms.toFixed(1) + ' ms' : '—'}</span>
                </div>
                <div class="card-stat">
                    <span class="card-stat-label">Success Rate</span>
                    <span class="card-stat-value">${(r.success_rate * 100).toFixed(1)}%</span>
                </div>
            </div>
        </div>`;
    },
};
