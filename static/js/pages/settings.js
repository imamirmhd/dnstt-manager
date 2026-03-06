/**
 * Settings page — binary paths, check intervals, process policies.
 */

const SettingsPage = {
    async render() {
        const container = document.getElementById('page-container');
        container.innerHTML = UI.loading();

        try {
            const res = await fetch('/api/system/settings');
            const settings = await res.json();

            // Build a map
            const map = {};
            for (const s of settings) map[s.key] = s.value;

            container.innerHTML = `
                <div class="page-header">
                    <h1>Settings</h1>
                    <p>Application configuration and binary paths</p>
                </div>

                <div class="card" style="max-width:700px;">
                    <div class="card-header">
                        <div>
                            <div class="card-title">Core Binary Paths</div>
                            <div class="card-subtitle">Paths to tunnel client binaries. You can manually input the full path or binary name.</div>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="form-group">
                            <label class="form-label">DNSTT Client Binary</label>
                            <input class="form-input" id="setting-dnstt_client_path" value="${esc(map.dnstt_client_path || 'dnstt-client')}" placeholder="/usr/local/bin/dnstt-client" />
                        </div>
                        <div class="form-group">
                            <label class="form-label">Slipstream Client Binary</label>
                            <input class="form-input" id="setting-slipstream_client_path" value="${esc(map.slipstream_client_path || 'slipstream-client')}" placeholder="/usr/local/bin/slipstream-client" />
                        </div>
                        <div class="form-group">
                            <label class="form-label">HAProxy Binary</label>
                            <input class="form-input" id="setting-haproxy_binary" value="${esc(map.haproxy_binary || 'haproxy')}" placeholder="/usr/sbin/haproxy" />
                        </div>
                    </div>
                </div>

                <div class="card" style="max-width:700px;">
                    <div class="card-header">
                        <div>
                            <div class="card-title">Check Intervals</div>
                            <div class="card-subtitle">How often health checks and monitoring run (in seconds)</div>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">Health Check</label>
                                <input class="form-input" id="setting-health_check_interval" type="number" value="${map.health_check_interval || 60}" min="10" />
                            </div>
                            <div class="form-group">
                                <label class="form-label">Resolver Check</label>
                                <input class="form-input" id="setting-resolver_check_interval" type="number" value="${map.resolver_check_interval || 120}" min="10" />
                            </div>
                        </div>
                        <div class="form-group" style="margin-top:12px;">
                            <label class="form-label">HTTP Health Check URL</label>
                            <input class="form-input" id="setting-health_check_url" value="${esc(map.health_check_url || 'http://gstatic.com/generate_204')}" placeholder="http://gstatic.com/generate_204" />
                            <div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px;">When testing over a proxy, this URL will be evaluated to determine real latency.</div>
                        </div>
                        <div class="form-group" style="margin-top:12px;">
                            <label class="form-label">HTTP Health Check Samples (Per config)</label>
                            <input class="form-input" id="setting-health_check_samples" type="number" value="${map.health_check_samples || 3}" min="1" max="10" />
                        </div>
                        <div class="form-group" style="margin-top:12px;">
                            <label class="form-label">System Monitor</label>
                            <input class="form-input" id="setting-system_monitor_interval" type="number" value="${map.system_monitor_interval || 5}" min="1" />
                        </div>
                    </div>
                </div>

                <div class="card" style="max-width:700px;">
                    <div class="card-header">
                        <div>
                            <div class="card-title">Process Recovery</div>
                            <div class="card-subtitle">Automatic restart policies for tunnel processes</div>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">Max Restart Attempts</label>
                                <input class="form-input" id="setting-max_restart_attempts" type="number" value="${map.max_restart_attempts || 5}" min="0" />
                            </div>
                            <div class="form-group">
                                <label class="form-label">Restart Window (seconds)</label>
                                <input class="form-input" id="setting-restart_window_seconds" type="number" value="${map.restart_window_seconds || 300}" min="30" />
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Backoff Base (seconds)</label>
                            <input class="form-input" id="setting-restart_backoff_base" type="number" step="0.1" value="${map.restart_backoff_base || 2.0}" min="1" />
                        </div>
                        <div class="form-group">
                            <label class="form-label">Resolver Dead Threshold (hours)</label>
                            <input class="form-input" id="setting-resolver_dead_threshold_hours" type="number" value="${map.resolver_dead_threshold_hours || 24}" min="1" />
                        </div>
                    </div>
                </div>

                <div style="max-width:700px;padding-bottom:32px;">
                    <button class="btn btn-primary" onclick="SettingsPage.saveAll()" style="width:100%;">Save All Settings</button>
                </div>
            `;
        } catch (err) {
            container.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
        }
    },

    async saveAll() {
        const keys = [
            'dnstt_client_path', 'slipstream_client_path', 'haproxy_binary',
            'health_check_interval', 'health_check_url', 'health_check_samples',
            'resolver_check_interval', 'system_monitor_interval',
            'max_restart_attempts', 'restart_window_seconds', 'restart_backoff_base',
            'resolver_dead_threshold_hours',
        ];

        let success = 0;
        for (const key of keys) {
            const el = document.getElementById(`setting-${key}`);
            if (!el) continue;
            try {
                const res = await fetch('/api/system/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key, value: el.value }),
                });
                if (res.ok) success++;
            } catch { }
        }

        if (success === keys.length) {
            UI.toast('All settings saved', 'success');
        } else {
            UI.toast(`Saved ${success}/${keys.length} settings`, 'error');
        }
    },
};
