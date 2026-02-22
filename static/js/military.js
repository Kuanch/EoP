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
            `<div class="region-badge"><div class="count">${c}</div><div class="label">${this.esc(r)}</div></div>`
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

// PizzINT: Pentagon Pizza Index display
const PizzINT = {
    init() {
        WS.on('pizzint', (data) => this.render(data));
        this.loadInitial();
    },
    async loadInitial() {
        try {
            const resp = await fetch('/api/pizzint');
            if (resp.ok) { const d = await resp.json(); if (d.optempo_level != null) this.render(d); }
        } catch (e) {}
    },
    render(data) {
        const panel = document.getElementById('pizzint-panel');
        if (!panel || data.optempo_level == null) return;
        panel.style.display = 'block';
        const level = data.optempo_level;
        // Level 5 = calm (green), 1 = critical (red)
        const colors = { 5: '#00e676', 4: '#448aff', 3: '#ffea00', 2: '#ff9100', 1: '#ff1744' };
        const color = colors[level] || '#e0e0e0';
        document.getElementById('pizzint-level').textContent = `Level ${level}`;
        document.getElementById('pizzint-level').style.color = color;
        document.getElementById('pizzint-label').textContent = data.optempo_label || '';
        document.getElementById('pizzint-assessment').textContent = data.assessment || '';
        // Polymarket odds
        const mkts = document.getElementById('pizzint-markets');
        if (mkts && data.polymarket && data.polymarket.length) {
            mkts.innerHTML = '<div style="font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;color:var(--text-secondary);">Polymarket Conflict Odds</div>' +
                data.polymarket.slice(0, 5).map(m => {
                const q = m.label || m.question || '';
                const p = m.probability != null ? (m.probability * 100).toFixed(1) + '%' : '';
                const color = m.probability > 0.15 ? 'var(--orange)' : m.probability > 0.05 ? 'var(--yellow)' : 'var(--text-secondary)';
                return `<div style="margin:2px 0;"><span style="color:${color};font-weight:600;">${p}</span> ${q.substring(0, 55)}</div>`;
            }).join('');
        }
        const ts = document.getElementById('pizzint-time');
        if (ts && data.timestamp) ts.textContent = timeAgo(data.timestamp);
    }
};

// Polymarket geopolitical odds display
const Polymarket = {
    init() {
        WS.on('polymarket', (data) => this.render(data));
        this.loadInitial();
    },
    async loadInitial() {
        try {
            const resp = await fetch('/api/polymarket');
            if (resp.ok) { const d = await resp.json(); if (d.length) this.render(d); }
        } catch (e) {}
    },
    render(events) {
        const panel = document.getElementById('polymarket-panel');
        const el = document.getElementById('polymarket-events');
        if (!panel || !el || !events.length) return;
        panel.style.display = 'block';
        el.innerHTML = events.map(e => {
            const pct = e.probability != null ? (e.probability * 100).toFixed(1) : '?';
            const pNum = e.probability || 0;
            const color = pNum > 0.20 ? 'var(--red)' : pNum > 0.10 ? 'var(--orange)' : pNum > 0.05 ? 'var(--yellow)' : 'var(--text-secondary)';
            const vol = e.volume > 1e6 ? (e.volume / 1e6).toFixed(1) + 'M' : e.volume > 1e3 ? (e.volume / 1e3).toFixed(0) + 'K' : Math.round(e.volume);
            return `<div style="background:var(--bg-tertiary);border:1px solid var(--border);border-left:3px solid ${color};border-radius:4px;padding:10px 12px;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <span style="font-size:22px;font-weight:700;color:${color};">${pct}%</span>
                    <span style="font-size:10px;color:var(--text-secondary);">$${vol} vol</span>
                </div>
                <div style="font-size:12px;color:var(--text-primary);margin-top:4px;line-height:1.3;">${this.esc(e.question)}</div>
            </div>`;
        }).join('');
    },
    esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
};

document.addEventListener('DOMContentLoaded', () => { Military.init(); PizzINT.init(); Polymarket.init(); });
