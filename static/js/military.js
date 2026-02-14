// Military tab: asset table and region summary

const Military = {
    assets: [],
    filter: 'all',

    init() {
        WS.on('military', (data) => { this.assets = data; this.render(); });
        this.loadInitial();
    },

    async loadInitial() {
        try {
            const resp = await fetch('/api/military');
            if (resp.ok) { this.assets = await resp.json(); this.render(); }
        } catch (e) { console.error('[Military] Initial load:', e); }
    },

    render() {
        this.renderSummary();
        this.renderTable();
        // Notify map module if available
        if (typeof MapView !== 'undefined' && MapView.updateMilitary) {
            MapView.updateMilitary(this.assets);
        }
    },

    renderSummary() {
        const el = document.getElementById('military-summary');
        if (!el) return;
        const regions = {};
        this.assets.forEach(a => {
            regions[a.region] = (regions[a.region] || 0) + 1;
        });
        el.innerHTML = Object.entries(regions).map(([r, c]) =>
            `<div class="region-badge"><div class="count">${c}</div><div class="label">${r}</div></div>`
        ).join('') || '<div style="color:var(--text-secondary)">No assets tracked</div>';
    },

    renderTable() {
        const el = document.getElementById('military-table');
        if (!el) return;
        const filtered = this.filter === 'all' ? this.assets : this.assets.filter(a => a.type === this.filter);
        const tbody = filtered.map(a =>
            `<tr>
                <td>${this.esc(a.callsign || 'N/A')}</td>
                <td>${this.esc(a.origin_country || '')}</td>
                <td>${a.altitude ? Math.round(a.altitude) + ' m' : '-'}</td>
                <td>${a.heading ? Math.round(a.heading) + '°' : '-'}</td>
                <td>${this.esc(a.region)}</td>
                <td>${this.esc(a.source)}</td>
            </tr>`
        ).join('');
        el.innerHTML = `<table class="asset-table">
            <thead><tr><th>Callsign</th><th>Country</th><th>Altitude</th><th>Heading</th><th>Region</th><th>Source</th></tr></thead>
            <tbody>${tbody || '<tr><td colspan="6" style="text-align:center;color:var(--text-secondary)">No assets tracked</td></tr>'}</tbody>
        </table>`;
    },

    esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
};

document.addEventListener('DOMContentLoaded', () => Military.init());
