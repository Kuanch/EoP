// Leaflet map with live aircraft tracking

const MapView = {
    map: null,
    militaryLayer: null,

    init() {
        const mapEl = document.getElementById('threat-map');
        if (!mapEl) return;

        this.map = L.map('threat-map', { zoomControl: true }).setView([25, 120], 4);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap &copy; CARTO',
            maxZoom: 18,
        }).addTo(this.map);

        this.militaryLayer = L.layerGroup().addTo(this.map);

        WS.on('military', (data) => this.updateMilitary(data));
        this.loadMilitary();
    },

    _aircraftIcon(heading, color) {
        const rot = heading != null ? heading : 0;
        const svg = `<svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg" style="transform:rotate(${rot}deg)">
            <path d="M10 2 L12 8 L18 14 L10 12 L2 14 L8 8 Z" fill="${color}" stroke="#000" stroke-width="0.5" opacity="0.9"/>
        </svg>`;
        return L.divIcon({
            html: svg,
            iconSize: [20, 20],
            iconAnchor: [10, 10],
            className: '',
        });
    },

    updateMilitary(assets) {
        this.militaryLayer.clearLayers();
        assets.forEach(a => {
            if (a.lat == null || a.lon == null) return;
            const color = this._countryColor(a.origin_country);
            const marker = L.marker([a.lat, a.lon], {
                icon: this._aircraftIcon(a.heading, color),
            });
            marker.bindTooltip(
                `<b>${this._esc(a.callsign || 'Unknown')}</b><br>` +
                `Country: ${this._esc(a.origin_country || 'N/A')}<br>` +
                `Alt: ${a.altitude ? Math.round(a.altitude) + 'm' : 'N/A'}<br>` +
                `Heading: ${a.heading ? Math.round(a.heading) + '°' : 'N/A'}<br>` +
                `Region: ${this._esc(a.region || '')}`,
                { className: 'dark-tooltip' }
            );
            this.militaryLayer.addLayer(marker);
        });
    },

    _countryColor(country) {
        if (!country) return '#e94560';
        const c = country.toLowerCase();
        if (c.includes('china') || c === 'hong kong') return '#ff4444';
        if (c.includes('russia')) return '#ff6600';
        if (c.includes('united states')) return '#4488ff';
        if (c.includes('japan')) return '#ffffff';
        if (c.includes('korea')) return '#44ddff';
        if (c.includes('taiwan') || c.includes('republic of china')) return '#44ff88';
        return '#e94560';
    },

    _esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; },

    async loadMilitary() {
        try {
            const resp = await fetch('/api/military');
            if (resp.ok) { const d = await resp.json(); if (d.length) this.updateMilitary(d); }
        } catch (e) {}
    }
};

document.addEventListener('DOMContentLoaded', () => {
    const observer = new MutationObserver(() => {
        const mapTab = document.getElementById('tab-map');
        if (mapTab && mapTab.classList.contains('active')) {
            observer.disconnect();
            setTimeout(() => MapView.init(), 50);
        }
    });
    observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'] });
    const mapTab = document.getElementById('tab-map');
    if (mapTab && mapTab.classList.contains('active')) {
        observer.disconnect();
        setTimeout(() => MapView.init(), 50);
    }
});
