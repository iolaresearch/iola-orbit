importScripts("https://cdn.jsdelivr.net/npm/satellite.js@4.1.3/dist/satellite.min.js");

let satrecs    = [];
let meanClasses = [];   // stable orbital class from mean semi-major axis, not instantaneous altitude
let objectTypes = [];   // 0=PAYLOAD, 1=DEBRIS, 2=ROCKET BODY

// Object type constants
const OBJ_PAYLOAD = 0;
const OBJ_DEBRIS  = 1;
const OBJ_RB      = 2;

// Orbital class constants (same as server-side engine.py)
const CLS_LEO = 0;
const CLS_MEO = 1;
const CLS_GEO = 2;

// Physical constants for mean semi-major axis computation
const GM_KM3S2 = 398600.4418;   // Earth gravitational parameter (km³/s²)
const R_EARTH  = 6371.0;        // Earth mean radius (km)

function parseTLEs(raw) {
    // Handles both 3LE (name + TLE1 + TLE2, from CelesTrak active payloads)
    // and 2LE (TLE1 + TLE2 only, from Space-Track debris and rocket bodies).
    // The catalog combines both because the debris catalog uses 2LE format.
    const lines = raw.split("\n").map(l => l.trim()).filter(Boolean);
    const records = [];
    let i = 0;
    while (i < lines.length - 1) {
        let name, line1, line2;
        if (lines[i].startsWith("1 ")) {
            // 2LE format: this line IS TLE line 1, next is TLE line 2
            name  = lines[i].substring(2, 7).trim();  // NORAD ID as name
            line1 = lines[i];
            line2 = lines[i + 1];
            i += 2;
        } else {
            // 3LE format: name line followed by the two TLE data lines
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
    // Use mean motion (rad/min) to compute mean semi-major axis and stable orbital class.
    // This avoids HEO debris flickering between LEO and GEO as it moves along its
    // eccentric orbit — a debris object with apogee at 45,000 km and perigee at 500 km
    // has a mean semi-major axis in MEO, not GEO.
    const n_rad_min = satrec.no;  // mean motion (rad/min) from TLE
    if (!n_rad_min || n_rad_min <= 0) return CLS_LEO;
    const n_rad_s   = n_rad_min / 60.0;
    const a_km      = Math.cbrt(GM_KM3S2 / (n_rad_s * n_rad_s));
    const alt_km    = a_km - R_EARTH;
    if (alt_km < 2000)  return CLS_LEO;
    if (alt_km < 35786) return CLS_MEO;
    return CLS_GEO;
}

function classifyObjectType(name) {
    // Mirror the exact classification logic from propagate/engine.py object_type field.
    const n = name.toUpperCase().trim();
    if (n.endsWith(" DEB") || n.endsWith("DEB") || n.includes("DEBRIS")) {
        return OBJ_DEBRIS;
    }
    if (n.includes(" R/B") || n.endsWith("R/B") || n.includes("ROCKET")) {
        return OBJ_RB;
    }
    // Numeric-only names are Space-Track 2LE entries without a name line — predominantly debris
    if (/^\d+$/.test(n)) {
        return OBJ_DEBRIS;
    }
    return OBJ_PAYLOAD;
}

self.onmessage = (e) => {
    if (e.data.type === "init") {
        satrecs = parseTLEs(e.data.raw);

        // Pre-compute stable orbital class and object type for every object.
        // These are computed once at init and reused on every propagation frame.
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
        const objTypesCopy = new Uint8Array(objectTypes);   // transfer-safe copy

        for (let i = 0; i < satrecs.length; i++) {
            const pv = satellite.propagate(satrecs[i].satrec, now);
            if (!pv || !pv.position) {
                // Failed propagation (decayed or invalid TLE) — park at origin
                positions[i * 3] = 0; positions[i * 3 + 1] = 0; positions[i * 3 + 2] = 0;
                altitudes[i] = 0;
                classes[i]   = meanClasses[i];
                continue;
            }
            const p = pv.position;
            positions[i * 3]     = p.x / 1000;
            positions[i * 3 + 1] = p.y / 1000;
            positions[i * 3 + 2] = p.z / 1000;

            // Instantaneous altitude for the density bars and inspector display
            altitudes[i] = Math.sqrt(p.x**2 + p.y**2 + p.z**2) - 6371;

            // Stable orbital class from mean semi-major axis (not instantaneous altitude).
            // Prevents HEO debris from flickering between LEO/GEO as it orbits.
            classes[i] = meanClasses[i];
        }

        self.postMessage(
            { type: "positions", positions, altitudes, classes, objectTypes: objTypesCopy },
            [positions.buffer, altitudes.buffer, classes.buffer, objTypesCopy.buffer]
        );
    }
};
