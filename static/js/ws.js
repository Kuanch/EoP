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
