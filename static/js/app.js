/**
 * SPA Router + WebSocket + global state
 */

const App = {
    ws: null,
    currentPage: null,
    refreshTimer: null,

    pages: {
        dashboard: DashboardPage,
        configurations: ConfigurationsPage,
        resolvers: ResolversPage,
        balancer: BalancerPage,
        settings: SettingsPage,
    },

    init() {
        // Modal close handlers
        document.getElementById('modal-close').addEventListener('click', UI.closeModal);
        document.getElementById('modal-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) UI.closeModal();
        });

        // Keyboard
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') UI.closeModal();
        });

        // Listen for hash changes
        window.addEventListener('hashchange', () => this.route());

        // Connect WebSocket
        this.connectWS();

        // Initial route
        this.route();
    },

    route() {
        const hash = location.hash.slice(2) || 'dashboard'; // #/configurations -> configurations
        const parts = hash.split('/');
        const pageName = parts[0] || 'dashboard';
        const subRoute = parts.slice(1); // e.g. ['detail', '5']
        const page = this.pages[pageName];

        // Update nav active state
        document.querySelectorAll('.nav-item').forEach(el => {
            el.classList.toggle('active', el.dataset.page === pageName);
        });

        // Clear auto-refresh
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }

        // Destroy previous page if it has a destroy method
        if (this.currentPage && this.pages[this.currentPage] && this.pages[this.currentPage].destroy) {
            this.pages[this.currentPage].destroy();
        }

        if (page) {
            this.currentPage = pageName;

            // Pass sub-route to page if it supports it
            if (subRoute.length > 0 && page.handleSubRoute) {
                page.render().then(() => page.handleSubRoute(subRoute));
            } else {
                page.render();
            }

            // Auto-refresh dashboard using lightweight refresh()
            if (pageName === 'dashboard') {
                this.refreshTimer = setInterval(() => {
                    if (page.refresh) {
                        page.refresh();
                    } else {
                        page.render();
                    }
                }, 10000);
            }
        }
    },

    connectWS() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${location.host}/ws`;

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('WebSocket connected');
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWSMessage(data);
                } catch { }
            };

            this.ws.onclose = () => {
                console.log('WebSocket disconnected, reconnecting in 5s…');
                setTimeout(() => this.connectWS(), 5000);
            };

            this.ws.onerror = () => {
                this.ws.close();
            };
        } catch {
            setTimeout(() => this.connectWS(), 5000);
        }
    },

    handleWSMessage(data) {
        // Can extend this to update UI in real-time
        if (data.type === 'system_stats' && this.currentPage === 'dashboard') {
            // Optionally update just the gauges without full re-render
        }
    },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
