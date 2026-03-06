/**
 * HAProxy page — intelligent mode toggle, listen config, active backends.
 */

const HAProxyPage = {
    async render() {
        const container = document.getElementById('page-container');
        container.innerHTML = UI.loading();

        try {
            const res = await fetch('/api/system/haproxy');
            if (!res.ok) throw new Error('Failed to load');
            const status = await res.json();

            const cfg = status.config;
            const enabled = cfg ? cfg.enabled : false;
            const listenAddr = cfg ? cfg.listen_address : '0.0.0.0';
            const listenPort = cfg ? cfg.listen_port : 1080;
            const statsEnabled = cfg ? cfg.stats_enabled : true;
            const statsPort = cfg ? cfg.stats_port : 8404;

            container.innerHTML = `
                <div class="page-header">
                    <h1>HAProxy — Intelligent Mode</h1>
                    <p>Automatically load balance between healthy tunnel configurations</p>
                </div>

                <div class="stat-grid" style="margin-bottom:24px;">
                    ${UI.statCard('Status', status.running ? 'Running' : 'Stopped', status.pid ? 'PID: ' + status.pid : '',
                status.running ? 'var(--green)' : 'var(--text-muted)')}
                    ${UI.statCard('Active Backends', status.active_backends, 'Healthy running tunnels', 'var(--cyan)')}
                </div>

                <div class="card" style="cursor:default;max-width:600px;">
                    <div class="card-header">
                        <div class="card-title">Configuration</div>
                    </div>
                    <form id="haproxy-form" onsubmit="HAProxyPage.save(event)">
                        <div class="form-group">
                            <label class="form-toggle">
                                <input type="checkbox" name="enabled" ${enabled ? 'checked' : ''} />
                                <div class="toggle-switch"></div>
                                <span style="font-size:0.92rem;">Enable Intelligent Mode</span>
                            </label>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">Listen Address</label>
                                <input class="form-input" name="listen_address" value="${listenAddr}" />
                            </div>
                            <div class="form-group">
                                <label class="form-label">Listen Port</label>
                                <input class="form-input" name="listen_port" type="number" value="${listenPort}" />
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="form-toggle">
                                <input type="checkbox" name="stats_enabled" ${statsEnabled ? 'checked' : ''} />
                                <div class="toggle-switch"></div>
                                <span style="font-size:0.92rem;">Enable Stats Dashboard</span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Stats Port</label>
                            <input class="form-input" name="stats_port" type="number" value="${statsPort}" style="max-width:200px;" />
                        </div>
                        <div style="display:flex;gap:10px;margin-top:16px;">
                            <button type="submit" class="btn btn-primary">Save & Apply</button>
                            ${status.running ? `<button type="button" class="btn" onclick="HAProxyPage.reload()">Reload Config</button>` : ''}
                        </div>
                    </form>
                </div>

                ${enabled ? `
                <div class="card-listen" style="max-width:600px;margin-top:16px;">
                    <span>HAProxy listens on ${listenAddr}:${listenPort}</span>
                    <button class="copy-btn" onclick="UI.copyText('${listenAddr}:${listenPort}')">Copy</button>
                </div>
                ` : ''}
            `;
        } catch (err) {
            container.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
        }
    },

    async save(event) {
        event.preventDefault();
        const form = event.target;
        const fd = new FormData(form);
        const data = {
            enabled: fd.has('enabled'),
            listen_address: fd.get('listen_address'),
            listen_port: parseInt(fd.get('listen_port')),
            stats_enabled: fd.has('stats_enabled'),
            stats_port: parseInt(fd.get('stats_port')),
        };

        try {
            const res = await fetch('/api/system/haproxy', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            const result = await res.json();
            UI.toast(result.message || 'HAProxy config saved', res.ok ? 'success' : 'error');
            setTimeout(() => this.render(), 500);
        } catch (err) {
            UI.toast(`Error: ${err.message}`, 'error');
        }
    },

    async reload() {
        try {
            const res = await fetch('/api/system/haproxy/reload', { method: 'POST' });
            const data = await res.json();
            UI.toast(data.message || 'Reloaded', res.ok ? 'success' : 'error');
        } catch (err) {
            UI.toast(`Error: ${err.message}`, 'error');
        }
    },
};
