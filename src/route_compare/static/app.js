// storage est injecté globalement par storage.js (window.storage)

// ── Leaflet polyline colors par preset ─────────────────────────────────────
const PRESET_COLORS = {
  motorway_capped: '#2563eb',
  avoid_tolls: '#16a34a',
  balanced: '#d97706',
};

// ── Utilitaires ────────────────────────────────────────────────────────────
function formatDuration(min) {
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return h > 0 ? `${h}h${String(m).padStart(2, '0')}` : `${m} min`;
}

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return 'à l\'instant';
  if (min < 60) return `il y a ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `il y a ${h}h`;
  const d = Math.floor(h / 24);
  return `il y a ${d}j`;
}

// ── Autocomplete Nominatim ─────────────────────────────────────────────────
async function geocodeSuggest(query) {
  if (query.length < 3) return [];
  try {
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=5&addressdetails=0&accept-language=fr`;
    const resp = await fetch(url, { headers: { 'User-Agent': 'route-compare/1.0' } });
    return await resp.json();
  } catch {
    return [];
  }
}

// ── App Alpine ─────────────────────────────────────────────────────────────
document.addEventListener('alpine:init', () => {
  Alpine.data('routeApp', () => ({
    // Form state
    origin: '',
    originSuggestions: [],
    originCoord: null,
    destination: '',
    destSuggestions: [],
    destCoord: null,
    maxSpeed: window.storage.prefs.get().last_max_speed || 110,
    manualConsumption: 6.5,
    manualFuelPrice: 1.75,

    // Vehicle
    vehicles: [],
    selectedVehicleId: null,
    showVehicleModal: false,
    editingVehicle: null,
    vehicleForm: { name: '', fuel_type: 'essence', consumption_l_per_100: 6.5, fuel_price: 1.75, preferred_max_speed: 110 },

    // Results
    loading: false,
    error: null,
    routes: [],
    narratorText: '',
    narratorLoading: false,
    narratorAvailable: false,

    // History
    historyItems: [],
    showHistory: true,

    // Settings
    showSettings: false,
    showImportInput: false,

    // Map
    map: null,
    polylines: [],

    // Onboarding
    showOnboarding: false,

    // Cache
    lastResultId: null,

    init() {
      this.vehicles = window.storage.vehicles.list();
      this.historyItems = window.storage.history.list();
      const prefs = window.storage.prefs.get();
      this.selectedVehicleId = prefs.last_vehicle_id;
      this.maxSpeed = prefs.last_max_speed;

      // Onboarding si pas de véhicule
      if (this.vehicles.length === 0) {
        this.showOnboarding = true;
      }

      // Restaurer le dernier résultat sans recalcul
      const lastId = prefs.last_result_id;
      if (lastId) {
        const cached = window.storage.results.get(lastId);
        if (cached) {
          this._applyResult(cached.data);
          // Pré-remplir le formulaire avec les valeurs de la recherche
          const entry = this.historyItems.find(h => h.id === lastId);
          if (entry) {
            this.origin = entry.from.label;
            this.destination = entry.to.label;
            this.maxSpeed = entry.max_speed;
          }
        }
      }

      this.$nextTick(() => this._initMap());
    },

    _applyResult(data) {
      this.routes = data.routes;
      this.narratorAvailable = data.narrator_available;
      this.$nextTick(() => this._drawRoutes(this.routes));
    },

    // ── Map ────────────────────────────────────────────────────────────────
    _initMap() {
      const container = document.getElementById('map');
      if (!container || container._leaflet_id) return; // déjà initialisée
      this.map = L.map('map').setView([46.8, 2.3], 6);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap',
        maxZoom: 18,
      }).addTo(this.map);
    },

    _drawRoutes(routes) {
      this.polylines.forEach(p => p.remove());
      this.polylines = [];
      const bounds = [];

      routes.forEach((route, i) => {
        if (!route.geometry?.length) return;
        // geometry = [[lng, lat], ...]  → Leaflet veut [lat, lng]
        const latlngs = route.geometry.map(([lng, lat]) => [lat, lng]);
        const color = PRESET_COLORS[route.preset] || '#888';
        const weight = i === 0 ? 5 : 3;
        const opacity = i === 0 ? 0.9 : 0.5;
        const pl = L.polyline(latlngs, { color, weight, opacity }).addTo(this.map);
        pl.bindTooltip(route.label);
        this.polylines.push(pl);
        bounds.push(...latlngs);
      });

      if (bounds.length > 0) {
        this.map.fitBounds(L.latLngBounds(bounds), { padding: [30, 30] });
      }
    },

    // ── Autocomplete ───────────────────────────────────────────────────────
    async onOriginInput() {
      this.originCoord = null;
      this.originSuggestions = await geocodeSuggest(this.origin);
    },

    selectOrigin(item) {
      this.origin = item.display_name;
      this.originCoord = { lat: parseFloat(item.lat), lng: parseFloat(item.lon) };
      this.originSuggestions = [];
    },

    async onDestInput() {
      this.destCoord = null;
      this.destSuggestions = await geocodeSuggest(this.destination);
    },

    selectDest(item) {
      this.destination = item.display_name;
      this.destCoord = { lat: parseFloat(item.lat), lng: parseFloat(item.lon) };
      this.destSuggestions = [];
    },

    // ── Véhicule courant ───────────────────────────────────────────────────
    get currentVehicle() {
      if (!this.selectedVehicleId) return null;
      return this.vehicles.find(v => v.id === this.selectedVehicleId) || null;
    },

    get fuelConsumption() {
      return this.currentVehicle?.consumption_l_per_100 ?? 6.5;
    },

    get fuelPrice() {
      return this.currentVehicle?.fuel_price ?? 1.75;
    },

    onVehicleChange() {
      window.storage.prefs.update({ last_vehicle_id: this.selectedVehicleId });
      const v = this.currentVehicle;
      if (v?.preferred_max_speed) this.maxSpeed = v.preferred_max_speed;
    },

    onSpeedChange() {
      window.storage.prefs.update({ last_max_speed: this.maxSpeed });
    },

    // ── CRUD Véhicule ──────────────────────────────────────────────────────
    openNewVehicle() {
      this.editingVehicle = null;
      this.vehicleForm = { name: '', fuel_type: 'essence', consumption_l_per_100: 6.5, fuel_price: 1.75, preferred_max_speed: 110 };
      this.showVehicleModal = true;
    },

    editVehicle(v) {
      this.editingVehicle = v;
      this.vehicleForm = { ...v };
      this.showVehicleModal = true;
    },

    saveVehicle() {
      const v = window.storage.vehicles.save({ ...this.vehicleForm, id: this.editingVehicle?.id });
      this.vehicles = window.storage.vehicles.list();
      if (!this.selectedVehicleId) {
        this.selectedVehicleId = v.id;
        window.storage.prefs.update({ last_vehicle_id: v.id });
      }
      this.showVehicleModal = false;
    },

    deleteVehicle(id) {
      if (!confirm('Supprimer ce véhicule ?')) return;
      window.storage.vehicles.delete(id);
      this.vehicles = window.storage.vehicles.list();
      if (this.selectedVehicleId === id) {
        this.selectedVehicleId = this.vehicles[0]?.id || null;
        window.storage.prefs.update({ last_vehicle_id: this.selectedVehicleId });
      }
    },

    // ── Onboarding ─────────────────────────────────────────────────────────
    createDefaultVehicle() {
      const v = window.storage.vehicles.save({
        name: 'Mon véhicule',
        fuel_type: 'essence',
        consumption_l_per_100: 6.5,
        fuel_price: 1.75,
        preferred_max_speed: 110,
      });
      this.vehicles = window.storage.vehicles.list();
      this.selectedVehicleId = v.id;
      window.storage.prefs.update({ last_vehicle_id: v.id });
      this.showOnboarding = false;
    },

    // ── Compare ────────────────────────────────────────────────────────────
    async compare() {
      if (!this.origin || !this.destination) {
        this.error = 'Veuillez renseigner le départ et la destination.';
        return;
      }

      this.loading = true;
      this.error = null;
      this.routes = [];
      this.narratorText = '';

      try {
        const resp = await fetch('/compare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            origin: this.origin,
            destination: this.destination,
            max_speed: this.maxSpeed,
            fuel_consumption_l_per_100: this.fuelConsumption,
            fuel_price: this.fuelPrice,
          }),
        });

        if (!resp.ok) {
          const err = await resp.json();
          throw new Error(err.detail || 'Erreur serveur');
        }

        const data = await resp.json();
        this.routes = data.routes;
        this.narratorAvailable = data.narrator_available;

        this._drawRoutes(this.routes);

        // Sauvegarder dans l'historique + résultat complet
        if (this.routes.length > 0) {
          const best = this.routes[0];
          const entry = window.storage.history.add({
            from: { label: this.origin, lat: this.originCoord?.lat, lng: this.originCoord?.lng },
            to: { label: this.destination, lat: this.destCoord?.lat, lng: this.destCoord?.lng },
            max_speed: this.maxSpeed,
            vehicle_id: this.selectedVehicleId,
            result_summary: {
              best_option_label: best.label,
              best_cost_eur: best.cost.total_eur,
              best_duration_min: best.duration_min,
            },
          });
          this.historyItems = window.storage.history.list();

          if (entry) {
            window.storage.results.save(entry.id, data);
            window.storage.prefs.update({ last_result_id: entry.id });
            this.lastResultId = entry.id;
          }
        }

        // Narration LLM
        if (data.narrator_available) {
          this._fetchNarration(data);
        }
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    async _fetchNarration(data) {
      this.narratorLoading = true;
      this.narratorText = '';
      try {
        const resp = await fetch('/narrate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop();
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const chunk = line.slice(6);
              if (chunk === '[DONE]') break;
              this.narratorText += chunk;
            }
          }
        }
      } catch (e) {
        console.warn('narrator error', e);
      } finally {
        this.narratorLoading = false;
      }
    },

    // ── Historique ─────────────────────────────────────────────────────────
    replaySearch(item) {
      this.origin = item.from.label;
      this.destination = item.to.label;
      this.maxSpeed = item.max_speed;
      this.originCoord = item.from;
      this.destCoord = item.to;
      this.error = null;
      this.narratorText = '';

      // Afficher depuis le cache localStorage si disponible
      const cached = window.storage.results.get(item.id);
      if (cached) {
        this._applyResult(cached.data);
        window.storage.prefs.update({ last_result_id: item.id });
        return;
      }

      // Sinon recalcul
      this.compare();
    },

    clearHistory() {
      if (!confirm('Effacer tout l\'historique ?')) return;
      window.storage.history.clear();
      this.historyItems = [];
    },

    // ── Export / Import ────────────────────────────────────────────────────
    exportData() {
      const json = window.storage.exportData();
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `route-compare-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      this.showSettings = false;
    },

    importData(event) {
      const file = event.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          window.storage.importData(e.target.result);
          this.vehicles = window.storage.vehicles.list();
          this.historyItems = window.storage.history.list();
          const prefs = window.storage.prefs.get();
          this.selectedVehicleId = prefs.last_vehicle_id;
          alert('Import réussi !');
        } catch (err) {
          alert('Erreur import : ' + err.message);
        }
        this.showSettings = false;
        this.showImportInput = false;
      };
      reader.readAsText(file);
    },

    // ── Helpers template ───────────────────────────────────────────────────
    formatDuration,
    timeAgo,

    isIOS() {
      return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    },

    isMac() {
      return /Macintosh/.test(navigator.userAgent);
    },

    showAppleMaps() {
      return this.isIOS() || this.isMac();
    },
  }));
});
