// WebSocket client with auto-reconnect and module dispatch

const WS = {
    socket: null,
    reconnectDelay: 1000,
    maxDelay: 30000,
    handlers: {},

    connect() {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${location.host}/ws`;

        this.setStatus('connecting');
        this.socket = new WebSocket(url);

        this.socket.onopen = () => {
            console.log('[WS] Connected');
            this.setStatus('connected');
            this.reconnectDelay = 1000;
        };

        this.socket.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                const handler = this.handlers[msg.module];
                if (handler) handler(msg.data);
            } catch (e) {
                console.error('[WS] Parse error:', e);
            }
        };

        this.socket.onclose = () => {
            console.log('[WS] Disconnected, reconnecting...');
            this.setStatus('disconnected');
            setTimeout(() => this.connect(), this.reconnectDelay);
            this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxDelay);
        };

        this.socket.onerror = () => {
            this.socket.close();
        };
    },

    on(module, handler) {
        this.handlers[module] = handler;
    },

    setStatus(state) {
        const dot = document.getElementById('ws-status');
        if (!dot) return;
        dot.className = 'ws-status';
        if (state === 'connected') dot.classList.add('connected');
        else if (state === 'connecting') dot.classList.add('connecting');
    }
};

document.addEventListener('DOMContentLoaded', () => WS.connect());

// Data freshness polling — one aggregated dot per tab
const BAD = ['down', 'error'];
const WARN = ['stale', 'no_data'];

const DataHealth = {
    _ageText(age) {
        if (age === null) return 'no data';
        if (age < 60) return Math.round(age) + 's ago';
        if (age < 3600) return Math.round(age / 60) + 'm ago';
        return Math.round(age / 3600) + 'h ago';
    },

    poll() {
        fetch('/api/health/data')
            .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
            .then(data => {
                document.querySelectorAll('.health-dot[data-tab-health]').forEach(dot => {
                    const sources = (dot.dataset.sources || '').split(',').filter(Boolean);
                    // Build per-source info; treat missing sources as no_data
                    const infos = sources.map(s => data[s] || { source_name: s, status: 'no_data', last_success_ago: null, error_count: 0, last_error_msg: null });

                    const allBad = infos.every(i => BAD.includes(i.status));
                    const anyBad = infos.some(i => BAD.includes(i.status) || WARN.includes(i.status));

                    let status;
                    if (allBad) status = 'down';
                    else if (anyBad) status = 'stale';
                    else status = 'fresh';

                    dot.className = 'health-dot ' + status;

                    const tabName = dot.dataset.tabHealth;
                    const lines = infos.map(i => {
                        let line = (i.source_name || '') + ': ' + i.status + ' (' + this._ageText(i.last_success_ago) + ')';
                        if (i.error_count > 0) line += ' [' + i.error_count + ' err]';
                        if (i.last_error_msg) line += ' ' + i.last_error_msg;
                        return line;
                    });
                    dot.setAttribute('title', tabName + ' — ' + status + '\n' + lines.join('\n'));
                });
            })
            .catch(() => {});
    },

    start() {
        this.poll();
        setInterval(() => this.poll(), 30000);
    }
};

document.addEventListener('DOMContentLoaded', () => DataHealth.start());
