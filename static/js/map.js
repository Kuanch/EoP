// Leaflet map with live aircraft + ship tracking

const MapView = {
    map: null,
    militaryLayer: null,
    shipsLayer: null,
    shipsRenderer: null,
    layers: { aircraft: true, ships: true },
    _allShips: [],       // raw data from server
    _filteredShips: [],   // after client-side filter

    // Filter state
    filters: {
        country: 'China',
        type: '',
        minSpeed: 0.5,
    },

    init() {
        const mapEl = document.getElementById('threat-map');
        if (!mapEl) return;

        this.map = L.map('threat-map', { zoomControl: true, preferCanvas: true }).setView([25, 120], 4);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap &copy; CARTO',
            maxZoom: 18,
        }).addTo(this.map);

        this.shipsRenderer = L.canvas({ padding: 0.5 });

        this.militaryLayer = L.layerGroup().addTo(this.map);
        this.shipsLayer = L.layerGroup().addTo(this.map);

        // WebSocket listeners
        WS.on('military', (data) => this.updateMilitary(data));
        WS.on('ships', (data) => { this._allShips = data; this._applyShipFilters(); });

        this._setupToggles();
        this._setupFilterPanel();

        this.loadMilitary();
        this.loadShips();
    },

    // --- Layer toggles ---

    _setupToggles() {
        document.querySelectorAll('.map-layer-btn[data-layer]').forEach(btn => {
            btn.addEventListener('click', () => {
                const layer = btn.dataset.layer;
                this.layers[layer] = !this.layers[layer];
                btn.classList.toggle('active', this.layers[layer]);
                this._applyLayers();
            });
        });
    },

    _applyLayers() {
        if (this.layers.aircraft) this.map.addLayer(this.militaryLayer);
        else this.map.removeLayer(this.militaryLayer);
        if (this.layers.ships) this.map.addLayer(this.shipsLayer);
        else this.map.removeLayer(this.shipsLayer);
    },

    // --- Filter panel ---

    _setupFilterPanel() {
        const toggle = document.getElementById('ship-filter-toggle');
        const panel = document.getElementById('ship-filter-panel');
        if (!toggle || !panel) return;

        toggle.addEventListener('click', () => {
            const open = panel.style.display !== 'none';
            panel.style.display = open ? 'none' : 'block';
            toggle.classList.toggle('active', !open);
        });

        // Live preview count on filter change
        const inputs = ['sf-country', 'sf-type', 'sf-speed'];
        inputs.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', () => this._updateFilterPreview());
        });

        // Apply button
        const applyBtn = document.getElementById('sf-apply');
        if (applyBtn) applyBtn.addEventListener('click', () => this._applyFiltersFromPanel());

        // Reset button
        const resetBtn = document.getElementById('sf-reset');
        if (resetBtn) resetBtn.addEventListener('click', () => this._resetFilters());
    },

    _readPanelFilters() {
        return {
            country: (document.getElementById('sf-country')?.value || ''),
            type: (document.getElementById('sf-type')?.value || ''),
            minSpeed: parseFloat(document.getElementById('sf-speed')?.value || '0'),
        };
    },

    _filterShips(ships, filters) {
        return ships.filter(s => {
            if (filters.country && (s.country || '') !== filters.country) return false;
            if (filters.type) {
                const tn = s.vessel_type_name || 'Other';
                if (filters.type === 'Other') {
                    if (tn !== 'Other') return false;
                } else if (tn !== filters.type) return false;
            }
            if (filters.minSpeed > 0 && (s.sog == null || s.sog < filters.minSpeed)) return false;
            return true;
        });
    },

    _updateFilterPreview() {
        const filters = this._readPanelFilters();
        const count = this._filterShips(this._allShips, filters).length;
        const el = document.getElementById('sf-result-count');
        if (el) el.textContent = `${count} ships`;
    },

    _applyFiltersFromPanel() {
        this.filters = this._readPanelFilters();
        this._applyShipFilters();
        // Close panel
        const panel = document.getElementById('ship-filter-panel');
        const toggle = document.getElementById('ship-filter-toggle');
        if (panel) panel.style.display = 'none';
        if (toggle) toggle.classList.remove('active');
    },

    _resetFilters() {
        const country = document.getElementById('sf-country');
        const type = document.getElementById('sf-type');
        const speed = document.getElementById('sf-speed');
        if (country) country.value = '';
        if (type) type.value = '';
        if (speed) speed.value = '0';
        this.filters = { country: '', type: '', minSpeed: 0 };
        this._applyShipFilters();
        this._updateFilterPreview();
    },

    _applyShipFilters() {
        this._filteredShips = this._filterShips(this._allShips, this.filters);
        this._renderShips(this._filteredShips);
    },

    // --- Aircraft ---

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
        this._updateCount('aircraft', assets.length);
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

    // --- Ships (Canvas-rendered CircleMarkers) ---

    _renderShips(ships) {
        this.shipsLayer.clearLayers();
        ships.forEach(s => {
            if (s.lat == null || s.lon == null) return;
            const color = this._vesselColor(s.vessel_type);
            const radius = this._vesselRadius(s.vessel_type);
            const marker = L.circleMarker([s.lat, s.lon], {
                renderer: this.shipsRenderer,
                radius: radius,
                fillColor: color,
                color: '#000',
                weight: 0.5,
                fillOpacity: 0.8,
            });
            const speedStr = s.sog != null ? s.sog + ' kn' : 'N/A';
            const headingStr = s.heading != null ? Math.round(s.heading) + '°' : 'N/A';
            marker.bindTooltip(
                `<b>${this._esc(s.name || 'Unknown')}</b><br>` +
                `MMSI: ${this._esc(s.mmsi)}<br>` +
                `Flag: ${this._esc(s.country || 'Unknown')}<br>` +
                `Type: ${this._esc(s.vessel_type_name || 'Other')}<br>` +
                `Speed: ${speedStr}<br>` +
                `Heading: ${headingStr}`,
                { className: 'dark-tooltip' }
            );
            this.shipsLayer.addLayer(marker);
        });
        this._updateCount('ships', ships.length);
    },

    _vesselColor(vtype) {
        if (vtype >= 70 && vtype <= 79) return '#4488ff';   // Cargo — blue
        if (vtype >= 80 && vtype <= 89) return '#ff4444';   // Tanker — red
        if (vtype === 30) return '#44cc66';                  // Fishing — green
        if (vtype === 35) return '#888888';                  // Military — gray
        if (vtype >= 60 && vtype <= 69) return '#aa44ff';   // Passenger — purple
        if (vtype === 36 || vtype === 37) return '#44dddd'; // Sailing/yacht — cyan
        return '#ff8833';                                    // Other — orange
    },

    _vesselRadius(vtype) {
        if (vtype === 35) return 5;                          // Military
        if (vtype >= 80 && vtype <= 89) return 4;           // Tanker
        if (vtype >= 70 && vtype <= 79) return 4;           // Cargo
        if (vtype >= 60 && vtype <= 69) return 4;           // Passenger
        return 3;
    },

    // --- Shared ---

    _updateCount(type, count) {
        const el = document.getElementById(`map-count-${type}`);
        if (el) el.textContent = count;
    },

    _esc(s) {
        if (!s) return '';
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    },

    async loadMilitary() {
        try {
            const resp = await fetch('/api/military');
            if (resp.ok) { const d = await resp.json(); if (d.length) this.updateMilitary(d); }
        } catch (e) {}
    },

    async loadShips() {
        try {
            // Fetch all ships, filter client-side for instant filtering
            const resp = await fetch('/api/ships?filter=all');
            if (resp.ok) {
                const d = await resp.json();
                this._allShips = d;
                this._applyShipFilters();
                this._updateFilterPreview();
            }
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
