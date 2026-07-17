importScripts("https://cdn.jsdelivr.net/npm/satellite.js@7.0.1/dist/satellite.min.js");

let satrecs     = [];
let meanClasses = [];
let objectTypes = [];

const OBJ_PAYLOAD = 0;
const OBJ_DEBRIS  = 1;
const OBJ_RB      = 2;

// Orbital class constants — must match LAYER_* arrays in index.html
const CLS_VLEO      = 0;   // Very Low Earth Orbit: 160–450 km
const CLS_LEO       = 1;   // Low Earth Orbit: 450–2,000 km
const CLS_MEO       = 2;   // Medium Earth Orbit: 2,000–35,486 km, ecc < 0.25
const CLS_GEO       = 3;   // Geostationary: 35,486–36,100 km band
const CLS_HEO       = 4;   // Highly Elliptical Orbit: eccentricity >= 0.25
const CLS_GRAVEYARD = 5;   // Disposal/Graveyard: > 36,100 km, ecc < 0.25

const GM_KM3S2    = 398600.4418;
const R_EARTH     = 6371.0;
const HEO_ECC_MIN = 0.25;
const GEO_LOW_KM  = 35486.0;
const GEO_HIGH_KM = 36086.0;
const VLEO_MAX_KM = 450.0;
const LEO_MAX_KM  = 2000.0;

function parseOMM(records) {
    // Parse an array of OMM JSON objects from /catalog into satrec records.
    // Uses satellite.js json2satrec — supports 6-digit NORAD IDs natively.
    const result = [];
    for (const omm of records) {
        if (!omm || omm.NORAD_CAT_ID === undefined) continue;
        try {
            const satrec = satellite.json2satrec(omm);
            const name   = omm.OBJECT_NAME || String(omm.NORAD_CAT_ID);
            const norad  = String(omm.NORAD_CAT_ID);
            result.push({ name, norad_id: norad, satrec });
        } catch (_) {}
    }
    return result;
}

function computeMeanOrbitalClass(satrec) {
    // Classify by mean semi-major axis altitude AND eccentricity.
    // HEO check runs BEFORE altitude to capture Molniya/Tundra.
    const n_rad_min = satrec.no;
    if (!n_rad_min || n_rad_min <= 0) return CLS_LEO;

    const ecc     = satrec.ecco || 0;
    const n_rad_s = n_rad_min / 60.0;
    const a_km    = Math.cbrt(GM_KM3S2 / (n_rad_s * n_rad_s));
    const alt_km  = a_km - R_EARTH;

    if (ecc >= HEO_ECC_MIN) return CLS_HEO;
    if (alt_km < VLEO_MAX_KM)  return CLS_VLEO;
    if (alt_km < LEO_MAX_KM)   return CLS_LEO;
    if (alt_km < GEO_LOW_KM)   return CLS_MEO;
    if (alt_km <= GEO_HIGH_KM) return CLS_GEO;
    return CLS_GRAVEYARD;
}

function classifyObjectType(name) {
    // Mirrors engine.py object_type classification exactly.
    const n = name.toUpperCase().trim();
    if (n.endsWith(" DEB") || n.endsWith("DEB") || n.includes("DEBRIS")) return OBJ_DEBRIS;
    if (n.includes(" R/B") || n.endsWith("R/B") || n.includes("ROCKET")) return OBJ_RB;
    if (/^\d+$/.test(n)) return OBJ_DEBRIS;
    return OBJ_PAYLOAD;
}

self.onmessage = (e) => {
    if (e.data.type === "init") {
        // e.data.records is an array of OMM JSON objects from /catalog
        satrecs     = parseOMM(e.data.records);
        meanClasses = satrecs.map(r => computeMeanOrbitalClass(r.satrec));
        objectTypes = new Uint8Array(satrecs.map(r => classifyObjectType(r.name)));
        self.postMessage({ type: "ready", count: satrecs.length });
        return;
    }

    if (e.data.type === "propagate") {
        const now = e.data.timestamp ? new Date(e.data.timestamp) : new Date();

        const positions    = new Float32Array(satrecs.length * 3);
        const altitudes    = new Float32Array(satrecs.length);
        const classes      = new Uint8Array(satrecs.length);
        const objTypesCopy = new Uint8Array(objectTypes);

        for (let i = 0; i < satrecs.length; i++) {
            const pv = satellite.propagate(satrecs[i].satrec, now);
            if (!pv || !pv.position) {
                positions[i*3] = 0; positions[i*3+1] = 0; positions[i*3+2] = 0;
                altitudes[i] = 0;
                classes[i]   = meanClasses[i];
                continue;
            }
            const p = pv.position;
            // ECI → Three.js y-up remap (same as before — unchanged)
            positions[i*3]   =  p.x / 1000;
            positions[i*3+1] =  p.z / 1000;
            positions[i*3+2] = -p.y / 1000;
            altitudes[i] = Math.sqrt(p.x**2 + p.y**2 + p.z**2) - 6371;
            classes[i]   = meanClasses[i];
        }

        self.postMessage(
            { type: "positions", positions, altitudes, classes, objectTypes: objTypesCopy },
            [positions.buffer, altitudes.buffer, classes.buffer, objTypesCopy.buffer]
        );
    }
};
