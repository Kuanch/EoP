// Markets tab: TradingView-style charts — 2x3 equal grid

const Markets = {
    data: { forex: {}, stocks: {}, crypto: {}, fear_greed: { value: 50, classification: 'Neutral' }, intraday: {} },
    dpr: window.devicePixelRatio || 1,
    // Instruments in display order: top row (EUR/USD, Bitcoin), middle row (SPY, QQQ), bottom row (Gold, USD/JPY)
    expected: [
        ['EUR/USD', 'forex'], ['Bitcoin', 'crypto'],
        ['S&P 500', 'stocks'], ['NASDAQ', 'stocks'],
        ['Gold', 'stocks'], ['USD/JPY', 'forex'],
    ],
    selectedRanges: {},
    _crosshairs: {},
    _rafId: {},

    init() {
        this.expected.forEach(([name]) => { this.selectedRanges[name] = '24h'; });
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
        return { ...(this.data.forex || {}), ...(this.data.stocks || {}), ...(this.data.crypto || {}) };
    },

    _sliceSeries(series, rangeKey) {
        if (!series || series.length < 2) return series;
        const hours = parseInt(rangeKey) || 24;
        const latest = series[series.length - 1].t;
        const cutoff = latest - hours * 3600000;
        const sliced = series.filter(s => s.t >= cutoff);
        return sliced.length >= 2 ? sliced : series;
    },

    _filterStockHours(series, itemName) {
        // Only filter for stocks (S&P 500, NASDAQ, Gold)
        const stockSymbols = ['S&P 500', 'NASDAQ', 'Gold'];
        if (!stockSymbols.includes(itemName) || !series || series.length < 2) {
            return series;
        }


        const filtered = [];
        let lastClose = null;
        const now = new Date();
        const isMarketCurrentlyOpen = this._isMarketOpen(now);

        for (let i = 0; i < series.length; i++) {
            const point = series[i];
            const date = new Date(point.t);
            const isPointDuringMarketHours = this._isMarketOpen(date);

            if (isPointDuringMarketHours) {
                // Connect to previous trading session if there's a gap
                if (lastClose !== null && filtered.length === 0) {
                    // Add connecting point from previous close to session start
                    filtered.push({
                        t: point.t - 300000, // 5 minutes before
                        p: lastClose
                    });
                }
                filtered.push(point);
                lastClose = point.p;
            } else {
                // Track closing price for connecting lines
                if (filtered.length > 0) {
                    lastClose = filtered[filtered.length - 1].p;
                }
            }
        }

        // If market is closed and we have historical data, show last trading day
        if (!isMarketCurrentlyOpen && filtered.length < 5 && series.length > 10) {
            // Show recent trading hours data
            const recent = series.slice(-100); // Last 100 points
            const recentFiltered = [];
            let lastTradingSession = null;

            for (let i = recent.length - 1; i >= 0; i--) {
                const point = recent[i];
                const date = new Date(point.t);
                if (this._isMarketOpen(date)) {
                    if (!lastTradingSession) {
                        lastTradingSession = this._getMarketDay(date);
                    }
                    if (this._getMarketDay(date) === lastTradingSession) {
                        recentFiltered.unshift(point);
                    }
                }
            }
            return recentFiltered.length >= 2 ? recentFiltered : series.slice(-50);
        }

        return filtered.length >= 2 ? filtered : series;
    },

    _isMarketOpen(date) {
        const utcHour = date.getUTCHours();
        const utcMinute = date.getUTCMinutes();
        const weekday = date.getUTCDay();

        return (
            weekday >= 1 && weekday <= 5 && // Monday-Friday
            (utcHour > 14 || (utcHour === 14 && utcMinute >= 30)) && // After 9:30 AM EST
            utcHour < 21 // Before 4:00 PM EST
        );
    },

    _getMarketDay(date) {
        // Return market day identifier (YYYY-MM-DD in EST)
        const est = new Date(date.getTime() - (5 * 3600000)); // EST approximation
        return est.toISOString().split('T')[0];
    },

    _canvasId(name) {
        return 'chart-' + name.replace(/[^a-zA-Z0-9]/g, '');
    },

    _nameFromCanvasId(canvasId) {
        return this.expected.find(([n]) => this._canvasId(n) === canvasId)?.[0];
    },

    render() {
        this.renderTicker();
        this.renderCharts();
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

    renderCharts() {
        const el = document.getElementById('market-charts');
        if (!el) return;
        const loaded = this.getLoaded();
        const total = this.expected.length;
        const loadedCount = Object.keys(loaded).length;

        const panels = this.expected.map(([name]) => {
            if (loaded[name]) return this.buildChartPanel(name, loaded[name]);
            return this.buildSkeleton(name, loadedCount, total);
        });
        el.innerHTML = panels.join('');

        requestAnimationFrame(() => {
            this.expected.forEach(([name]) => {
                if (!loaded[name]) return;
                const canvasId = this._canvasId(name);
                const series = (this.data.intraday || {})[name] || [];
                const sliced = this._sliceSeries(series, this.selectedRanges[name]);
                const filtered = this._filterStockHours(sliced, name);
                const prevClose = loaded[name].prev_close || (filtered.length > 1 ? filtered[0].p : loaded[name].price);
                this.drawIntradayChart(canvasId, filtered, prevClose, loaded[name]);
                this._attachCrosshair(canvasId, filtered, prevClose, loaded[name]);
            });
        });

        this._attachRangeListeners();
    },

    _attachRangeListeners() {
        const container = document.getElementById('market-charts');
        if (!container) return;
        container.onclick = (e) => {
            const btn = e.target.closest('.range-btn');
            if (!btn) return;
            const chartName = btn.dataset.chart;
            const range = btn.dataset.range;
            if (this.selectedRanges[chartName] === range) return;
            this.selectedRanges[chartName] = range;
            btn.closest('.range-selector').querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            this._redrawSingleChart(chartName);
        };
    },

    _redrawSingleChart(name) {
        const loaded = this.getLoaded();
        if (!loaded[name]) return;
        const canvasId = this._canvasId(name);
        const series = (this.data.intraday || {})[name] || [];
        const sliced = this._sliceSeries(series, this.selectedRanges[name]);
        const filtered = this._filterStockHours(sliced, name);
        const prevClose = loaded[name].prev_close || (filtered.length > 1 ? filtered[0].p : loaded[name].price);
        this.drawIntradayChart(canvasId, filtered, prevClose, loaded[name]);
        this._attachCrosshair(canvasId, filtered, prevClose, loaded[name]);
    },

    buildSkeleton(name, loadedCount, total) {
        return `<div class="chart-panel" style="opacity:0.5;">
            <div class="chart-header">
                <div class="chart-title">
                    <span class="chart-symbol">${name}</span>
                </div>
                <div class="chart-price-info">
                    <span class="chart-price" style="color:var(--text-secondary);">—</span>
                </div>
            </div>
            <div style="height:220px;display:flex;align-items:center;justify-content:center;background:#131722;">
                <div style="text-align:center;">
                    <span class="loader-spin"></span>
                    <div style="font-size:11px;color:var(--text-secondary);margin-top:8px;">loading</div>
                </div>
            </div>
        </div>`;
    },

    buildChartPanel(key, item) {
        const dir = (item.change_pct || 0) >= 0 ? 'up' : 'down';
        const sign = dir === 'up' ? '+' : '';
        const canvasId = this._canvasId(key);
        const changeStr = item.change !== undefined
            ? `${sign}${this.fmtChange(item)} (${sign}${item.change_pct.toFixed(2)}%)`
            : `${sign}${item.change_pct.toFixed(2)}%`;

        const closedBadge = item.is_open === false
            ? '<span style="background:#333;color:#888;font-size:10px;padding:2px 6px;border-radius:3px;margin-left:8px;vertical-align:middle;">CLOSED</span>'
            : '';

        const metaHtml = item.high !== undefined
            ? `<div class="chart-meta"><span>O: ${this.fmtPrice(item, 'open')}</span><span>H: ${this.fmtPrice(item, 'high')}</span><span>L: ${this.fmtPrice(item, 'low')}</span>${item.volume ? '<span>Vol: ' + this.fmtVol(item.volume) + '</span>' : ''}</div>`
            : '';

        const sel = this.selectedRanges[key] || '24h';
        const ranges = ['1h', '5h', '12h', '24h'];
        const rangeHtml = `<div class="range-selector">${ranges.map(r =>
            `<button class="range-btn${r === sel ? ' active' : ''}" data-chart="${key}" data-range="${r}">${r.toUpperCase()}</button>`
        ).join('')}</div>`;

        return `<div class="chart-panel">
            <div class="chart-header">
                <div class="chart-title">
                    <span class="chart-symbol">${item.symbol || key}</span>
                    <span class="chart-name">${item.name || key}</span>${closedBadge}
                </div>
                <div class="chart-price-info">
                    <span class="chart-price">${this.fmtPrice(item)}</span>
                    <span class="chart-change ${dir}">${changeStr}</span>
                </div>
                ${metaHtml}
                ${rangeHtml}
            </div>
            <canvas id="${canvasId}" class="chart-canvas"></canvas>
        </div>`;
    },

    // --- Crosshair ---
    _attachCrosshair(canvasId, series, prevClose, item) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        if (this._crosshairs[canvasId]) {
            const old = this._crosshairs[canvasId];
            canvas.removeEventListener('mousemove', old.onMove);
            canvas.removeEventListener('mouseleave', old.onLeave);
        }
        const state = { hovering: false, mx: 0, my: 0 };

        const onMove = (e) => {
            const rect = canvas.getBoundingClientRect();
            state.mx = e.clientX - rect.left;
            state.my = e.clientY - rect.top;
            state.hovering = true;
            if (!this._rafId[canvasId]) {
                this._rafId[canvasId] = requestAnimationFrame(() => {
                    this._rafId[canvasId] = null;
                    this.drawIntradayChart(canvasId, series, prevClose, item);
                    if (state.hovering) this._drawCrosshair(canvasId, series, prevClose, item, state.mx, state.my);
                });
            }
        };
        const onLeave = () => {
            state.hovering = false;
            this.drawIntradayChart(canvasId, series, prevClose, item);
        };
        canvas.addEventListener('mousemove', onMove);
        canvas.addEventListener('mouseleave', onLeave);
        this._crosshairs[canvasId] = { onMove, onLeave };
    },

    _drawCrosshair(canvasId, series, prevClose, item, mx, my) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !series || series.length < 2) return;
        const ctx = canvas.getContext('2d');
        const dpr = this.dpr;
        const w = canvas.width / dpr;
        const h = canvas.height / dpr;

        const prices = series.map(s => s.p);
        const times = series.map(s => s.t);
        const allPrices = [...prices, prevClose];
        const minP = Math.min(...allPrices);
        const maxP = Math.max(...allPrices);
        const range = maxP - minP || 1;
        const padding = { top: 8, bottom: 24, left: 8, right: 64 };
        const chartW = w - padding.left - padding.right;
        const chartH = h - padding.top - padding.bottom;

        const cx = Math.max(padding.left, Math.min(mx, w - padding.right));

        // Find data point index and get its Y position
        const idx = Math.round(((cx - padding.left) / chartW) * (prices.length - 1));
        const ci = Math.max(0, Math.min(prices.length - 1, idx));
        const dataPrice = prices[ci];
        const dataY = padding.top + (1 - (dataPrice - minP) / range) * chartH;

        ctx.strokeStyle = 'rgba(255,255,255,0.25)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(cx, padding.top); ctx.lineTo(cx, h - padding.bottom); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(padding.left, dataY); ctx.lineTo(w - padding.right, dataY); ctx.stroke();
        ctx.setLineDash([]);

        const d = new Date(times[ci]);
        const timeLabel = d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
        const tlw = 44;
        ctx.fillStyle = '#363a45';
        ctx.fillRect(cx - tlw / 2, h - padding.bottom + 1, tlw, 18);
        ctx.fillStyle = '#e0e0e0';
        ctx.font = '10px Segoe UI';
        ctx.textAlign = 'center';
        ctx.fillText(timeLabel, cx, h - padding.bottom + 13);

        const priceLabel = this.fmtAxis(dataPrice, item);
        ctx.fillStyle = '#363a45';
        ctx.fillRect(w - padding.right + 1, dataY - 9, padding.right - 2, 18);
        ctx.fillStyle = '#e0e0e0';
        ctx.font = '10px Segoe UI';
        ctx.textAlign = 'left';
        ctx.fillText(priceLabel, w - padding.right + 4, dataY + 4);

        const snapX = padding.left + (ci / (prices.length - 1)) * chartW;
        const snapY = padding.top + (1 - (prices[ci] - minP) / range) * chartH;
        ctx.beginPath();
        ctx.arc(snapX, snapY, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#fff';
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.5)';
        ctx.lineWidth = 1;
        ctx.stroke();
    },

    // --- Chart Drawing ---
    drawIntradayChart(canvasId, series, prevClose, item) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        this.sizeCanvas(canvas);
        const ctx = canvas.getContext('2d');
        const dpr = this.dpr;
        const w = canvas.width / dpr;
        const h = canvas.height / dpr;

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

        // Current price dot + line to label
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

        // Time axis
        ctx.fillStyle = '#555';
        ctx.font = '9px Segoe UI';
        ctx.textAlign = 'center';
        const step = Math.max(1, Math.floor(times.length / 6));
        for (let i = 0; i < times.length; i += step) {
            const d = new Date(times[i]);
            const label = d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
            ctx.fillText(label, toX(i), h - 6);
        }

        // CLOSED watermark
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
