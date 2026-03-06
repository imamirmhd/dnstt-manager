/**
 * Chart.js helpers — consistent styling, instance tracking for reuse.
 */

const Charts = {
    /** Chart instance registry keyed by a unique string id. */
    _instances: {},

    /** Destroy a tracked instance by key. */
    destroy(key) {
        if (this._instances[key]) {
            this._instances[key].destroy();
            delete this._instances[key];
        }
    },

    /** Generic line chart. Returns Chart instance. */
    line(canvasId, key, datasets, labels, options = {}) {
        // Destroy previous if same key
        this.destroy(key);

        const canvas = document.getElementById(canvasId);
        if (!canvas) return null;

        const defaults = {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            scales: {
                x: {
                    ticks: { color: '#8794a7', maxRotation: 0, maxTicksLimit: 8, font: { size: 10 } },
                    grid: { color: 'rgba(255,255,255,0.04)' },
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: '#8794a7', font: { size: 10 } },
                    grid: { color: 'rgba(255,255,255,0.04)' },
                },
            },
            plugins: {
                legend: { display: datasets.length > 1, labels: { color: '#c5cdd8', boxWidth: 14, padding: 12, font: { size: 11 } } },
            },
            interaction: { mode: 'index', intersect: false },
        };

        const chart = new Chart(canvas, {
            type: 'line',
            data: { labels, datasets },
            options: { ...defaults, ...options },
        });

        this._instances[key] = chart;
        return chart;
    },

    /** System chart — CPU + RAM */
    systemChart(canvasId, key, cpuData, ramData, labels) {
        return this.line(canvasId, key, [
            {
                label: 'CPU %',
                data: cpuData,
                borderColor: '#6c5ce7',
                backgroundColor: 'rgba(108, 92, 231, 0.08)',
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                tension: 0.3,
            },
            {
                label: 'RAM %',
                data: ramData,
                borderColor: '#00cec9',
                backgroundColor: 'rgba(0, 206, 201, 0.08)',
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                tension: 0.3,
            },
        ], labels);
    },

    /** Latency chart — single line */
    latencyChart(canvasId, key, latencyData, labels) {
        return this.line(canvasId, key, [
            {
                label: 'Latency (ms)',
                data: latencyData,
                borderColor: '#fdcb6e',
                backgroundColor: 'rgba(253, 203, 110, 0.08)',
                borderWidth: 2,
                pointRadius: 2,
                fill: true,
                tension: 0.3,
            },
        ], labels);
    },

    /** Speed chart — download + upload */
    speedChart(canvasId, key, downloadData, uploadData, labels) {
        return this.line(canvasId, key, [
            {
                label: 'Download (KB/s)',
                data: downloadData,
                borderColor: '#74b9ff',
                backgroundColor: 'rgba(116, 185, 255, 0.08)',
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                tension: 0.3,
            },
            {
                label: 'Upload (KB/s)',
                data: uploadData,
                borderColor: '#a29bfe',
                backgroundColor: 'rgba(162, 155, 254, 0.08)',
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                tension: 0.3,
            },
        ], labels);
    },
};
