// Markets tab: TradingView-style charts
// EUR/USD + Bitcoin = large primary charts
// Other forex, crypto, stocks = smaller secondary

const Markets = {
    data: { forex: {}, stocks: {}, crypto: {}, fear_greed: { value: 50, classification: 'Neutral' }, intraday: {} },
    dpr: window.devicePixelRatio || 1,
    // Expected instruments: [name, category, size]
    expected: [
        ['EUR/USD', 'forex', 'primary'], ['Bitcoin', 'crypto', 'primary'],
        ['USD/JPY', 'forex', 'secondary'], ['Ethereum', 'crypto', 'secondary'],
        ['S&P 500', 'stocks', 'secondary'], ['NASDAQ', 'stocks', 'secondary'],
    ],

    init() {
        WS.on('markets', (d) => { this.data = d; this.render(); });
        this.loadInitial();
    },

    async loadInitial() {
        try {
            const resp = await fetch('/api/markets');
            if (resp.ok) { this.data = await resp.json(); this.render(); }
        } catch (e) { console.error('[Markets] Initial load:', e); }
    },

    getLoaded() {
        const all = { ...(this.data.forex || {}), ...(this.data.stocks || {}), ...(this.data.crypto || {}) };
        return all;
    },

    render() {
        this.renderTicker();
        this.renderPrimary();
        this.renderSecondary();
    },

    renderTicker() {
        const el = document.getElementById('market-ticker');
        if (!el) return;
        const items = [
            ...Object.values(this.data.forex || {}),
            ...Object.values(this.data.crypto || {}),
            ...Object.values(this.data.stocks || {}),
        ];
        el.innerHTML = items.map(i => {
            const dir = (i.change_pct || 0) >= 0 ? 'up' : 'down';
            const sign = dir === 'up' ? '+' : '';
            const closed = i.is_open === false ? ' <span style="color:#555;font-size:10px;">CLOSED</span>' : '';
            return `<div class="ticker-item">
                <span class="symbol">${i.name || i.symbol}</span>
                <span class="price">${this.fmtPrice(i)}</span>
                <span class="change ${dir}">${sign}${(i.change_pct || 0).toFixed(2)}%</span>${closed}
            </div>`;
        }).join('');
    },

    renderPrimary() {
        const el = document.getElementById('primary-charts');
        if (!el) return;
        const loaded = this.getLoaded();
        const total = this.expected.length;
        const loadedCount = Object.keys(loaded).length;

        const panels = this.expected.filter(e => e[2] === 'primary').map(([name]) => {
            if (loaded[name]) return this.buildChartPanel(name, loaded[name], 'primary');
            return this.buildSkeleton(name, 'primary', loadedCount, total);
        });
        el.innerHTML = panels.join('');

        requestAnimationFrame(() => {
            this.expected.filter(e => e[2] === 'primary').forEach(([name]) => {
                if (!loaded[name]) return;
                const canvasId = 'chart-' + name.replace(/[^a-zA-Z0-9]/g, '');
                const series = (this.data.intraday || {})[name] || [];
                const prevClose = loaded[name].prev_close || (series.length > 1 ? series[0].p : loaded[name].price);
                this.drawIntradayChart(canvasId, series, prevClose, loaded[name]);
            });
        });
    },

    renderSecondary() {
        const el = document.getElementById('secondary-charts');
        if (!el) return;
        const loaded = this.getLoaded();
        const total = this.expected.length;
        const loadedCount = Object.keys(loaded).length;

        const panels = this.expected.filter(e => e[2] === 'secondary').map(([name]) => {
            if (loaded[name]) return this.buildChartPanel(name, loaded[name], 'secondary');
            return this.buildSkeleton(name, 'secondary', loadedCount, total);
        });
        el.innerHTML = panels.join('');

        requestAnimationFrame(() => {
            this.expected.filter(e => e[2] === 'secondary').forEach(([name]) => {
                if (!loaded[name]) return;
                const canvasId = 'chart-' + name.replace(/[^a-zA-Z0-9]/g, '');
                const series = (this.data.intraday || {})[name] || [];
                const prevClose = loaded[name].prev_close || (series.length > 1 ? series[0].p : loaded[name].price);
                this.drawIntradayChart(canvasId, series, prevClose, loaded[name]);
            });
        });
    },

    buildSkeleton(name, size, loadedCount, total) {
        const h = size === 'primary' ? 300 : 150;
        return `<div class="chart-panel ${size}-panel" style="opacity:0.5;">
            <div class="chart-header">
                <div class="chart-title">
                    <span class="chart-symbol">${name}</span>
                </div>
                <div class="chart-price-info">
                    <span class="chart-price" style="color:var(--text-secondary);">—</span>
                </div>
            </div>
            <div style="height:${h}px;display:flex;align-items:center;justify-content:center;background:#131722;">
                <div style="text-align:center;">
                    <span class="loader-spin"></span>
                    <div style="font-size:11px;color:var(--text-secondary);margin-top:8px;">loading</div>
                </div>
            </div>
        </div>`;
    },

    buildChartPanel(key, item, size) {
        const dir = (item.change_pct || 0) >= 0 ? 'up' : 'down';
        const sign = dir === 'up' ? '+' : '';
        const canvasId = 'chart-' + key.replace(/[^a-zA-Z0-9]/g, '');
        const canvasClass = size === 'primary' ? 'primary-canvas' : 'secondary-canvas';
        const changeStr = item.change !== undefined
            ? `${sign}${this.fmtChange(item)} (${sign}${item.change_pct.toFixed(2)}%)`
            : `${sign}${item.change_pct.toFixed(2)}%`;

        const closedBadge = item.is_open === false
            ? '<span style="background:#333;color:#888;font-size:10px;padding:2px 6px;border-radius:3px;margin-left:8px;vertical-align:middle;">CLOSED</span>'
            : '';

        const metaHtml = item.high !== undefined
            ? `<div class="chart-meta"><span>O: ${this.fmtPrice(item, 'open')}</span><span>H: ${this.fmtPrice(item, 'high')}</span><span>L: ${this.fmtPrice(item, 'low')}</span>${item.volume ? '<span>Vol: ' + this.fmtVol(item.volume) + '</span>' : ''}</div>`
            : '';

        return `<div class="chart-panel ${size}-panel">
            <div class="chart-header">
                <div class="chart-title">
                    <span class="chart-symbol">${item.symbol || key}</span>
                    <span class="chart-name">${item.name || key}</span>${closedBadge}
                </div>
                <div class="chart-price-info">
                    <span class="chart-price ${size === 'primary' ? 'large' : ''}">${this.fmtPrice(item)}</span>
                    <span class="chart-change ${dir}">${changeStr}</span>
                </div>
                ${metaHtml}
            </div>
            <canvas id="${canvasId}" class="${canvasClass}"></canvas>
        </div>`;
    },

    drawIntradayChart(canvasId, series, prevClose, item) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        this.sizeCanvas(canvas);
        const ctx = canvas.getContext('2d');
        const dpr = this.dpr;
        const w = canvas.width / dpr;
        const h = canvas.height / dpr;

        // Background
        ctx.fillStyle = '#131722';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        if (!series || series.length < 2) {
            ctx.fillStyle = '#555';
            ctx.font = '13px Segoe UI';
            ctx.textAlign = 'center';
            const msg = item.is_open === false ? 'Market Closed' : 'Waiting for data...';
            ctx.fillText(msg, w / 2, h / 2);
            if (item.price) {
                ctx.fillStyle = '#e0e0e0';
                ctx.font = '18px Segoe UI';
                ctx.fillText(this.fmtPrice(item), w / 2, h / 2 + 25);
            }
            return;
        }

        const prices = series.map(s => s.p);
        const times = series.map(s => s.t);
        const allPrices = [...prices, prevClose];
        const minP = Math.min(...allPrices);
        const maxP = Math.max(...allPrices);
        const range = maxP - minP || 1;
        const padding = { top: 8, bottom: 24, left: 8, right: 64 };
        const chartW = w - padding.left - padding.right;
        const chartH = h - padding.top - padding.bottom;

        const lastPrice = prices[prices.length - 1];
        const isUp = lastPrice >= prevClose;
        const lineColor = isUp ? '#26a69a' : '#ef5350';
        const fillColor = isUp ? 'rgba(38,166,154,0.08)' : 'rgba(239,83,80,0.08)';

        const toX = (i) => padding.left + (i / (prices.length - 1)) * chartW;
        const toY = (p) => padding.top + (1 - (p - minP) / range) * chartH;

        // Grid
        ctx.strokeStyle = '#1e222d';
        ctx.lineWidth = 0.5;
        for (let i = 0; i < 4; i++) {
            const y = padding.top + (i / 3) * chartH;
            ctx.beginPath(); ctx.moveTo(padding.left, y); ctx.lineTo(w - padding.right, y); ctx.stroke();
        }

        // Prev close dashed line
        const prevY = toY(prevClose);
        ctx.strokeStyle = '#555';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(padding.left, prevY); ctx.lineTo(w - padding.right, prevY); ctx.stroke();
        ctx.setLineDash([]);

        // Prev close label
        ctx.fillStyle = '#363a45';
        ctx.fillRect(w - padding.right + 1, prevY - 8, padding.right - 2, 16);
        ctx.fillStyle = '#888';
        ctx.font = '10px Segoe UI';
        ctx.textAlign = 'left';
        ctx.fillText(this.fmtAxis(prevClose, item), w - padding.right + 4, prevY + 3);

        // Filled area
        ctx.beginPath();
        ctx.moveTo(toX(0), toY(prices[0]));
        for (let i = 1; i < prices.length; i++) ctx.lineTo(toX(i), toY(prices[i]));
        ctx.lineTo(toX(prices.length - 1), padding.top + chartH);
        ctx.lineTo(toX(0), padding.top + chartH);
        ctx.closePath();
        ctx.fillStyle = fillColor;
        ctx.fill();

        // Price line
        ctx.beginPath();
        ctx.moveTo(toX(0), toY(prices[0]));
        for (let i = 1; i < prices.length; i++) ctx.lineTo(toX(i), toY(prices[i]));
        ctx.strokeStyle = lineColor;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Current price dot + horizontal line to label
        const lastX = toX(prices.length - 1);
        const lastY = toY(lastPrice);
        ctx.strokeStyle = lineColor;
        ctx.lineWidth = 0.5;
        ctx.setLineDash([2, 2]);
        ctx.beginPath(); ctx.moveTo(lastX, lastY); ctx.lineTo(w - padding.right, lastY); ctx.stroke();
        ctx.setLineDash([]);

        ctx.beginPath();
        ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
        ctx.fillStyle = lineColor;
        ctx.fill();

        // Current price label
        ctx.fillStyle = lineColor;
        ctx.fillRect(w - padding.right + 1, lastY - 8, padding.right - 2, 16);
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 10px Segoe UI';
        ctx.textAlign = 'left';
        ctx.fillText(this.fmtAxis(lastPrice, item), w - padding.right + 4, lastY + 3);

        // Y-axis labels
        ctx.fillStyle = '#555';
        ctx.font = '9px Segoe UI';
        ctx.textAlign = 'right';
        for (let i = 0; i < 4; i++) {
            const p = maxP - (i / 3) * range;
            const y = padding.top + (i / 3) * chartH;
            ctx.fillText(this.fmtAxis(p, item), w - padding.right - 3, y + 3);
        }

        // Time axis — always show HH:MM format (intraday focus)
        ctx.fillStyle = '#555';
        ctx.font = '9px Segoe UI';
        ctx.textAlign = 'center';
        const step = Math.max(1, Math.floor(times.length / 6));
        for (let i = 0; i < times.length; i += step) {
            const d = new Date(times[i]);
            const label = d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
            ctx.fillText(label, toX(i), h - 6);
        }

        // If market is closed, overlay a subtle "CLOSED" watermark
        if (item.is_open === false) {
            ctx.save();
            ctx.fillStyle = 'rgba(255,255,255,0.06)';
            ctx.font = 'bold 28px Segoe UI';
            ctx.textAlign = 'center';
            ctx.fillText('CLOSED', w / 2, h / 2 + 10);
            ctx.restore();
        }
    },

    sizeCanvas(canvas) {
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * this.dpr;
        canvas.height = rect.height * this.dpr;
        canvas.getContext('2d').scale(this.dpr, this.dpr);
    },

    // Formatting helpers
    fmtPrice(item, field) {
        const p = field ? item[field] : item.price;
        if (p == null) return '-';
        const sym = item.symbol || '';
        if (sym.startsWith('C:') || (item.price && item.price < 10 && item.price > 0.5)) {
            return p.toFixed(4);
        }
        return p >= 1000 ? p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : p.toFixed(2);
    },
    fmtChange(item) {
        if (item.change == null) return '-';
        const sym = item.symbol || '';
        if (sym.startsWith('C:')) return item.change.toFixed(4);
        return item.change >= 1000 ? item.change.toLocaleString('en-US', { minimumFractionDigits: 2 }) : item.change.toFixed(2);
    },
    fmtAxis(n, item) {
        if (n == null) return '-';
        const sym = (item && item.symbol) || '';
        if (sym.startsWith('C:')) return n.toFixed(4);
        if (n >= 10000) return n.toFixed(0);
        if (n >= 100) return n.toFixed(1);
        return n.toFixed(2);
    },
    fmtVol(n) {
        if (!n) return '-';
        if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
        if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
        return n.toString();
    }
};

document.addEventListener('DOMContentLoaded', () => Markets.init());
