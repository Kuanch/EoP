// Cyber tab: threat cards and stats

const Cyber = {
    events: [],
    stats: { total_iocs: 0, active_campaigns: 0, new_cves: 0, threat_level: 'Low' },

    init() {
        WS.on('cyber', (d) => { this.events = d.events || []; this.stats = d.stats || this.stats; this.render(); });
        this.loadInitial();
    },

    async loadInitial() {
        try {
            const resp = await fetch('/api/cyber');
            if (resp.ok) {
                const d = await resp.json();
                this.events = d.events || [];
                this.stats = d.stats || this.stats;
                this.render();
            }
        } catch (e) { console.error('[Cyber] Initial load:', e); }
    },

    render() {
        this.renderStats();
        this.renderEvents();
    },

    renderStats() {
        const el = document.getElementById('cyber-stats');
        if (!el) return;
        const s = this.stats;
        const lvlClass = s.threat_level === 'Critical' ? 'critical' : s.threat_level === 'High' ? 'high' : '';
        el.innerHTML = `
            <div class="cyber-stat ${lvlClass}"><div class="value">${s.threat_level}</div><div class="label">Threat Level</div></div>
            <div class="cyber-stat"><div class="value">${s.total_iocs}</div><div class="label">Total IOCs</div></div>
            <div class="cyber-stat"><div class="value">${s.active_campaigns}</div><div class="label">Active Campaigns</div></div>
            <div class="cyber-stat"><div class="value">${s.new_cves}</div><div class="label">New CVEs Today</div></div>
        `;
    },

    renderEvents() {
        const el = document.getElementById('cyber-events');
        if (!el) return;
        el.innerHTML = this.events.map(e => `
            <div class="card threat-card severity-${e.severity}">
                <span class="severity-badge ${e.severity}">${e.severity}</span>
                <span class="source-badge">${this.esc(e.source)}</span>
                <div class="title" style="margin-top:6px">${this.esc(e.title)}</div>
                <div class="summary" style="margin-top:4px">${this.esc(e.description)}</div>
                <div class="meta" style="margin-top:6px">
                    <span>${timeAgo(e.timestamp)}</span>
                    <span>IOCs: ${e.ioc_count || 0}</span>
                </div>
            </div>
        `).join('') || '<div style="color:var(--text-secondary)">No threat events</div>';
    },

    esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
};

document.addEventListener('DOMContentLoaded', () => {
    Cyber.init();

    // Cyber alerts toggle — syncs with threat_rules.json sources.cyber
    const toggle = document.getElementById('cyber-alerts-toggle');
    if (toggle) {
        fetch('/api/threats/config').then(r => r.ok ? r.json() : null).then(cfg => {
            if (cfg) toggle.checked = cfg.sources?.cyber ?? true;
        }).catch(() => {});

        toggle.addEventListener('change', async () => {
            try {
                const resp = await fetch('/api/threats/config');
                if (!resp.ok) return;
                const cfg = await resp.json();
                cfg.sources.cyber = toggle.checked;
                await fetch('/api/threats/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(cfg),
                });
            } catch (e) { console.error('[Cyber] Toggle error:', e); }
        });
    }
});
