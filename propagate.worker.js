importScripts("https://cdn.jsdelivr.net/npm/satellite.js@4.1.3/dist/satellite.min.js");

let satrecs     = [];
let meanClasses = [];
let objectTypes = [];

// Object type constants
const OBJ_PAYLOAD = 0;
const OBJ_DEBRIS  = 1;
const OBJ_RB      = 2;

// Orbital class constants — 6 regimes (must match LAYER_* arrays in index.html)
const CLS_VLEO      = 0;   // Very Low Earth Orbit: 160–450 km
const CLS_LEO       = 1;   // Low Earth Orbit: 450–2,000 km
const CLS_MEO       = 2;   // Medium Earth Orbit: 2,000–35,486 km, ecc < 0.25
const CLS_GEO       = 3;   // Geostationary: 35,486–36,100 km band
const CLS_HEO       = 4;   // Highly Elliptical Orbit: eccentricity ≥ 0.25
const CLS_GRAVEYARD = 5;   // Disposal/Graveyard: > 36,100 km, ecc < 0.25

// Physical constants
const GM_KM3S2    = 398600.4418;
const R_EARTH     = 6371.0;
const HEO_ECC_MIN = 0.25;    // eccentricity threshold for HEO classification
const GEO_LOW_KM  = 35486.0; // GEO band lower boundary (35,786 - 300)
const GEO_HIGH_KM = 36086.0; // GEO band upper boundary (35,786 + 300)
const MEO_MAX_KM  = GEO_LOW_KM;
const VLEO_MAX_KM = 450.0;
const LEO_MAX_KM  = 2000.0;

function parseTLEs(raw) {
    // Handles both 3LE (name + TLE1 + TLE2, CelesTrak active payloads)
    // and 2LE (TLE1 + TLE2, Space-Track debris/rocket bodies).
    const lines = raw.split("\n").map(l => l.trim()).filter(Boolean);
    const records = [];
    let i = 0;
    while (i < lines.length - 1) {
        let name, line1, line2;
        if (lines[i].startsWith("1 ")) {
            name  = lines[i].substring(2, 7).trim();
            line1 = lines[i];
            line2 = lines[i + 1];
            i += 2;
        } else {
            name  = lines[i];
            line1 = lines[i + 1];
            line2 = lines[i + 2];
            i += 3;
        }
        if (!line1 || !line2) break;
        if (!line1.startsWith("1 ") || !line2.startsWith("2 ")) continue;
        try {
            const satrec = satellite.twoline2satrec(line1, line2);
            records.push({ name, norad_id: line1.substring(2, 7).trim(), satrec });
        } catch (_) {}
    }
    return records;
}

function computeMeanOrbitalClass(satrec) {
    // Classify by mean semi-major axis altitude AND eccentricity.
    //
    // Why mean SMA, not instantaneous altitude:
    //   An HEO satellite (e.g. Molniya, Tundra) has a mean SMA in MEO range
    //   but instantaneous positions ranging from LEO perigee to beyond-GEO apogee.
    //   Using instantaneous altitude causes the dot to appear far above GEO while
    //   colored MEO-blue — visually inconsistent. Using mean SMA + eccentricity
    //   gives a stable, physically meaningful class.
    //
    // Why eccentricity threshold (HEO detection):
    //   Molniya orbits: ecc ~0.74, SMA ~26,560 km (would be MEO without ecc check)
    //   Tundra orbits:  ecc ~0.27, SMA ~42,164 km (would be GEO without ecc check)
    //   ecc ≥ 0.25 correctly captures both.

    const n_rad_min = satrec.no;
    if (!n_rad_min || n_rad_min <= 0) return CLS_LEO;

    const ecc     = satrec.ecco || 0;
    const n_rad_s = n_rad_min / 60.0;
    const a_km    = Math.cbrt(GM_KM3S2 / (n_rad_s * n_rad_s));
    const alt_km  = a_km - R_EARTH;

    // HEO takes priority — checked before altitude to correctly capture Molniya/Tundra
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
    if (/^\d+$/.test(n)) return OBJ_DEBRIS;  // numeric-only = Space-Track 2LE debris
    return OBJ_PAYLOAD;
}

self.onmessage = (e) => {
    if (e.data.type === "init") {
        satrecs = parseTLEs(e.data.raw);
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
            positions[i*3]     = p.x / 1000;
            positions[i*3+1]   = p.y / 1000;
            positions[i*3+2]   = p.z / 1000;
            altitudes[i] = Math.sqrt(p.x**2 + p.y**2 + p.z**2) - 6371;
            classes[i]   = meanClasses[i];
        }

        self.postMessage(
            { type: "positions", positions, altitudes, classes, objectTypes: objTypesCopy },
            [positions.buffer, altitudes.buffer, classes.buffer, objTypesCopy.buffer]
        );
    }
};
