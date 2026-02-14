// Leaflet map with heatmap, military markers, and threat regions

const MapView = {
    map: null,
    heatLayer: null,
    militaryLayer: null,
    regionLayer: null,
    newsPoints: [],
    militaryMarkers: [],
    layers: { heatmap: true, military: true, regions: true },

    init() {
        const mapEl = document.getElementById('threat-map');
        if (!mapEl) return;

        this.map = L.map('threat-map', { zoomControl: true }).setView([25, 45], 3);

        // Dark tiles
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap &copy; CARTO',
            maxZoom: 18,
        }).addTo(this.map);

        this.militaryLayer = L.layerGroup().addTo(this.map);
        this.regionLayer = L.layerGroup().addTo(this.map);

        // Heatmap layer (if leaflet.heat loaded)
        if (typeof L.heatLayer !== 'undefined') {
            this.heatLayer = L.heatLayer([], { radius: 25, blur: 15, maxZoom: 10 }).addTo(this.map);
        }

        // Listen to WS
        WS.on('news', (data) => this.onNews(data));
        WS.on('military', (data) => this.updateMilitary(data));
        WS.on('threats', (data) => this.updateRegions(data));

        // Layer controls
        this.setupControls();
        this.loadThreats();
    },

    setupControls() {
        document.querySelectorAll('.map-layer-toggle').forEach(cb => {
            cb.addEventListener('change', (e) => {
                this.layers[e.target.dataset.layer] = e.target.checked;
                this.applyLayers();
            });
        });
    },

    applyLayers() {
        if (this.heatLayer) {
            this.layers.heatmap ? this.map.addLayer(this.heatLayer) : this.map.removeLayer(this.heatLayer);
        }
        this.layers.military ? this.map.addLayer(this.militaryLayer) : this.map.removeLayer(this.militaryLayer);
        this.layers.regions ? this.map.addLayer(this.regionLayer) : this.map.removeLayer(this.regionLayer);
    },

    onNews(articles) {
        articles.forEach(a => {
            if (a.geo_lat && a.geo_lon) {
                this.newsPoints.push([a.geo_lat, a.geo_lon, Math.min(a.threat_score / 10, 1) || 0.3]);
            }
        });
        if (this.heatLayer) {
            this.heatLayer.setLatLngs(this.newsPoints);
        }
    },

    updateMilitary(assets) {
        this.militaryLayer.clearLayers();
        assets.forEach(a => {
            if (a.lat == null || a.lon == null) return;
            const marker = L.circleMarker([a.lat, a.lon], {
                radius: 4,
                color: '#e94560',
                fillColor: '#e94560',
                fillOpacity: 0.8,
                weight: 1,
            });
            marker.bindTooltip(
                `<b>${a.callsign || 'Unknown'}</b><br>` +
                `Country: ${a.origin_country || 'N/A'}<br>` +
                `Alt: ${a.altitude ? Math.round(a.altitude) + 'm' : 'N/A'}<br>` +
                `Heading: ${a.heading ? Math.round(a.heading) + '°' : 'N/A'}`,
                { className: 'dark-tooltip' }
            );
            this.militaryLayer.addLayer(marker);
        });
    },

    updateRegions(data) {
        this.regionLayer.clearLayers();
        const regions = {
            "Taiwan Strait": [24.0, 119.5],
            "East Ukraine": [49.0, 36.0],
            "Middle East": [33.0, 44.0],
            "Korean Peninsula": [38.0, 127.0],
            "South China Sea": [13.0, 113.0],
        };
        for (const [name, score] of Object.entries(data)) {
            const center = regions[name];
            if (!center) continue;
            const color = score >= 70 ? '#ff1744' : score >= 40 ? '#ff9100' : score >= 20 ? '#ffea00' : '#448aff';
            const circle = L.circle(center, {
                radius: 300000 + score * 5000,
                color: color,
                fillColor: color,
                fillOpacity: 0.15,
                weight: 2,
            });
            circle.bindTooltip(`<b>${name}</b><br>Threat Score: ${score}/100`, { className: 'dark-tooltip' });
            this.regionLayer.addLayer(circle);
        }
    },

    async loadThreats() {
        try {
            const resp = await fetch('/api/threats');
            if (resp.ok) this.updateRegions(await resp.json());
        } catch (e) {}
    }
};

document.addEventListener('DOMContentLoaded', () => {
    // Defer init until map tab is first shown (Leaflet needs visible container)
    const observer = new MutationObserver(() => {
        const mapTab = document.getElementById('tab-map');
        if (mapTab && mapTab.classList.contains('active')) {
            observer.disconnect();
            setTimeout(() => MapView.init(), 50);
        }
    });
    observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'] });
    // Also try immediately in case map tab is already active
    const mapTab = document.getElementById('tab-map');
    if (mapTab && mapTab.classList.contains('active')) {
        observer.disconnect();
        setTimeout(() => MapView.init(), 50);
    }
});
