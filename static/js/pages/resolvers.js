/**
 * Resolvers page — list, add/edit, detail modal with latency graph.
 * With pagination, scroll preservation, and health check details.
 */

const ResolversPage = {
    _currentPage: 1,
    _perPage: 12,
    _totalPages: 1,

    async render() {
        const container = document.getElementById('page-container');
        container.innerHTML = UI.loading();

        try {
            const res = await fetch(`/api/resolvers/?page=${this._currentPage}&per_page=${this._perPage}`);
            if (!res.ok) throw new Error('Failed to load');
            const result = await res.json();

            const resolvers = Array.isArray(result) ? result : (result.items || []);
            const total = Array.isArray(result) ? resolvers.length : (result.total || resolvers.length);
            this._totalPages = Math.max(1, Math.ceil(total / this._perPage));

            container.innerHTML = `
                <div class="page-header page-header-actions">
                    <div>
                        <h1>Resolvers</h1>
                        <p>Manage DNS resolvers for tunnel transport</p>
                    </div>
                    <button class="btn btn-primary" onclick="ResolversPage.showAddForm()">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                            <path d="M12 5v14M5 12h14"/>
                        </svg>
                        Add Resolver
                    </button>
                </div>

                ${resolvers.length === 0
                    ? UI.emptyState('No resolvers yet. Add DoH, DoT, or UDP resolvers.', '+ Add Resolver', 'ResolversPage.showAddForm()')
                    : `<div class="card-grid">${resolvers.map(r => this._card(r)).join('')}</div>`
                }

                ${this._totalPages > 1 ? this._pagination() : ''}
            `;
        } catch (err) {
            container.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
        }
    },

    /** Deep-link handler for #/resolvers/detail/3 */
    handleSubRoute(parts) {
        if (parts[0] === 'detail' && parts[1]) {
            this.showDetail(parseInt(parts[1]));
        }
    },

    _pagination() {
        let pages = '';
        for (let i = 1; i <= this._totalPages; i++) {
            const active = i === this._currentPage ? ' btn-primary' : '';
            pages += `<button class="btn btn-sm${active}" onclick="ResolversPage.goToPage(${i})">${i}</button>`;
        }
        return `
        <div class="pagination">
            <button class="btn btn-sm" onclick="ResolversPage.goToPage(${this._currentPage - 1})" ${this._currentPage <= 1 ? 'disabled' : ''}>← Prev</button>
            ${pages}
            <button class="btn btn-sm" onclick="ResolversPage.goToPage(${this._currentPage + 1})" ${this._currentPage >= this._totalPages ? 'disabled' : ''}>Next →</button>
        </div>`;
    },

    goToPage(page) {
        if (page < 1 || page > this._totalPages) return;
        this._currentPage = page;
        this.render();
    },

    _card(r) {
        const rateColor = r.success_rate >= 0.9 ? 'var(--green)' : r.success_rate >= 0.5 ? 'var(--yellow)' : 'var(--red)';
        const successCount = r.total_checks - (r.failed_checks || 0);
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
                    <span class="card-stat-label">Address</span>
                    <span class="card-stat-value" style="font-size:0.78rem;word-break:break-all;">${esc(r.address)}</span>
                </div>
                ${r.total_checks > 0 ? `
                <div class="card-stat">
                    <span class="card-stat-label">Latency</span>
                    <span class="card-stat-value">${r.last_latency_ms != null ? r.last_latency_ms.toFixed(1) + ' ms' : '—'}</span>
                </div>
                <div class="card-stat">
                    <span class="card-stat-label">Success Rate</span>
                    <span class="card-stat-value" style="color:${rateColor}">${(r.success_rate * 100).toFixed(1)}%</span>
                </div>
                <div class="card-stat">
                    <span class="card-stat-label">Checks</span>
                    <span class="card-stat-value">${successCount}✓ / ${r.failed_checks || 0}✗ (${r.total_checks} total)</span>
                </div>
                ` : `
                <div class="card-stat">
                    <span class="card-stat-label">Status</span>
                    <span class="card-stat-value" style="color:var(--text-muted)">Not tested yet</span>
                </div>
                `}
                <div class="card-stat">
                    <span class="card-stat-label">Configs</span>
                    <span class="card-stat-value">${r.config_count || 0} connected</span>
                </div>
            </div>
            <div class="card-actions">
                <button class="btn btn-sm btn-success" onclick="event.stopPropagation();ResolversPage.testResolver(${r.id})">Test</button>
                <button class="btn btn-sm" onclick="event.stopPropagation();ResolversPage.showEdit(${r.id})">Edit</button>
                <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();ResolversPage.remove(${r.id})" style="margin-left:auto;">Delete</button>
            </div>
        </div>`;
    },

    async remove(id) {
        if (!confirm('Delete this resolver?')) return;
        const scrollPos = UI._saveScroll();
        try {
            await fetch(`/api/resolvers/${id}`, { method: 'DELETE' });
            UI.toast('Resolver deleted', 'success');
            await this.render();
            UI._restoreScroll(scrollPos);
        } catch (err) {
            UI.toast(`Error: ${err.message}`, 'error');
        }
    },

    async testResolver(id) {
        const scrollPos = UI._saveScroll();
        try {
            UI.toast('Testing resolver...', 'info');
            const res = await fetch(`/api/resolvers/${id}/test`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.ok) {
                UI.toast(data.message, 'success');
            } else {
                UI.toast(data.message || 'Test failed', 'error');
            }
            await this.render();
            UI._restoreScroll(scrollPos);
        } catch (err) {
            UI.toast(`Test error: ${err.message}`, 'error');
        }
    },

    async showDetail(id) {
        try {
            const [rRes, metricsRes] = await Promise.all([
                fetch(`/api/resolvers/${id}`),
                fetch(`/api/resolvers/${id}/metrics?limit=50`),
            ]);
            const resolver = await rRes.json();
            const metrics = await metricsRes.json();

            const successCount = resolver.total_checks - resolver.failed_checks;
            const rateColor = resolver.success_rate >= 0.9 ? 'var(--green)' : resolver.success_rate >= 0.5 ? 'var(--yellow)' : 'var(--red)';

            const html = `
                <div class="detail-grid">
                    <div class="detail-item">
                        <span class="detail-label">Name</span>
                        <span class="detail-value">${esc(resolver.name)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Type</span>
                        <span class="detail-value">${resolver.resolver_type.toUpperCase()}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Address</span>
                        <span class="detail-value" style="word-break:break-all;">${esc(resolver.address)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Status</span>
                        <span class="detail-value">${UI.badge(resolver.status)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Latency</span>
                        <span class="detail-value">${resolver.last_latency_ms != null ? resolver.last_latency_ms.toFixed(1) + ' ms' : '—'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Success Rate</span>
                        <span class="detail-value" style="color:${rateColor}">${(resolver.success_rate * 100).toFixed(1)}%</span>
                    </div>
                </div>

                <!-- Health check cycle details -->
                <div class="detail-section-title" style="margin-top:16px;">Health Check Cycle</div>
                <div class="detail-grid">
                    <div class="detail-item">
                        <span class="detail-label">Total Checks</span>
                        <span class="detail-value">${resolver.total_checks}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Successful</span>
                        <span class="detail-value" style="color:var(--green)">${successCount}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Failed</span>
                        <span class="detail-value" style="color:var(--red)">${resolver.failed_checks}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Last Success</span>
                        <span class="detail-value">${resolver.last_success_at ? new Date(resolver.last_success_at).toLocaleString() : 'Never'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Created</span>
                        <span class="detail-value">${new Date(resolver.created_at).toLocaleString()}</span>
                    </div>
                </div>

                <div class="chart-container">
                    <div class="chart-title">Latency History (ms)</div>
                    <div class="chart-wrapper"><canvas id="resolver-latency-chart"></canvas></div>
                </div>

                <div class="modal-footer">
                    <button class="btn btn-success" onclick="ResolversPage.testResolver(${resolver.id}); UI.closeModal();">Test Now</button>
                    <button class="btn" onclick="ResolversPage.showEdit(${resolver.id})">Edit</button>
                    <button class="btn" onclick="UI.closeModal()">Close</button>
                </div>
            `;

            UI.openModal(`Resolver — ${resolver.name}`, html, true);

            const labels = metrics.map(m => new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
            Charts.latencyChart('resolver-latency-chart', `res-lat-${id}`,
                metrics.map(m => m.latency_ms || 0), labels);

        } catch (err) {
            UI.toast('Failed to load details', 'error');
        }
    },

    showAddForm() {
        this._showForm('Add Resolver', null);
    },

    async showEdit(id) {
        try {
            UI.closeModal();
            const res = await fetch(`/api/resolvers/${id}`);
            const resolver = await res.json();
            this._showForm('Edit Resolver', resolver);
        } catch (err) {
            UI.toast('Failed to load', 'error');
        }
    },

    _showForm(title, resolver) {
        const html = `
            <form id="resolver-form" onsubmit="ResolversPage.submitForm(event, ${resolver ? resolver.id : 'null'})">
                <div class="form-group">
                    <label class="form-label">Name</label>
                    <input class="form-input" name="name" required value="${resolver ? esc(resolver.name) : ''}" placeholder="Google DoH" />
                </div>
                <div class="form-group">
                    <label class="form-label">Type</label>
                    <select class="form-select" name="resolver_type" required>
                        <option value="doh" ${resolver && resolver.resolver_type === 'doh' ? 'selected' : ''}>DoH (DNS over HTTPS)</option>
                        <option value="dot" ${resolver && resolver.resolver_type === 'dot' ? 'selected' : ''}>DoT (DNS over TLS)</option>
                        <option value="udp" ${resolver && resolver.resolver_type === 'udp' ? 'selected' : ''}>UDP</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Address</label>
                    <input class="form-input" name="address" required value="${resolver ? esc(resolver.address) : ''}" placeholder="https://dns.google/dns-query or 8.8.8.8:53" />
                </div>
                <div class="modal-footer" style="padding:16px 0 0;">
                    <button type="button" class="btn" onclick="UI.closeModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">${resolver ? 'Update' : 'Create'}</button>
                </div>
            </form>
        `;

        UI.openModal(title, html);
    },

    async submitForm(event, id) {
        event.preventDefault();
        const form = event.target;
        const data = Object.fromEntries(new FormData(form));

        const scrollPos = UI._saveScroll();
        try {
            const url = id ? `/api/resolvers/${id}` : '/api/resolvers/';
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
            UI.toast(id ? 'Resolver updated' : 'Resolver created', 'success');
            await this.render();
            UI._restoreScroll(scrollPos);
        } catch (err) {
            UI.toast(`Error: ${err.message}`, 'error');
        }
    },
};
