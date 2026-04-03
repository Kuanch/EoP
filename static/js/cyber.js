// Cyber tab: IODA outage map, cyber news, CISA KEV, correlations

const Cyber = {
    map: null,
    outageLayer: null,
    watchedLayer: null,
    outages: [],
    cyberNews: [],
    cves: [],
    stats: { active_outages: 0, countries_affected: 0, new_cves: 0, feeds_ok: 0 },
    correlations: [],
    watchedSignals: {},
    lastUpdated: null,
    _initialized: false,

    init() {
        WS.on('cyber', (d) => {
            this.outages = d.outages || [];
            this.cyberNews = d.cyber_news || [];
            this.cves = d.cves || [];
            this.stats = d.stats || this.stats;
            this.correlations = d.correlations || [];
            this.watchedSignals = d.watched_signals || {};
            this.lastUpdated = d.last_updated || null;
            this.render();
        });
        this._setupTabObserver();
        this.loadInitial();
    },

    _setupTabObserver() {
        // Lazy-init map when cyber tab becomes active (same pattern as map.js)
        const observer = new MutationObserver(() => {
            const tab = document.getElementById('tab-cyber');
            if (tab && tab.classList.contains('active')) {
                observer.disconnect();
                this._initMap();
            }
        });
        observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'] });

        // Check if already active
        const tab = document.getElementById('tab-cyber');
        if (tab && tab.classList.contains('active')) {
            observer.disconnect();
            this._initMap();
        }
    },

    _initMap() {
        if (this._initialized) return;
        const el = document.getElementById('cyber-map');
        if (!el) return;

        this._initialized = true;
        this.map = L.map('cyber-map', {
            zoomControl: true,
            preferCanvas: false,  // SVG renderer so CSS animations work on circle markers
            maxBounds: [[-90, -180], [90, 180]],
            maxBoundsViscosity: 1.0,
        }).setView([25, 60], 3);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap &copy; CARTO',
            maxZoom: 18,
            subdomains: 'abcd',
        }).addTo(this.map);

        this.outageLayer = L.layerGroup().addTo(this.map);
        this.watchedLayer = L.layerGroup().addTo(this.map);
        this.render();
    },

    async loadInitial() {
        try {
            const resp = await fetch('/api/cyber');
            if (resp.ok) {
                const d = await resp.json();
                this.outages = d.outages || [];
                this.cyberNews = d.cyber_news || [];
                this.cves = d.cves || [];
                this.stats = d.stats || this.stats;
                this.correlations = d.correlations || [];
                this.watchedSignals = d.watched_signals || {};
                this.lastUpdated = d.last_updated || null;
                this.render();
            }
        } catch (e) { console.error('[Cyber] Initial load:', e); }
    },

    render() {
        this.renderStats();
        this.renderOutageMap();
        this.renderWatchedSignals();
        this.renderWatchedPanel();
        this.renderOutageList();
        this.renderNews();
        this.renderKEV();
        this.renderCorrelations();
        this.renderLastUpdated();
    },

    renderStats() {
        const el = document.getElementById('cyber-stats');
        if (!el) return;
        const s = this.stats;
        const hasOutages = s.active_outages > 0;
        el.innerHTML = `
            <div class="cyber-stat ${hasOutages ? 'high' : ''}"><div class="value">${s.active_outages}</div><div class="label">Active Outages</div></div>
            <div class="cyber-stat"><div class="value">${s.countries_affected}</div><div class="label">Countries</div></div>
            <div class="cyber-stat"><div class="value">${s.new_cves}</div><div class="label">New CVEs Today</div></div>
            <div class="cyber-stat"><div class="value">${s.feeds_ok || 0}/3</div><div class="label">Feeds Active</div></div>
            <div class="cyber-stat"><div class="value">${this.correlations.length}</div><div class="label">Correlations</div></div>
        `;
    },

    renderLastUpdated() {
        const el = document.getElementById('cyber-last-updated');
        if (!el || !this.lastUpdated) return;
        const ago = timeAgo(this.lastUpdated);
        el.textContent = `Updated ${ago}`;
    },

    // --- Outage Map ---

    _datasourceColor(ds) {
        if (ds === 'bgp') return '#ff4444';
        if (ds === 'ping-slash24') return '#ff9800';
        if (ds === 'merit-nt' || ds === 'ucsd-nt') return '#ffeb3b';
        return '#ff6666';
    },

    _datasourceLabel(ds) {
        if (ds === 'bgp') return 'BGP routing';
        if (ds === 'ping-slash24') return 'Active probing';
        if (ds === 'merit-nt' || ds === 'ucsd-nt') return 'Network telescope';
        if (ds === 'gtr' || ds === 'gtr-norm') return 'Google traffic';
        return ds;
    },

    renderOutageMap() {
        if (!this.outageLayer) return;
        this.outageLayer.clearLayers();

        this.outages.forEach(o => {
            if (o.lat == null || o.lon == null) return;
            const color = this._datasourceColor(o.datasource);
            const radius = 8 + (o.severity || 1) * 2.5;

            // Pulsing outer ring
            const pulse = L.circleMarker([o.lat, o.lon], {
                radius: radius + 4,
                fillColor: color,
                color: color,
                weight: 2,
                fillOpacity: 0.15,
                opacity: 0.4,
                className: 'outage-pulse',
            });

            // Inner circle
            const marker = L.circleMarker([o.lat, o.lon], {
                radius: radius,
                fillColor: color,
                color: '#000',
                weight: 1,
                fillOpacity: 0.7,
            });

            const durStr = o.duration > 0
                ? (o.duration < 3600 ? Math.round(o.duration / 60) + 'm' : Math.round(o.duration / 3600) + 'h')
                : 'ongoing';
            const startStr = o.start ? new Date(o.start * 1000).toLocaleTimeString() : '—';

            marker.bindTooltip(
                `<b>${this.esc(o.country_name)}</b><br>` +
                `Severity: ${o.severity}/10<br>` +
                `Type: ${this.esc(this._datasourceLabel(o.datasource))}<br>` +
                `Duration: ${durStr}<br>` +
                `Start: ${startStr}<br>` +
                `Region: ${this.esc(o.region)}` +
                (o.alert_drop_pct ? `<br>Drop: ${o.alert_drop_pct}%` : ''),
                { className: 'dark-tooltip' }
            );

            this.outageLayer.addLayer(pulse);
            this.outageLayer.addLayer(marker);
        });
    },

    // --- Watched Country Signals (TW, UA) ---

    _statusColor(status) {
        if (status === 'critical') return '#ff4444';
        if (status === 'degraded') return '#ff9800';
        if (status === 'warning') return '#ffeb3b';
        if (status === 'normal') return '#4caf50';
        return '#888';
    },

    _miniSparkline(values, color, w, h) {
        if (!values || values.length < 2) return '';
        const valid = values.map((v, i) => v != null ? { x: i, y: v } : null).filter(Boolean);
        if (valid.length < 2) return '';
        const minY = Math.min(...valid.map(p => p.y));
        const maxY = Math.max(...valid.map(p => p.y));
        const rangeY = maxY - minY || 1;
        const pts = valid.map(p => {
            const x = (p.x / (values.length - 1)) * w;
            const y = h - ((p.y - minY) / rangeY) * (h - 4) - 2;
            return `${x},${y}`;
        }).join(' ');
        return `<svg width="${w}" height="${h}" style="vertical-align:middle;"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
    },

    renderWatchedSignals() {
        if (!this.watchedLayer) return;
        this.watchedLayer.clearLayers();

        const signals = this.watchedSignals;
        if (!signals || !Object.keys(signals).length) return;

        Object.entries(signals).forEach(([code, info]) => {
            if (!info.lat || !info.lon || !info.datasources || !Object.keys(info.datasources).length) return;

            // Determine worst status across datasources
            const statuses = Object.values(info.datasources).map(d => d.status);
            const worstOrder = ['critical', 'degraded', 'warning', 'normal', 'unknown'];
            const worst = worstOrder.find(s => statuses.includes(s)) || 'unknown';
            const color = this._statusColor(worst);

            // Diamond-shaped marker (rotated square) — distinct from outage circles
            const marker = L.marker([info.lat, info.lon], {
                icon: L.divIcon({
                    className: '',
                    html: `<div style="width:18px;height:18px;background:${color};border:2px solid #fff;transform:rotate(45deg);opacity:0.9;box-shadow:0 0 8px ${color};"></div>`,
                    iconSize: [22, 22],
                    iconAnchor: [11, 11],
                }),
            });

            // Build tooltip with per-datasource details
            let tip = `<b>${this.esc(info.name)}</b> — Signal Monitor<br>`;
            Object.entries(info.datasources).forEach(([ds, d]) => {
                const dsColor = this._statusColor(d.status);
                const arrow = d.pct_change > 0 ? '▲' : d.pct_change < 0 ? '▼' : '—';
                const spark = this._miniSparkline(d.values, dsColor, 60, 18);
                tip += `<div style="margin-top:4px;">` +
                    `<span style="color:${dsColor};font-weight:600;">${this.esc(this._datasourceLabel(ds))}</span> ` +
                    `${spark} ` +
                    `<span style="color:${dsColor};">${arrow} ${d.pct_change > 0 ? '+' : ''}${d.pct_change}%</span>` +
                    `<span style="color:var(--text-secondary);font-size:11px;"> (${d.current})</span>` +
                    `</div>`;
            });
            marker.bindTooltip(tip, { className: 'dark-tooltip', maxWidth: 280 });

            this.watchedLayer.addLayer(marker);
        });
    },

    // --- Watched Signals Panel (below map) ---

    renderWatchedPanel() {
        const el = document.getElementById('cyber-watched-panel');
        if (!el) return;
        const signals = this.watchedSignals;
        if (!signals || !Object.keys(signals).length) {
            el.innerHTML = '';
            return;
        }
        el.innerHTML = '<div style="font-size:11px; color:var(--text-secondary); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">Signal Monitor — Watched Countries</div>' +
            Object.entries(signals).map(([code, info]) => {
                if (!info.datasources || !Object.keys(info.datasources).length) return '';
                const statuses = Object.values(info.datasources).map(d => d.status);
                const worstOrder = ['critical', 'degraded', 'warning', 'normal', 'unknown'];
                const worst = worstOrder.find(s => statuses.includes(s)) || 'unknown';
                const color = this._statusColor(worst);
                const dsHtml = Object.entries(info.datasources).map(([ds, d]) => {
                    const c = this._statusColor(d.status);
                    const arrow = d.pct_change > 0 ? '▲' : d.pct_change < 0 ? '▼' : '—';
                    const spark = this._miniSparkline(d.values, c, 80, 20);
                    return `<div style="display:flex;align-items:center;gap:8px;margin-top:4px;">` +
                        `<span style="font-size:12px;color:${c};font-weight:600;min-width:110px;">${this.esc(this._datasourceLabel(ds))}</span>` +
                        `${spark}` +
                        `<span style="font-size:12px;color:${c};">${arrow} ${d.pct_change > 0 ? '+' : ''}${d.pct_change}%</span>` +
                        `<span style="font-size:11px;color:var(--text-secondary);">${d.current}</span>` +
                        `</div>`;
                }).join('');
                return `<div class="card" style="padding:10px 14px;margin-bottom:6px;border-left:3px solid ${color};">` +
                    `<div style="display:flex;justify-content:space-between;align-items:center;">` +
                    `<b>${this.esc(info.name)}</b>` +
                    `<span style="font-size:11px;padding:2px 8px;border-radius:3px;background:${color}22;color:${color};font-weight:600;text-transform:uppercase;">${worst}</span>` +
                    `</div>${dsHtml}</div>`;
            }).join('');
    },

    // --- Outage List ---

    renderOutageList() {
        const el = document.getElementById('cyber-outage-list');
        if (!el) return;
        if (!this.outages.length) {
            el.innerHTML = '<div style="color:var(--text-secondary); font-size:13px; padding:8px;">No active outages in monitored regions</div>';
            return;
        }
        el.innerHTML = this.outages.map(o => {
            const color = this._datasourceColor(o.datasource);
            const durStr = o.duration > 0
                ? (o.duration < 3600 ? Math.round(o.duration / 60) + 'm' : Math.round(o.duration / 3600) + 'h')
                : 'ongoing';
            return `
                <div class="card" style="padding:8px 12px; margin-bottom:6px; border-left:3px solid ${color};">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <b>${this.esc(o.country_name)}</b>
                            <span style="color:var(--text-secondary); font-size:12px; margin-left:8px;">${this.esc(o.region)}</span>
                        </div>
                        <div style="display:flex; gap:8px; align-items:center; font-size:12px;">
                            <span style="color:${color}; font-weight:600;">${o.severity}/10</span>
                            <span style="color:var(--text-secondary);">${this.esc(this._datasourceLabel(o.datasource))}</span>
                            <span style="color:var(--text-secondary);">${durStr}</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    },

    // --- Cyber News Feed ---

    renderNews() {
        const el = document.getElementById('cyber-news-feed');
        if (!el) return;
        if (!this.cyberNews.length) {
            el.innerHTML = '<div style="color:var(--text-secondary); font-size:13px; padding:8px;">No recent cyber news</div>';
            return;
        }
        el.innerHTML = this.cyberNews.map(a => `
            <div class="card" style="padding:8px 12px; margin-bottom:6px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <a href="${this.safeUrl(a.url)}" target="_blank" rel="noopener" style="color:var(--text-primary); text-decoration:none; font-size:13px; font-weight:500; flex:1;">
                        ${this.esc(a.title)}
                    </a>
                    <span class="source-badge" style="margin-left:8px; white-space:nowrap;">${this.esc(a.source)}</span>
                </div>
                <div style="font-size:12px; color:var(--text-secondary); margin-top:4px;">
                    ${a.summary ? this.esc(a.summary.substring(0, 150)) + (a.summary.length > 150 ? '...' : '') : ''}
                </div>
                <div style="font-size:11px; color:var(--text-secondary); margin-top:4px;">
                    ${timeAgo(a.published)}
                </div>
            </div>
        `).join('');
    },

    // --- CISA KEV Panel ---

    renderKEV() {
        const el = document.getElementById('cyber-kev-panel');
        if (!el) return;
        if (!this.cves.length) {
            el.innerHTML = '<div style="color:var(--text-secondary); font-size:13px; padding:8px;">No recent CVEs</div>';
            return;
        }
        el.innerHTML = this.cves.map(c => `
            <div class="card" style="padding:6px 10px; margin-bottom:4px; font-size:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:600; color:var(--accent);">${this.esc(c.cve_id)}</span>
                    <span class="severity-badge ${c.severity}" style="font-size:11px;">${c.severity}</span>
                </div>
                <div style="color:var(--text-primary); margin-top:2px;">${this.esc(c.title)}</div>
                <div style="color:var(--text-secondary); margin-top:2px;">${this.esc(c.date_added)}</div>
            </div>
        `).join('');
    },

    // --- Correlations ---

    renderCorrelations() {
        const el = document.getElementById('cyber-correlations');
        if (!el) return;
        if (!this.correlations.length) {
            el.innerHTML = '';
            return;
        }
        el.innerHTML = '<h3 style="font-size:13px; color:var(--orange); margin:0 0 8px 0;">Outage + News Correlations</h3>' +
            this.correlations.map(c => `
                <div class="card" style="padding:10px 14px; margin-bottom:8px; border-left:3px solid var(--orange);">
                    <div style="font-weight:600;">${this.esc(c.country)} — Severity ${c.outage_severity}/10 (${this.esc(c.datasource)})</div>
                    <div style="font-size:12px; color:var(--text-secondary); margin-top:4px;">
                        ${c.matched_articles} matching article${c.matched_articles > 1 ? 's' : ''}:
                        ${(c.article_titles || []).map(t => '<div style="margin-left:12px;">• ' + this.esc(t) + '</div>').join('')}
                    </div>
                    ${c.llm_assessment ? `<div style="font-size:12px; margin-top:6px; padding:6px 8px; background:rgba(255,167,38,0.1); border-radius:4px;"><b>Analysis:</b> ${this.esc(c.llm_assessment)}</div>` : ''}
                </div>
            `).join('');
    },

    esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; },
    safeUrl(u) { if (!u) return '#'; try { const p = new URL(u); return (p.protocol === 'https:' || p.protocol === 'http:') ? p.href : '#'; } catch { return '#'; } }
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
                if (!cfg.sources) cfg.sources = {};
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
