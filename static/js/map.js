// Leaflet map with live aircraft + ship tracking

const MapView = {
    map: null,
    militaryLayer: null,
    shipsLayer: null,
    shipsRenderer: null,
    layers: { aircraft: true, ships: true },
    _allShips: [],       // raw data from server
    _filteredShips: [],   // after client-side filter
    _allAircraft: [],    // raw aircraft data
    _filteredAircraft: [], // after client-side filter

    // Filter states
    shipFilters: {
        country: 'China',
        type: 'Law Enforcement',
        minSpeed: 0,
    },
    aircraftFilters: {
        country: '',
        type: '',
        minAltitude: 0,
    },

    init() {
        const mapEl = document.getElementById('threat-map');
        if (!mapEl) {
            return;
        }

        this.map = L.map('threat-map', { zoomControl: true, preferCanvas: true }).setView([25, 120], 4);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap &copy; CARTO',
            maxZoom: 18,
        }).addTo(this.map);

        this.shipsRenderer = L.canvas({ padding: 0.5 });

        this.militaryLayer = L.layerGroup().addTo(this.map);
        this.shipsLayer = L.layerGroup().addTo(this.map);

        // WebSocket listeners
        WS.on('military', (data) => {
            this._allAircraft = data;
            this._filteredAircraft = this._filterAircraft(this._allAircraft, this.aircraftFilters);
            this._renderAircraft();
        });
        WS.on('ships', (data) => {
            this._allShips = data;
            this._filteredShips = this._filterShips(this._allShips, this.shipFilters);
            this._renderShips(this._filteredShips);
        });

        this._setupIntegratedFilters();

        this.loadMilitary();
        this.loadShips();

        console.log('[MapView] Map initialization complete');
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

    // --- Integrated Filter System ---

    _setupIntegratedFilters() {
        // Aircraft filter dropdown and layer toggle
        const aircraftBtn = document.getElementById('aircraft-toggle');
        const aircraftPanel = document.getElementById('aircraft-filter-panel');

        if (aircraftBtn && aircraftPanel) {
            // Left click - open/close dropdown
            aircraftBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const isOpen = aircraftPanel.style.display === 'block' || window.getComputedStyle(aircraftPanel).display === 'block';
                this._closeAllFilterPanels();
                if (!isOpen) {
                    aircraftPanel.style.display = 'block';
                    aircraftBtn.classList.add('dropdown-open');
                }
            });

            // Right click - toggle layer visibility
            aircraftBtn.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.layers.aircraft = !this.layers.aircraft;
                aircraftBtn.classList.toggle('active', this.layers.aircraft);
                this._applyLayers();
                this._closeAllFilterPanels();
            });

            // Aircraft filter controls with live preview
            const aircraftInputs = ['af-country', 'af-type', 'af-altitude'];
            aircraftInputs.forEach(id => {
                const el = document.getElementById(id);
                if (el) {
                    el.addEventListener('change', () => this._updateAircraftFilterPreview());
                    el.addEventListener('input', () => this._updateAircraftFilterPreview());
                }
            });

            // Initialize preview
            setTimeout(() => this._updateAircraftFilterPreview(), 100);

            const afApply = document.getElementById('af-apply');
            const afReset = document.getElementById('af-reset');
            if (afApply) afApply.addEventListener('click', () => this._applyAircraftFilters());
            if (afReset) afReset.addEventListener('click', () => this._resetAircraftFilters());
        }

        // Ships filter dropdown and layer toggle
        const shipsBtn = document.getElementById('ships-toggle');
        const shipsPanel = document.getElementById('ships-filter-panel');

        if (shipsBtn && shipsPanel) {
            // Left click - open/close dropdown
            shipsBtn.addEventListener('click', (e) => {
                e.stopPropagation();

                const isOpen = shipsPanel.style.display === 'block' || window.getComputedStyle(shipsPanel).display === 'block';
                this._closeAllFilterPanels();
                if (!isOpen) {
                    shipsPanel.style.display = 'block';
                    shipsBtn.classList.add('dropdown-open');
                }
            });

            // Right click - toggle layer visibility
            shipsBtn.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.layers.ships = !this.layers.ships;
                shipsBtn.classList.toggle('active', this.layers.ships);
                this._applyLayers();
                this._closeAllFilterPanels();
            });

            // Ships filter controls with live preview
            const shipInputs = ['sf-country', 'sf-type', 'sf-speed'];
            shipInputs.forEach(id => {
                const el = document.getElementById(id);
                if (el) {
                    el.addEventListener('change', () => this._updateShipFilterPreview());
                    el.addEventListener('input', () => this._updateShipFilterPreview());
                }
            });

            // Initialize preview
            setTimeout(() => this._updateShipFilterPreview(), 100);

            const sfApply = document.getElementById('sf-apply');
            const sfReset = document.getElementById('sf-reset');
            if (sfApply) sfApply.addEventListener('click', () => this._applyShipFilters());
            if (sfReset) sfReset.addEventListener('click', () => {
                this._resetShipFilters();
            });
        }

        // Close dropdowns when clicking outside, but not inside the panels
        document.addEventListener('click', (e) => {
            // Don't close if clicking on a button or inside a filter panel
            if (e.target.closest('.map-layer-btn') || e.target.closest('.filter-dropdown')) {
                return;
            }
            this._closeAllFilterPanels();
        });

        // Prevent filter panels from closing when clicked inside
        document.getElementById('aircraft-filter-panel')?.addEventListener('click', (e) => {
            e.stopPropagation();
        });
        document.getElementById('ships-filter-panel')?.addEventListener('click', (e) => {
            e.stopPropagation();
        });
    },

    _closeAllFilterPanels() {
        const panels = ['aircraft-filter-panel', 'ships-filter-panel'];
        const buttons = ['aircraft-toggle', 'ships-toggle'];

        panels.forEach(id => {
            const panel = document.getElementById(id);
            if (panel) panel.style.display = 'none';
        });

        buttons.forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.classList.remove('dropdown-open');
        });
    },

    // --- Aircraft Filter Methods ---

    _readAircraftFilters() {
        return {
            country: (document.getElementById('af-country')?.value || ''),
            type: (document.getElementById('af-type')?.value || ''),
            minAltitude: parseFloat(document.getElementById('af-altitude')?.value || '0'),
        };
    },

    _filterAircraft(aircraft, filters) {
        return aircraft.filter(a => {
            if (filters.country && (a.origin_country || '') !== filters.country) return false;
            if (filters.type) {
                // Basic type classification based on available data
                let type = 'Civilian';
                if (a.callsign && (a.callsign.includes('MIL') || a.callsign.length < 4)) type = 'Military';
                if (filters.type !== type) return false;
            }
            if (filters.minAltitude > 0) {
                const altitude = a.altitude || 0;
                if (altitude < filters.minAltitude) return false;
            }
            return true;
        });
    },

    _updateAircraftFilterPreview() {
        const filters = this._readAircraftFilters();
        const filtered = this._filterAircraft(this._allAircraft, filters);
        const countEl = document.getElementById('af-result-count');
        if (countEl) countEl.textContent = `${filtered.length} aircraft`;
    },

    _applyAircraftFilters() {
        this.aircraftFilters = this._readAircraftFilters();
        this._filteredAircraft = this._filterAircraft(this._allAircraft, this.aircraftFilters);
        this._renderAircraft();
        this._closeAllFilterPanels();
    },

    _resetAircraftFilters() {
        document.getElementById('af-country').value = '';
        document.getElementById('af-type').value = '';
        document.getElementById('af-altitude').value = '0';
        this._applyAircraftFilters();
    },

    // --- Ship Filter Methods ---

    _readShipFilters() {
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

    _updateShipFilterPreview() {
        const filters = this._readShipFilters();
        const filtered = this._filterShips(this._allShips, filters);
        const countEl = document.getElementById('sf-result-count');
        if (countEl) countEl.textContent = `${filtered.length} ships`;
    },

    _applyShipFilters() {
        const filters = this._readShipFilters();
        this.shipFilters = filters;
        this._filteredShips = this._filterShips(this._allShips, filters);
        this._renderShips(this._filteredShips);
        this._updateShipFilterPreview();
        this._closeAllFilterPanels();
    },

    _resetShipFilters() {
        document.getElementById('sf-country').value = 'China';
        document.getElementById('sf-type').value = 'Law Enforcement';
        document.getElementById('sf-speed').value = '0';
        this._applyShipFilters();
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

    _renderAircraft() {
        this.militaryLayer.clearLayers();
        this._filteredAircraft.forEach(a => {
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
        this._updateCount('aircraft', this._filteredAircraft.length);
    },

    // Legacy method for compatibility - called by WebSocket
    updateMilitary(assets) {
        this._allAircraft = assets;
        this._applyAircraftFilters();
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

    // --- Ships ---

    _shipIcon(s) {
        const color = this._countryColor(s.country);
        const rot = s.cog != null ? Math.round(s.cog) : 0;
        const vtype = s.vessel_type || 0;
        const vname = (s.vessel_type_name || '').toLowerCase();
        const isSpecial = vtype === 35 || vname === 'military' ||
                          vtype === 55 || vname === 'law enforcement' ||
                          vtype === 51 || vname === 'sar';
        const isUnknown = !s.country || s.country === 'Unknown';

        let shape;
        if (isSpecial) {
            // Diamond for military / law enforcement / SAR
            shape = `<polygon points="10,2 18,10 10,18 2,10" fill="${color}" stroke="#fff" stroke-width="1" opacity="0.9"/>`;
        } else if (isUnknown) {
            // X for unknown nationality
            shape = `<line x1="4" y1="4" x2="16" y2="16" stroke="${color}" stroke-width="2.5" opacity="0.9"/>` +
                    `<line x1="16" y1="4" x2="4" y2="16" stroke="${color}" stroke-width="2.5" opacity="0.9"/>`;
        } else {
            // Circle for normal vessels
            return null; // Use circleMarker for performance
        }

        const svg = `<svg width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg" style="transform:rotate(${rot}deg)">${shape}</svg>`;
        return L.divIcon({ html: svg, iconSize: [20, 20], iconAnchor: [10, 10], className: '' });
    },

    _renderShips(ships) {
        this.shipsLayer.clearLayers();
        ships.forEach(s => {
            if (s.lat == null || s.lon == null) return;
            const color = this._countryColor(s.country);
            const icon = this._shipIcon(s);
            let marker;
            if (icon) {
                // SVG marker for special/unknown ships
                marker = L.marker([s.lat, s.lon], { icon });
            } else {
                // Canvas circleMarker for normal ships (fast)
                marker = L.circleMarker([s.lat, s.lon], {
                    renderer: this.shipsRenderer,
                    radius: 3,
                    fillColor: color,
                    color: '#000',
                    weight: 0.5,
                    fillOpacity: 0.8,
                });
            }
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

    // --- Shared ---

    _updateCount(type, count) {
        const el = document.getElementById(`map-count-${type}`);
        if (el) el.textContent = count;
    },

    // Debug helper - call from browser console: MapView.testFilters()
    testFilters() {
        console.log('=== TESTING SHIP FILTERS ===');
        console.log('All ships:', this._allShips.length);

        if (this._allShips.length > 0) {
            console.log('Sample ship:', this._allShips[0]);

            // Test empty filter (should show all)
            const emptyFilter = { country: '', type: '', minSpeed: 0 };
            const emptyResult = this._filterShips(this._allShips, emptyFilter);
            console.log('Empty filter result:', emptyResult.length);

            // Test country filter
            const countryFilter = { country: 'China', type: '', minSpeed: 0 };
            const countryResult = this._filterShips(this._allShips, countryFilter);
            console.log('China filter result:', countryResult.length);

            // Test speed filter
            const speedFilter = { country: '', type: '', minSpeed: 1 };
            const speedResult = this._filterShips(this._allShips, speedFilter);
            console.log('Moving filter result:', speedResult.length);
        }

        console.log('Current ship filters:', this.shipFilters);
        console.log('Current filtered ships:', this._filteredShips.length);
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
                this._filteredShips = this._filterShips(this._allShips, this.shipFilters);
                this._renderShips(this._filteredShips);
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
