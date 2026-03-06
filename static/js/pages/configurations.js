/**
 * Configurations page — list, add/edit, detail modal with graphs.
 * Uses scroll preservation and bandwidth display.
 */

const ConfigurationsPage = {
    _currentPage: 1,
    _perPage: 12,
    _totalPages: 1,

    async render() {
        const container = document.getElementById('page-container');
        container.innerHTML = UI.loading();

        try {
            const res = await fetch(`/api/configurations/?page=${this._currentPage}&per_page=${this._perPage}`);
            if (!res.ok) throw new Error('Failed to load');
            const result = await res.json();

            // Handle both paginated and non-paginated responses
            const configs = Array.isArray(result) ? result : (result.items || []);
            const total = Array.isArray(result) ? configs.length : (result.total || configs.length);
            this._totalPages = Math.max(1, Math.ceil(total / this._perPage));

            container.innerHTML = `
                <div class="page-header page-header-actions">
                    <div>
                        <h1>Configurations</h1>
                        <p>Manage DNS tunnel configurations</p>
                    </div>
                    <button class="btn btn-primary" onclick="ConfigurationsPage.showAddForm()">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                            <path d="M12 5v14M5 12h14"/>
                        </svg>
                        Add Configuration
                    </button>
                </div>

                ${configs.length === 0
                    ? UI.emptyState('No tunnel configurations yet. Add your first one to get started.', '+ Add Configuration', 'ConfigurationsPage.showAddForm()')
                    : `<div class="card-grid">${configs.map(c => this._card(c)).join('')}</div>`
                }

                ${this._totalPages > 1 ? this._pagination() : ''}
            `;
        } catch (err) {
            container.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
        }

        // Start bandwidth polling for running configs
        this._pollBandwidth();
    },

    /** Deep-link handler for #/configurations/detail/5 */
    handleSubRoute(parts) {
        if (parts[0] === 'detail' && parts[1]) {
            this.showDetail(parseInt(parts[1]));
        }
    },

    _pagination() {
        let pages = '';
        for (let i = 1; i <= this._totalPages; i++) {
            const active = i === this._currentPage ? ' btn-primary' : '';
            pages += `<button class="btn btn-sm${active}" onclick="ConfigurationsPage.goToPage(${i})">${i}</button>`;
        }
        return `
        <div class="pagination">
            <button class="btn btn-sm" onclick="ConfigurationsPage.goToPage(${this._currentPage - 1})" ${this._currentPage <= 1 ? 'disabled' : ''}>← Prev</button>
            ${pages}
            <button class="btn btn-sm" onclick="ConfigurationsPage.goToPage(${this._currentPage + 1})" ${this._currentPage >= this._totalPages ? 'disabled' : ''}>Next →</button>
        </div>`;
    },

    goToPage(page) {
        if (page < 1 || page > this._totalPages) return;
        this._currentPage = page;
        this.render();
    },

    destroy() {
        if (this._bwTimer) {
            clearInterval(this._bwTimer);
            this._bwTimer = null;
        }
    },

    _bwTimer: null,
    _pollBandwidth() {
        if (this._bwTimer) clearInterval(this._bwTimer);
        const poll = async () => {
            try {
                const res = await fetch('/api/configurations/');
                if (!res.ok) return;
                const rawResult = await res.json();
                const configs = Array.isArray(rawResult) ? rawResult : (rawResult.items || []);
                for (const c of configs) {
                    if (c.status !== 'running' || !c.socks_port) continue;
                    const bwRes = await fetch(`/api/configurations/${c.id}/bandwidth`);
                    if (!bwRes.ok) continue;
                    const bw = await bwRes.json();

                    // Update bandwidth rate
                    const el = document.getElementById(`bw-${c.id}`);
                    if (el && bw.active) {
                        el.style.display = '';
                        el.querySelector('.bw-value').textContent =
                            `↑ ${bw.up_kbps} KB/s  ↓ ${bw.down_kbps} KB/s`;
                    }

                    // Update data usage
                    const dataEl = document.getElementById(`data-usage-${c.id}`);
                    if (dataEl && bw.active) {
                        dataEl.style.display = '';
                        dataEl.querySelector('.data-usage-value').textContent =
                            `↑ ${UI.formatBytes(bw.bytes_up)}  ↓ ${UI.formatBytes(bw.bytes_down)}`;
                    }
                }
            } catch (e) { }
        };
        poll();
        this._bwTimer = setInterval(poll, 3000);
    },

    _card(c) {
        return `
        <div class="card" onclick="ConfigurationsPage.showDetail(${c.id})">
            <div class="card-header">
                <div>
                    <div class="card-title">${esc(c.name)}</div>
                    <div class="card-subtitle">${c.transport_type.toUpperCase()} · ${c.domain}</div>
                </div>
                <div style="display:flex;gap:6px;flex-wrap:wrap;">
                    ${UI.badge(c.status)}
                    ${UI.badge(c.health)}
                </div>
            </div>
            <div class="card-body">
                <div class="card-stat">
                    <span class="card-stat-label">Backend</span>
                    <span class="card-stat-value">${c.backend_type.toUpperCase()}</span>
                </div>
                ${c.resolver_name ? `
                <div class="card-stat">
                    <span class="card-stat-label">Resolver</span>
                    <span class="card-stat-value">${esc(c.resolver_name)}</span>
                </div>
                ` : ''}
                <div class="card-stat" id="bw-${c.id}" style="display:none;">
                    <span class="card-stat-label">Bandwidth</span>
                    <span class="card-stat-value bw-value">—</span>
                </div>
                <div class="card-stat" id="data-usage-${c.id}" style="display:none;">
                    <span class="card-stat-label">Data Usage</span>
                    <span class="card-stat-value data-usage-value">—</span>
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
            <div class="card-actions">
                ${c.status === 'running' ? `
                    <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();ConfigurationsPage.action(${c.id},'stop')">Stop</button>
                    <button class="btn btn-sm" onclick="event.stopPropagation();ConfigurationsPage.action(${c.id},'restart')">Restart</button>
                ` : `
                    <button class="btn btn-sm btn-success" onclick="event.stopPropagation();ConfigurationsPage.action(${c.id},'start')">Start</button>
                `}
                <button class="btn btn-sm" onclick="event.stopPropagation();ConfigurationsPage.showEdit(${c.id})">Edit</button>
                <button class="btn btn-sm" onclick="event.stopPropagation();ConfigurationsPage.showLogs(${c.id},'${esc(c.name)}')">Logs</button>
                <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();ConfigurationsPage.remove(${c.id})" style="margin-left:auto;">Delete</button>
            </div>
        </div>`;
    },

    async action(id, action) {
        const scrollPos = UI._saveScroll();
        try {
            const res = await fetch(`/api/configurations/${id}/${action}`, { method: 'POST' });
            const data = await res.json();
            UI.toast(data.message || `${action} done`, res.ok ? 'success' : 'error');
            setTimeout(async () => {
                await this.render();
                UI._restoreScroll(scrollPos);
            }, 500);
        } catch (err) {
            UI.toast(`Error: ${err.message}`, 'error');
        }
    },

    async remove(id) {
        if (!confirm('Delete this configuration?')) return;
        const scrollPos = UI._saveScroll();
        try {
            await fetch(`/api/configurations/${id}`, { method: 'DELETE' });
            UI.toast('Configuration deleted', 'success');
            await this.render();
            UI._restoreScroll(scrollPos);
        } catch (err) {
            UI.toast(`Error: ${err.message}`, 'error');
        }
    },

    async showLogs(id, name) {
        try {
            const res = await fetch(`/api/configurations/${id}/logs`);
            const data = await res.json();
            UI.openModal(`Logs — ${name}`, UI.logViewer(data.logs || [], id));
        } catch (err) {
            UI.toast('Failed to load logs', 'error');
        }
    },

    async showDetail(id) {
        try {
            const [cfgRes, metricsRes] = await Promise.all([
                fetch(`/api/configurations/${id}`),
                fetch(`/api/configurations/${id}/metrics?limit=50`),
            ]);
            const cfg = await cfgRes.json();
            const metrics = await metricsRes.json();

            // Get bandwidth info
            let bwInfo = null;
            try {
                const bwRes = await fetch(`/api/configurations/${id}/bandwidth`);
                if (bwRes.ok) bwInfo = await bwRes.json();
            } catch { }

            const html = `
                <div class="detail-grid">
                    <div class="detail-item">
                        <span class="detail-label">Name</span>
                        <span class="detail-value">${esc(cfg.name)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Transport</span>
                        <span class="detail-value">${cfg.transport_type.toUpperCase()}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Domain</span>
                        <span class="detail-value">${esc(cfg.domain)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Tunnel Endpoint</span>
                        <span class="detail-value">${cfg.listen_address}:${cfg.listen_port}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">SOCKS5 Proxy</span>
                        <span class="detail-value" style="color:var(--green)">${cfg.socks_port ? cfg.socks_address + ':' + cfg.socks_port : 'Not configured'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Backend</span>
                        <span class="detail-value">${cfg.backend_type.toUpperCase()} → ${cfg.backend_host}:${cfg.backend_port || '—'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Resolver Mode</span>
                        <span class="detail-value">${cfg.resolver_mode}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Status</span>
                        <span class="detail-value">${UI.badge(cfg.status)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Health</span>
                        <span class="detail-value">${UI.badge(cfg.health)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Tunnel PID</span>
                        <span class="detail-value">${cfg.pid || '—'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">SOCKS PID</span>
                        <span class="detail-value">${cfg.socks_pid === -1 ? 'In-Process Relay' : (cfg.socks_pid || '—')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Restarts</span>
                        <span class="detail-value">${cfg.restart_count}</span>
                    </div>
                </div>

                ${bwInfo && bwInfo.active ? `
                <div class="detail-grid" style="margin-top:12px;">
                    <div class="detail-item">
                        <span class="detail-label">Upload Total</span>
                        <span class="detail-value" style="color:var(--purple)">${UI.formatBytes(bwInfo.bytes_up)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Download Total</span>
                        <span class="detail-value" style="color:var(--blue)">${UI.formatBytes(bwInfo.bytes_down)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Upload Speed</span>
                        <span class="detail-value">${bwInfo.up_kbps} KB/s</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Download Speed</span>
                        <span class="detail-value">${bwInfo.down_kbps} KB/s</span>
                    </div>
                </div>` : ''}

                <!-- Latency chart -->
                <div class="chart-container">
                    <div class="chart-title">Latency (ms)</div>
                    <div class="chart-wrapper"><canvas id="cfg-latency-chart"></canvas></div>
                </div>
                <div class="chart-container">
                    <div class="chart-title">Speed (KB/s)</div>
                    <div class="chart-wrapper"><canvas id="cfg-speed-chart"></canvas></div>
                </div>

                <div class="modal-footer">
                    <button class="btn" onclick="ConfigurationsPage.showEdit(${cfg.id})">Edit</button>
                    <button class="btn" onclick="UI.closeModal()">Close</button>
                </div>
            `;

            UI.openModal(`Configuration — ${cfg.name}`, html, true);

            // Draw charts
            const labels = metrics.map(m => new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
            Charts.latencyChart('cfg-latency-chart', `cfg-lat-${id}`,
                metrics.map(m => m.latency_ms || m.http_ping_ms || 0), labels);
            Charts.speedChart('cfg-speed-chart', `cfg-spd-${id}`,
                metrics.map(m => m.download_speed_kbps || 0),
                metrics.map(m => m.upload_speed_kbps || 0), labels);

        } catch (err) {
            UI.toast('Failed to load details', 'error');
        }
    },

    showAddForm() {
        this._showForm('Add Configuration', null);
    },

    async showEdit(id) {
        try {
            UI.closeModal();
            const res = await fetch(`/api/configurations/${id}`);
            const cfg = await res.json();
            this._showForm('Edit Configuration', cfg);
        } catch (err) {
            UI.toast('Failed to load', 'error');
        }
    },

    async _showForm(title, cfg) {
        // Load resolvers for the dropdown
        let resolvers = [];
        try {
            const res = await fetch('/api/resolvers/');
            const raw = await res.json();
            resolvers = Array.isArray(raw) ? raw : (raw.items || []);
        } catch { }

        const resolverOptions = resolvers.map(r =>
            `<option value="${r.id}" ${cfg && cfg.resolver_id === r.id ? 'selected' : ''}>${esc(r.name)} (${r.resolver_type})</option>`
        ).join('');

        const html = `
            <form id="config-form" onsubmit="ConfigurationsPage.submitForm(event, ${cfg ? cfg.id : 'null'})">
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Name</label>
                        <input class="form-input" name="name" required value="${cfg ? esc(cfg.name) : ''}" placeholder="my-tunnel" />
                    </div>
                    <div class="form-group">
                        <label class="form-label">Transport</label>
                        <select class="form-select" name="transport_type" required>
                            <option value="dnstt" ${cfg && cfg.transport_type === 'dnstt' ? 'selected' : ''}>DNSTT</option>
                            <option value="slipstream" ${cfg && cfg.transport_type === 'slipstream' ? 'selected' : ''}>Slipstream</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label">Domain</label>
                    <input class="form-input" name="domain" required value="${cfg ? esc(cfg.domain) : ''}" placeholder="t.example.com" />
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Listen Address</label>
                        <input class="form-input" name="listen_address" value="${cfg ? cfg.listen_address : '127.0.0.1'}" />
                    </div>
                    <div class="form-group">
                        <label class="form-label">Listen Port</label>
                        <div style="display:flex;gap:6px;">
                            <input class="form-input" name="listen_port" type="number" required value="${cfg ? cfg.listen_port : ''}" placeholder="1080" style="flex:1;" />
                            <button type="button" class="btn btn-sm" id="gen-listen-port">Generate</button>
                        </div>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">SOCKS5 Proxy Address</label>
                        <input class="form-input" name="socks_address" value="${cfg ? cfg.socks_address : '127.0.0.1'}" placeholder="127.0.0.1" />
                    </div>
                    <div class="form-group">
                        <label class="form-label">SOCKS5 Proxy Port</label>
                        <div style="display:flex;gap:6px;">
                            <input class="form-input" name="socks_port" type="number" value="${cfg && cfg.socks_port ? cfg.socks_port : ''}" placeholder="Auto-assigned" style="flex:1;" />
                            <button type="button" class="btn btn-sm" id="gen-socks-port">Generate</button>
                        </div>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Backend Type</label>
                        <select class="form-select" name="backend_type" required>
                            <option value="socks5" ${cfg && cfg.backend_type === 'socks5' ? 'selected' : ''}>SOCKS5</option>
                            <option value="ssh" ${cfg && cfg.backend_type === 'ssh' ? 'selected' : ''}>SSH</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Backend Host</label>
                        <input class="form-input" name="backend_host" value="${cfg ? cfg.backend_host : '127.0.0.1'}" />
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Backend Port</label>
                        <input class="form-input" name="backend_port" type="number" value="${cfg && cfg.backend_port ? cfg.backend_port : ''}" placeholder="Optional" />
                    </div>
                    <div class="form-group">
                        <label class="form-label">Backend User</label>
                        <input class="form-input" name="backend_user" value="${cfg && cfg.backend_user ? esc(cfg.backend_user) : ''}" placeholder="Optional" />
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label">Backend Password</label>
                    <input class="form-input" name="backend_password" type="password" value="${cfg && cfg.backend_password ? cfg.backend_password : ''}" placeholder="Optional" />
                </div>
                <div class="form-group">
                    <label class="form-label">Public Key (DNSTT)</label>
                    <input class="form-input" name="pubkey" value="${cfg && cfg.pubkey ? esc(cfg.pubkey) : ''}" placeholder="64 hex digits" />
                </div>
                <div class="form-group">
                    <label class="form-label">Certificate Content (Slipstream)</label>
                    <textarea class="form-input" name="cert_path" rows="4" style="font-family:var(--font-mono);font-size:0.82rem;resize:vertical;" placeholder="-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----">${cfg && cfg.cert_path ? esc(cfg.cert_path) : ''}</textarea>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Resolver Mode</label>
                        <select class="form-select" name="resolver_mode">
                            <option value="smart" ${cfg && cfg.resolver_mode === 'smart' ? 'selected' : ''}>Smart (Auto-select best)</option>
                            <option value="manual" ${cfg && cfg.resolver_mode === 'manual' ? 'selected' : ''}>Manual</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Resolver</label>
                        <select class="form-select" name="resolver_id">
                            <option value="">— Auto / None —</option>
                            ${resolverOptions}
                        </select>
                    </div>
                </div>
                <div class="modal-footer" style="padding:16px 0 0;">
                    <button type="button" class="btn" onclick="UI.closeModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">${cfg ? 'Update' : 'Create'}</button>
                </div>
            </form>
        `;

        UI.openModal(title, html);

        // Attach auto-port generation listeners
        this._addPortButtonListeners();
    },

    _addPortButtonListeners() {
        const genListen = document.getElementById('gen-listen-port');
        const genSocks = document.getElementById('gen-socks-port');
        if (genListen) {
            genListen.addEventListener('click', async () => {
                const port = await ConfigurationsPage._fetchFreePort();
                if (port) document.querySelector('input[name="listen_port"]').value = port;
            });
        }
        if (genSocks) {
            genSocks.addEventListener('click', async () => {
                const port = await ConfigurationsPage._fetchFreePort();
                if (port) document.querySelector('input[name="socks_port"]').value = port;
            });
        }
    },

    async _fetchFreePort() {
        try {
            const res = await fetch('/api/system/free-port');
            const data = await res.json();
            return data.port;
        } catch {
            UI.toast('Failed to generate port', 'error');
            return null;
        }
    },

    async submitForm(event, id) {
        event.preventDefault();
        const form = event.target;
        const data = Object.fromEntries(new FormData(form));

        // Convert numeric fields
        data.listen_port = parseInt(data.listen_port);
        if (data.socks_port) data.socks_port = parseInt(data.socks_port);
        else delete data.socks_port;
        if (data.backend_port) data.backend_port = parseInt(data.backend_port);
        else delete data.backend_port;
        if (data.resolver_id) data.resolver_id = parseInt(data.resolver_id);
        else delete data.resolver_id;
        if (!data.pubkey) delete data.pubkey;
        if (!data.cert_path) delete data.cert_path;
        if (!data.backend_user) delete data.backend_user;
        if (!data.backend_password) delete data.backend_password;
        if (!data.socks_address) delete data.socks_address;

        const scrollPos = UI._saveScroll();
        try {
            const url = id ? `/api/configurations/${id}` : '/api/configurations/';
            const method = id ? 'PUT' : 'POST';
            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Request failed');
            }
            UI.closeModal();
            UI.toast(id ? 'Configuration updated' : 'Configuration created', 'success');
            await this.render();
            UI._restoreScroll(scrollPos);
        } catch (err) {
            UI.toast(`Error: ${err.message}`, 'error');
        }
    },
};
