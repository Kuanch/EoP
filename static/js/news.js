// News tab rendering and filtering

const News = {
    articles: [],
    activeSource: 'All',

    init() {
        WS.on('news', (data) => this.onData(data));
        this.setupFilters();
        this.loadInitial();
    },

    async loadInitial() {
        try {
            const resp = await fetch('/api/news');
            if (resp.ok) {
                const data = await resp.json();
                this.articles = data;
                this.render();
            }
        } catch (e) { console.error('[News] Initial load:', e); }
    },

    onData(newArticles) {
        this.articles = newArticles.concat(this.articles).slice(0, 200);
        this.render();
    },

    setupFilters() {
        const container = document.getElementById('news-filters');
        if (!container) return;
        container.addEventListener('click', (e) => {
            if (e.target.tagName === 'BUTTON') {
                this.activeSource = e.target.dataset.source;
                container.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.source === this.activeSource));
                this.render();
            }
        });
    },

    render() {
        const feed = document.getElementById('news-feed');
        if (!feed) return;

        const filtered = this.activeSource === 'All'
            ? this.articles
            : this.articles.filter(a => a.source === this.activeSource);

        feed.innerHTML = filtered.map(a => {
            const threatClass = a.threat_score >= 15 ? 'high-threat' : a.threat_score >= 8 ? 'medium-threat' : '';
            return `<div class="card news-card ${threatClass}" onclick="window.open('${this.escapeHtml(a.url)}','_blank')">
                <span class="source-badge">${this.escapeHtml(a.source)}</span>
                ${a.geo_region ? `<span class="source-badge">${this.escapeHtml(a.geo_region)}</span>` : ''}
                <div class="title">${this.escapeHtml(a.title)}</div>
                <div class="summary">${this.escapeHtml(a.summary)}</div>
                <div class="meta">
                    <span>${timeAgo(a.published || a.collected_at)}</span>
                    <span>Threat: ${Math.min(Math.round(a.threat_score), 100)}</span>
                </div>
            </div>`;
        }).join('');
    },

    escapeHtml(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }
};

document.addEventListener('DOMContentLoaded', () => News.init());
