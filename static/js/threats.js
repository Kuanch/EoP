// Threats tab: feed display + config management

const ThreatsView = {
    config: null,

    async init() {
        await this.loadConfig();
        await this.loadFeed();
        this._bindEvents();
    },

    _bindEvents() {
        document.getElementById('t-refresh')?.addEventListener('click', () => this.loadFeed());
        document.getElementById('t-save-config')?.addEventListener('click', () => this.saveConfig());
        document.getElementById('t-add-keyword')?.addEventListener('click', () => this._addKeyword());

        // Slider live values
        const llmSlider = document.getElementById('t-llm-threshold');
        const notifySlider = document.getElementById('t-notify-threshold');
        if (llmSlider) llmSlider.addEventListener('input', () => {
            document.getElementById('t-llm-threshold-val').textContent = llmSlider.value;
        });
        if (notifySlider) notifySlider.addEventListener('input', () => {
            document.getElementById('t-notify-threshold-val').textContent = notifySlider.value;
        });
    },

    async loadFeed() {
        try {
            const [feedResp, statsResp] = await Promise.all([
                fetch('/api/threats/feed'),
                fetch('/api/threats/stats'),
            ]);
            if (feedResp.ok) {
                const feed = await feedResp.json();
                this._renderFeed(feed);
            }
            if (statsResp.ok) {
                const stats = await statsResp.json();
                this._renderStats(stats);
            }
        } catch (e) {
            console.error('[threats] Load feed error:', e);
        }
    },

    async loadConfig() {
        try {
            const resp = await fetch('/api/threats/config');
            if (resp.ok) {
                this.config = await resp.json();
                this._populateConfig();
            }
        } catch (e) {
            console.error('[threats] Load config error:', e);
        }
    },

    async saveConfig() {
        const config = this._readConfig();
        try {
            const resp = await fetch('/api/threats/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });
            const status = document.getElementById('t-save-status');
            if (resp.ok) {
                this.config = config;
                if (status) { status.textContent = 'Saved!'; setTimeout(() => status.textContent = '', 2000); }
            } else {
                if (status) { status.textContent = 'Save failed'; status.style.color = 'var(--red)'; }
            }
        } catch (e) {
            console.error('[threats] Save config error:', e);
        }
    },

    _populateConfig() {
        if (!this.config) return;
        const c = this.config;

        const llmSlider = document.getElementById('t-llm-threshold');
        const notifySlider = document.getElementById('t-notify-threshold');
        if (llmSlider) { llmSlider.value = c.llm_threshold || 5; document.getElementById('t-llm-threshold-val').textContent = llmSlider.value; }
        if (notifySlider) { notifySlider.value = c.notify_threshold || 7; document.getElementById('t-notify-threshold-val').textContent = notifySlider.value; }

        const cooldown = document.getElementById('t-cooldown');
        if (cooldown) cooldown.value = c.cooldown_minutes || 15;

        const llmEnabled = document.getElementById('t-llm-enabled');
        if (llmEnabled) llmEnabled.checked = c.llm_enabled || false;

        const prompt = document.getElementById('t-llm-prompt');
        if (prompt) prompt.value = c.llm_prompt || '';

        // Sources
        document.getElementById('t-src-news').checked = c.sources?.news ?? true;
        document.getElementById('t-src-cyber').checked = c.sources?.cyber ?? true;
        document.getElementById('t-src-pizzint').checked = c.sources?.pizzint ?? true;

        // Keywords
        this._renderKeywords(c.keyword_rules || {});
    },

    _readConfig() {
        const rules = {};
        document.querySelectorAll('.kw-row').forEach(row => {
            const kw = row.dataset.keyword;
            const wt = parseInt(row.querySelector('.kw-weight').value) || 1;
            if (kw) rules[kw] = wt;
        });

        return {
            keyword_rules: rules,
            llm_threshold: parseInt(document.getElementById('t-llm-threshold')?.value) || 5,
            notify_threshold: parseInt(document.getElementById('t-notify-threshold')?.value) || 7,
            llm_enabled: document.getElementById('t-llm-enabled')?.checked || false,
            llm_prompt: document.getElementById('t-llm-prompt')?.value || '',
            cooldown_minutes: parseInt(document.getElementById('t-cooldown')?.value) || 15,
            sources: {
                news: document.getElementById('t-src-news')?.checked ?? true,
                cyber: document.getElementById('t-src-cyber')?.checked ?? true,
                pizzint: document.getElementById('t-src-pizzint')?.checked ?? true,
            },
        };
    },

    _renderKeywords(rules) {
        const container = document.getElementById('t-keyword-rules');
        if (!container) return;
        container.innerHTML = '';
        const sorted = Object.entries(rules).sort((a, b) => b[1] - a[1]);
        for (const [kw, wt] of sorted) {
            const row = document.createElement('div');
            row.className = 'kw-row';
            row.dataset.keyword = kw;
            row.innerHTML = `
                <span class="kw-name">${this._esc(kw)}</span>
                <input type="number" class="kw-weight config-input" value="${wt}" min="1" max="10" style="width:45px;">
                <button class="kw-remove" title="Remove">&times;</button>
            `;
            row.querySelector('.kw-remove').addEventListener('click', () => row.remove());
            container.appendChild(row);
        }
    },

    _addKeyword() {
        const kwInput = document.getElementById('t-new-keyword');
        const wtInput = document.getElementById('t-new-weight');
        const kw = kwInput?.value?.trim().toLowerCase();
        const wt = parseInt(wtInput?.value) || 5;
        if (!kw) return;

        const container = document.getElementById('t-keyword-rules');
        const row = document.createElement('div');
        row.className = 'kw-row';
        row.dataset.keyword = kw;
        row.innerHTML = `
            <span class="kw-name">${this._esc(kw)}</span>
            <input type="number" class="kw-weight config-input" value="${wt}" min="1" max="10" style="width:45px;">
            <button class="kw-remove" title="Remove">&times;</button>
        `;
        row.querySelector('.kw-remove').addEventListener('click', () => row.remove());
        container.appendChild(row);
        kwInput.value = '';
        wtInput.value = '';
    },

    _renderFeed(feed) {
        const container = document.getElementById('threat-feed-list');
        if (!container) return;
        if (!feed.length) {
            container.innerHTML = '<div style="color:var(--text-secondary); font-size:13px; padding:20px; text-align:center;">No high-risk threats detected. Showing score 5+ only.</div>';
            return;
        }
        container.innerHTML = feed.map(t => {
            const time = new Date(t.timestamp * 1000).toLocaleTimeString();
            const scoreColor = t.final_score >= 7 ? 'var(--red)' : t.final_score >= 5 ? 'var(--orange)' : t.final_score >= 3 ? 'var(--yellow)' : 'var(--blue)';
            const borderColor = t.final_score >= 7 ? 'var(--red)' : t.final_score >= 5 ? 'var(--orange)' : t.final_score >= 3 ? 'var(--yellow)' : 'var(--border)';
            const notifIcon = t.notified ? '<span style="color:var(--green);" title="Notification sent">&#9889;</span>' : '';
            const llmBadge = t.llm_score != null ? `<span class="severity-badge" style="background:rgba(68,138,255,0.2); color:var(--blue);">LLM: ${t.llm_score}/10</span>` : '';
            const typeBadge = t.llm_threat_type ? `<span class="severity-badge" style="background:rgba(255,255,255,0.05); color:var(--text-secondary);">${this._esc(t.llm_threat_type)}</span>` : '';
            const escalationBadge = t.escalation_level && t.escalation_level !== 'background'
                ? `<span class="severity-badge" style="background:${t.escalation_level === 'strategic' ? 'rgba(255,82,82,0.18)' : 'rgba(255,167,38,0.18)'}; color:${t.escalation_level === 'strategic' ? 'var(--red)' : 'var(--orange)'};">${this._esc(t.escalation_level)}</span>`
                : '';
            const regionMeta = t.geo_region && t.geo_region !== 'Global' ? `<div style="font-size:11px; color:var(--text-secondary);">Region: ${this._esc(t.geo_region)}</div>` : '';
            const sectorMeta = t.target_sector && t.target_sector !== 'unknown' ? `<div style="font-size:11px; color:var(--text-secondary);">Sector: ${this._esc(t.target_sector)}</div>` : '';
            const confidenceMeta = t.attribution_confidence ? `<div style="font-size:11px; color:var(--text-secondary);">Confidence: ${this._esc(t.attribution_confidence)}</div>` : '';

            return `<div class="card" style="border-left:3px solid ${borderColor}; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; align-items:start; gap:8px;">
                    <div style="flex:1;">
                        <div style="display:flex; gap:6px; align-items:center; margin-bottom:4px;">
                            <span class="source-badge">${this._esc(t.source)}</span>
                            ${llmBadge}${typeBadge}${escalationBadge}${notifIcon}
                        </div>
                        <div style="font-size:14px; font-weight:600; margin-bottom:3px;">${this._esc(t.title)}</div>
                        ${t.llm_rationale ? `<div style="font-size:12px; color:var(--text-secondary); font-style:italic;">${this._esc(t.llm_rationale)}</div>` : ''}
                        ${regionMeta}${sectorMeta}${confidenceMeta}
                    </div>
                    <div style="text-align:right; white-space:nowrap;">
                        <div style="font-size:20px; font-weight:700; color:${scoreColor};">${t.final_score}</div>
                        <div style="font-size:10px; color:var(--text-secondary);">rule: ${t.rule_score}</div>
                        <div style="font-size:10px; color:var(--text-secondary);">${time}</div>
                    </div>
                </div>
            </div>`;
        }).join('');
    },

    _renderStats(s) {
        const el = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
        el('t-stat-today', s.threats_today || 0);
        el('t-stat-notified', s.notifications_sent || 0);
        el('t-stat-llm', s.llm_calls || 0);
    },

    _esc(s) {
        if (!s) return '';
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    },
};

// Initialize when threats tab becomes active
document.addEventListener('DOMContentLoaded', () => {
    let loaded = false;
    const observer = new MutationObserver(() => {
        const tab = document.getElementById('tab-threats');
        if (tab && tab.classList.contains('active') && !loaded) {
            loaded = true;
            ThreatsView.init();
        }
    });
    observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'] });

    // Also check on click
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.dataset.tab === 'threats' && !loaded) {
                loaded = true;
                setTimeout(() => ThreatsView.init(), 50);
            } else if (btn.dataset.tab === 'threats') {
                ThreatsView.loadFeed();
            }
        });
    });
});
