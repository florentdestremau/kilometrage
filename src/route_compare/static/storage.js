/**
 * storage.js — Wrapper localStorage pour Route Compare.
 * Toutes les clés sont préfixées `rc:`.
 * Schéma versionné avec migration automatique.
 */

const SCHEMA_VERSION = 1;
const PREFIX = 'rc:';
const HISTORY_MAX = 20;
const DEDUP_WINDOW_MS = 5 * 60 * 1000; // 5 min

function key(name) {
  return PREFIX + name;
}

function safeGet(k) {
  try {
    const raw = localStorage.getItem(k);
    return raw ? JSON.parse(raw) : null;
  } catch {
    console.warn('[storage] parse error for', k, '— resetting');
    localStorage.removeItem(k);
    return null;
  }
}

function safeSet(k, v) {
  try {
    localStorage.setItem(k, JSON.stringify(v));
  } catch (e) {
    console.warn('[storage] write error', e);
  }
}

// ── Migration ──────────────────────────────────────────────────────────────
function migrate(data) {
  if (!data || !data.schema_version) return null;
  // Versions futures : ajouter des cases ici
  return data;
}

// ── Vehicles ───────────────────────────────────────────────────────────────
const vehicles = {
  list() {
    return safeGet(key('vehicles')) || [];
  },

  get(id) {
    return this.list().find(v => v.id === id) || null;
  },

  save(vehicle) {
    const list = this.list();
    const now = new Date().toISOString();
    if (vehicle.id) {
      const idx = list.findIndex(v => v.id === vehicle.id);
      if (idx >= 0) {
        list[idx] = { ...list[idx], ...vehicle };
      } else {
        list.push({ created_at: now, ...vehicle });
      }
    } else {
      vehicle = { ...vehicle, id: crypto.randomUUID(), created_at: now };
      list.push(vehicle);
    }
    safeSet(key('vehicles'), list);
    return vehicle;
  },

  delete(id) {
    const list = this.list().filter(v => v.id !== id);
    safeSet(key('vehicles'), list);
    // Si le véhicule supprimé était le dernier utilisé, réinitialiser
    const prefs = storage.prefs.get();
    if (prefs.last_vehicle_id === id) {
      storage.prefs.update({ last_vehicle_id: list[0]?.id || null });
    }
  },
};

// ── History ────────────────────────────────────────────────────────────────
const history = {
  list(limit = HISTORY_MAX) {
    const all = safeGet(key('history')) || [];
    return all.slice(0, limit);
  },

  add(search) {
    const all = safeGet(key('history')) || [];
    const now = Date.now();

    // Dedupe : même from+to+max_speed dans les 5 dernières min
    const isDupe = all.some(s =>
      s.from?.label === search.from?.label &&
      s.to?.label === search.to?.label &&
      s.max_speed === search.max_speed &&
      now - new Date(s.timestamp).getTime() < DEDUP_WINDOW_MS
    );
    if (isDupe) return;

    const entry = {
      ...search,
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
    };
    all.unshift(entry);
    safeSet(key('history'), all.slice(0, HISTORY_MAX));
  },

  clear() {
    localStorage.removeItem(key('history'));
  },
};

// ── Prefs ──────────────────────────────────────────────────────────────────
const DEFAULT_PREFS = {
  schema_version: SCHEMA_VERSION,
  last_vehicle_id: null,
  last_max_speed: 110,
  units: 'metric',
};

const prefs = {
  get() {
    const raw = safeGet(key('prefs'));
    const migrated = migrate(raw);
    return { ...DEFAULT_PREFS, ...(migrated || {}) };
  },

  update(partial) {
    const current = this.get();
    safeSet(key('prefs'), { ...current, ...partial });
  },
};

// ── Export / Import ────────────────────────────────────────────────────────
function exportData() {
  return JSON.stringify(
    {
      schema_version: SCHEMA_VERSION,
      exported_at: new Date().toISOString(),
      vehicles: vehicles.list(),
      history: history.list(),
      prefs: prefs.get(),
    },
    null,
    2
  );
}

function importData(json) {
  let data;
  try {
    data = JSON.parse(json);
  } catch {
    throw new Error('JSON invalide');
  }
  if (data.schema_version !== SCHEMA_VERSION) {
    throw new Error(`Version de schéma incompatible : ${data.schema_version}`);
  }
  if (Array.isArray(data.vehicles)) safeSet(key('vehicles'), data.vehicles);
  if (Array.isArray(data.history)) safeSet(key('history'), data.history);
  if (data.prefs) safeSet(key('prefs'), data.prefs);
}

window.storage = { vehicles, history, prefs, exportData, importData };
