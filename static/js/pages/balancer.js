/**
 * Balancer Page
 * Manages DNS Balancer and Data Balancer configurations.
 */

const BalancerPage = {
    _detailTimer: null,
    _speedHistory: { up: [], down: [], labels: [] },
    _maxSpeedPoints: 30,

    async render() {
        const container = document.getElementById('page-container');
        container.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;

        try {
            const [dnsRes, dnsStatusRes, dataRes, dataStatusRes] = await Promise.all([
                fetch('/api/balancer/dns'),
                fetch('/api/balancer/dns/status'),
                fetch('/api/balancer/data'),
                fetch('/api/balancer/data/status')
            ]);

            const dnsConfig = await dnsRes.json();
            const dnsStatus = await dnsStatusRes.json();
            const dataConfig = await dataRes.json();
            const dataStatus = await dataStatusRes.json();

            container.innerHTML = `
                <div class="page-header">
                    <div>
                        <h1 class="page-title">Load Balancer</h1>
                        <p class="page-subtitle">Manage built-in DNS and TCP load balancing.</p>
                    </div>
                </div>

                <div class="card-grid">
                    <!-- DNS Balancer -->
                    <div class="card">
                        <div class="card-header">
                            <div>
                                <div class="card-title">DNS Balancer</div>
                                <div class="card-subtitle">Local DNS proxy & resolver selection</div>
                            </div>
                            ${UI.badge(dnsStatus.running ? 'running' : 'stopped')}
                        </div>
                        <div class="card-body">
                            <form id="dns-balancer-form" class="card-form" onsubmit="event.preventDefault();BalancerPage.saveDns()">
                                <div class="card-stat-container" style="margin-top:0; margin-bottom:16px;">
                                    <div class="card-stat">
                                        <span class="card-stat-label">Queries Handled</span>
                                        <span class="card-stat-value">${dnsStatus.queries_handled}</span>
                                    </div>
                                    <div class="card-stat" style="margin-top:8px;">
                                        <span class="card-stat-label">Queries Failed</span>
                                        <span class="card-stat-value" style="color:var(--red);">${dnsStatus.queries_failed}</span>
                                    </div>
                                </div>
                                <div style="margin-top:auto; display:flex; flex-direction:column;">
                                    <div class="form-group">
                                        <label class="form-label">Listen Address</label>
                                        <input type="text" class="form-input" id="dns-listen" value="${esc(dnsConfig.listen_address)}" required>
                                    </div>
                                    <div style="display:flex;gap:12px;" class="form-row-responsive">
                                        <div class="form-group" style="flex:1;">
                                            <label class="form-label">UDP Port</label>
                                            <input type="number" class="form-input" id="dns-udp" value="${dnsConfig.udp_port}" min="0" max="65535">
                                        </div>
                                        <div class="form-group" style="flex:1;">
                                            <label class="form-label">DoT Port</label>
                                            <input type="number" class="form-input" id="dns-dot" value="${dnsConfig.dot_port}" min="0" max="65535">
                                        </div>
                                        <div class="form-group" style="flex:1;">
                                            <label class="form-label">DoH Port</label>
                                            <input type="number" class="form-input" id="dns-doh" value="${dnsConfig.doh_port}" min="0" max="65535">
                                        </div>
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">Selection Strategy</label>
                                        <select class="form-select" id="dns-strategy">
                                            <option value="least_latency" ${dnsConfig.strategy === 'least_latency' ? 'selected' : ''}>Least Latency</option>
                                            <option value="round_robin" ${dnsConfig.strategy === 'round_robin' ? 'selected' : ''}>Round Robin</option>
                                            <option value="weighted" ${dnsConfig.strategy === 'weighted' ? 'selected' : ''}>Weighted Reliability</option>
                                        </select>
                                    </div>
                                </div>
                            </form>
                        </div>
                        <div class="card-actions">
                            ${dnsStatus.running ? `
                                <button class="btn btn-danger" onclick="BalancerPage.action('dns', 'stop')">Stop</button>
                                <button class="btn btn-sm" onclick="BalancerPage.showDetail('dns')">Show Details</button>
                            ` : `
                                <button class="btn btn-success" onclick="BalancerPage.action('dns', 'start')">Start</button>
                            `}
                            <button type="submit" form="dns-balancer-form" class="btn btn-primary" style="margin-left:auto;">Save Config</button>
                        </div>
                    </div>

                    <!-- Data Balancer -->
                    <div class="card">
                        <div class="card-header">
                            <div>
                                <div class="card-title">Data Balancer</div>
                                <div class="card-subtitle">TCP proxy across SOCKS configs</div>
                            </div>
                            ${UI.badge(dataStatus.running ? 'running' : 'stopped')}
                        </div>
                        <div class="card-body">
                            <form id="data-balancer-form" class="card-form" onsubmit="event.preventDefault();BalancerPage.saveData()">
                                <div class="card-stat-container" style="margin-top:0; margin-bottom:16px;">
                                    <div class="card-stat">
                                        <span class="card-stat-label">Active Connections</span>
                                        <span class="card-stat-value" style="color:var(--green);">${dataStatus.active_connections}</span>
                                    </div>
                                    <div class="card-stat" style="margin-top:8px;">
                                        <span class="card-stat-label">Total Connections</span>
                                        <span class="card-stat-value">${dataStatus.total_connections}</span>
                                    </div>


                                </div>
                                <div style="margin-top:auto; display:flex; flex-direction:column;">
                                    <div class="form-group">
                                        <label class="form-label">Listen Address</label>
                                        <input type="text" class="form-input" id="data-listen" value="${esc(dataConfig.listen_address)}" required>
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">Listen Port (TCP)</label>
                                        <input type="number" class="form-input" id="data-port" value="${dataConfig.listen_port}" min="1" max="65535" required>
                                    </div>
                                    <div class="form-group">
                                        <label class="form-label">Routing Strategy</label>
                                        <select class="form-select" id="data-strategy">
                                            <option value="round_robin" ${dataConfig.strategy === 'round_robin' ? 'selected' : ''}>Round Robin</option>
                                            <option value="least_connections" ${dataConfig.strategy === 'least_connections' ? 'selected' : ''}>Least Connections</option>
                                            <option value="least_latency" ${dataConfig.strategy === 'least_latency' ? 'selected' : ''}>Least Latency</option>
                                        </select>
                                    </div>
                                </div>
                            </form>
                        </div>
                        <div class="card-actions">
                            ${dataStatus.running ? `
                                <button class="btn btn-danger" onclick="BalancerPage.action('data', 'stop')">Stop</button>
                                <button class="btn btn-sm" onclick="BalancerPage.showDetail('data')">Show Details</button>
                            ` : `
                                <button class="btn btn-success" onclick="BalancerPage.action('data', 'start')">Start</button>
                            `}
                            <button type="submit" form="data-balancer-form" class="btn btn-primary" style="margin-left:auto;">Save Config</button>
                        </div>
                    </div>
                </div>
            `;
        } catch (err) {
            container.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
        }
    },

    destroy() {
        this._stopDetailPolling();
    },

    // --- Modal Detail Views ---

    async showDetail(type) {
        try {
            const res = await fetch(`/api/balancer/${type}/status`);
            const status = await res.json();

            if (!status.running) {
                UI.toast(`The ${type.toUpperCase()} balancer is not running.`, 'info');
                return;
            }

            if (type === 'dns') {
                const html = `
                <div class="detail-grid">
                    <div class="detail-item">
                        <span class="detail-label">Queries Handled</span>
                        <span class="detail-value" style="color:var(--green)">${status.queries_handled}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Queries Failed</span>
                        <span class="detail-value" style="color:var(--red)">${status.queries_failed}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">UDP Active</span>
                        <span class="detail-value">${status.udp_active ? '✓ Yes' : '✗ No'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">DoT Active</span>
                        <span class="detail-value">${status.dot_active ? '✓ Yes' : '✗ No'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">DoH Active</span>
                        <span class="detail-value">${status.doh_active ? '✓ Yes' : '✗ No'}</span>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-danger" onclick="BalancerPage.action('dns', 'stop'); UI.closeModal();">Stop Balancer</button>
                    <button class="btn" onclick="UI.closeModal()">Close</button>
                </div>
                `;
                UI.openModal('DNS Balancer Status', html);
            } else if (type === 'data') {
                // Initialize speed history on open
                this._speedHistory = { up: [], down: [], labels: [] };

                const backendsHTML = status.backends.length > 0 ? status.backends.map(b => `
                    <div class="balancer-backend-row">
                        <span class="backend-id">Config #${b.config_id}</span>
                        <span class="backend-addr">${b.address}</span>
                        <span class="backend-stat">${b.active} active / ${b.total || 0} total</span>
                        ${b.bytes_up !== undefined ? `
                        <span class="backend-stat">↑ ${UI.formatBytes(b.bytes_up)} ↓ ${UI.formatBytes(b.bytes_down)}</span>
                        ` : ''}
                        ${b.latency_ms !== undefined ? `
                        <span class="backend-stat">Latency: ${b.latency_ms != null ? b.latency_ms.toFixed(1) + 'ms' : '—'}</span>
                        ` : ''}
                        ${b.ping_ms !== undefined ? `
                        <span class="backend-stat">Ping: ${b.ping_ms != null ? b.ping_ms.toFixed(1) + 'ms' : '—'}</span>
                        ` : ''}
                    </div>
                `).join('') : '<div style="color:var(--text-muted);font-size:0.85rem;">No backends active</div>';

                const html = `
                <div class="detail-grid" id="data-balancer-metrics">
                    <div class="detail-item">
                        <span class="detail-label">Active Connections</span>
                        <span class="detail-value" id="db-active-conn" style="color:var(--green)">${status.active_connections}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Total Connections</span>
                        <span class="detail-value" id="db-total-conn">${status.total_connections}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Data Uploaded</span>
                        <span class="detail-value" id="db-bytes-up" style="color:var(--purple)">${UI.formatBytes(status.bytes_up || 0)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Data Downloaded</span>
                        <span class="detail-value" id="db-bytes-down" style="color:var(--blue)">${UI.formatBytes(status.bytes_down || 0)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Avg Latency</span>
                        <span class="detail-value" id="db-latency">${status.avg_latency_ms != null ? status.avg_latency_ms.toFixed(1) + ' ms' : '—'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Avg Ping</span>
                        <span class="detail-value" id="db-ping">${status.avg_ping_ms != null ? status.avg_ping_ms.toFixed(1) + ' ms' : '—'}</span>
                    </div>
                </div>

                <!-- Speed chart -->
                <div class="chart-container" style="margin-top:16px;">
                    <div class="chart-title">Throughput (KB/s)</div>
                    <div class="chart-wrapper"><canvas id="balancer-speed-chart"></canvas></div>
                </div>

                <!-- Per-backend breakdown -->
                <div class="detail-section-title" style="margin-top:16px;">Backend Instances</div>
                <div class="balancer-backends-list" id="data-balancer-backends">
                    ${backendsHTML}
                </div>

                <!-- Logs -->
                <div class="detail-section-title" style="margin-top:16px;">Recent Events</div>
                <div class="log-viewer" id="balancer-logs" style="max-height:160px; margin-bottom: 20px;">${(status.logs || []).length > 0
                        ? status.logs.map(l => `<div class="log-line">${esc(l)}</div>`).join('')
                        : '<div class="log-line" style="color:var(--text-muted)">No events yet</div>'
                    }</div>

                <div class="modal-footer">
                    <button class="btn btn-danger" onclick="BalancerPage.action('data', 'stop'); UI.closeModal();">Stop Balancer</button>
                    <button class="btn" onclick="UI.closeModal()">Close</button>
                </div>
                `;

                UI.openModal('Data Balancer Status', html, true);
                this._drawSpeedChart();
                this._startDetailPolling();
            }
        } catch (err) {
            UI.toast(`Error loading details: ${err.message}`, 'error');
        }
    },

    _startDetailPolling() {
        this._stopDetailPolling();
        this._detailTimer = setInterval(async () => {
            // Check if the modal is still open by looking for our element
            const metricsEl = document.getElementById('data-balancer-metrics');
            if (!metricsEl) {
                this._stopDetailPolling();
                return;
            }

            try {
                const statusRes = await fetch('/api/balancer/data/status');
                const status = await statusRes.json();

                // Patch metric values
                const el = (id) => document.getElementById(id);
                if (el('db-active-conn')) el('db-active-conn').textContent = status.active_connections;
                if (el('db-total-conn')) el('db-total-conn').textContent = status.total_connections;
                if (el('db-bytes-up')) el('db-bytes-up').textContent = UI.formatBytes(status.bytes_up || 0);
                if (el('db-bytes-down')) el('db-bytes-down').textContent = UI.formatBytes(status.bytes_down || 0);
                if (el('db-latency')) el('db-latency').textContent = status.avg_latency_ms != null ? status.avg_latency_ms.toFixed(1) + ' ms' : '—';
                if (el('db-ping')) el('db-ping').textContent = status.avg_ping_ms != null ? status.avg_ping_ms.toFixed(1) + ' ms' : '—';

                // Update speed history
                const upKbps = status.up_kbps || 0;
                const downKbps = status.down_kbps || 0;
                this._speedHistory.up.push(upKbps);
                this._speedHistory.down.push(downKbps);
                this._speedHistory.labels.push(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
                if (this._speedHistory.up.length > this._maxSpeedPoints) {
                    this._speedHistory.up.shift();
                    this._speedHistory.down.shift();
                    this._speedHistory.labels.shift();
                }

                // Update speed chart in-place
                const chart = Charts._instances['balancer-speed'];
                if (chart) {
                    chart.data.labels = [...this._speedHistory.labels];
                    chart.data.datasets[0].data = [...this._speedHistory.down];
                    chart.data.datasets[1].data = [...this._speedHistory.up];
                    chart.update('none');
                }

                // Update backends list
                const backendsEl = el('data-balancer-backends');
                if (backendsEl && status.backends) {
                    backendsEl.innerHTML = status.backends.length > 0
                        ? status.backends.map(b => `
                            <div class="balancer-backend-row">
                                <span class="backend-id">Config #${b.config_id}</span>
                                <span class="backend-addr">${b.address}</span>
                                <span class="backend-stat">${b.active} active / ${b.total || 0} total</span>
                                ${b.bytes_up !== undefined ? `<span class="backend-stat">↑ ${UI.formatBytes(b.bytes_up)} ↓ ${UI.formatBytes(b.bytes_down)}</span>` : ''}
                                ${b.latency_ms !== undefined ? `<span class="backend-stat">Latency: ${b.latency_ms != null ? b.latency_ms.toFixed(1) + 'ms' : '—'}</span>` : ''}
                                ${b.ping_ms !== undefined ? `<span class="backend-stat">Ping: ${b.ping_ms != null ? b.ping_ms.toFixed(1) + 'ms' : '—'}</span>` : ''}
                            </div>
                        `).join('')
                        : '<div style="color:var(--text-muted);font-size:0.85rem;">No backends active</div>';
                }

                // Update logs
                const logsEl = el('balancer-logs');
                if (logsEl && status.logs) {
                    const wasScrolledToBottom = logsEl.scrollHeight - logsEl.clientHeight <= logsEl.scrollTop + 10;
                    logsEl.innerHTML = status.logs.length > 0
                        ? status.logs.map(l => `<div class="log-line">${esc(l)}</div>`).join('')
                        : '<div class="log-line" style="color:var(--text-muted)">No events yet</div>';
                    if (wasScrolledToBottom) {
                        logsEl.scrollTop = logsEl.scrollHeight;
                    }
                }

                // Auto close modal if it stopped running
                if (!status.running) {
                    UI.closeModal();
                    this.render(); // update card to show 'stopped'
                }
            } catch (e) { }
        }, 3000);
    },

    _stopDetailPolling() {
        if (this._detailTimer) {
            clearInterval(this._detailTimer);
            this._detailTimer = null;
        }
    },

    _drawSpeedChart() {
        Charts.speedChart(
            'balancer-speed-chart', 'balancer-speed',
            this._speedHistory.down,
            this._speedHistory.up,
            this._speedHistory.labels
        );
    },

    // --- Save & actions ---

    async saveDns() {
        const body = {
            listen_address: document.getElementById('dns-listen').value,
            udp_port: parseInt(document.getElementById('dns-udp').value) || 0,
            dot_port: parseInt(document.getElementById('dns-dot').value) || 0,
            doh_port: parseInt(document.getElementById('dns-doh').value) || 0,
            strategy: document.getElementById('dns-strategy').value
        };
        try {
            const res = await fetch('/api/balancer/dns', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (res.ok) {
                UI.toast('DNS Balancer config saved', 'success');
            } else {
                throw new Error(await res.text());
            }
        } catch (err) {
            UI.toast(err.message, 'error');
        }
    },

    async saveData() {
        const body = {
            listen_address: document.getElementById('data-listen').value,
            listen_port: parseInt(document.getElementById('data-port').value),
            strategy: document.getElementById('data-strategy').value
        };
        try {
            const res = await fetch('/api/balancer/data', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (res.ok) {
                UI.toast('Data Balancer config saved', 'success');
            } else {
                throw new Error(await res.text());
            }
        } catch (err) {
            UI.toast(err.message, 'error');
        }
    },

    async action(type, actionName) {
        try {
            const res = await fetch(`/api/balancer/${type}/${actionName}`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.ok) {
                UI.toast(data.message, 'success');
                if (actionName === 'start') {
                    // Automatically open details once started
                    this.showDetail(type);
                }
            } else {
                UI.toast(data.message || `Failed to ${actionName}`, 'error');
            }
            this.render();
        } catch (err) {
            UI.toast(`Error: ${err.message}`, 'error');
        }
    }
};
