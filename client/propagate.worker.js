importScripts("https://cdn.jsdelivr.net/npm/satellite.js@4.1.3/dist/satellite.min.js");

let satrecs = [];

function parseTLEs(raw) {
    const lines = raw.split("\n").map(l => l.trim()).filter(Boolean);
    const records = [];
    for (let i = 0; i < lines.length - 2; i += 3) {
        if (lines[i].startsWith("1 ") || lines[i].startsWith("2 ")) continue;
        try {
            const satrec = satellite.twoline2satrec(lines[i + 1], lines[i + 2]);
            records.push({ name: lines[i], norad_id: lines[i + 1].substring(2, 7).trim(), satrec });
        } catch (_) {}
    }
    return records;
}

self.onmessage = (e) => {
    if (e.data.type === "init") {
        satrecs = parseTLEs(e.data.raw);
        self.postMessage({ type: "ready", count: satrecs.length });
        return;
    }

    if (e.data.type === "propagate") {
        const now = new Date();
        const positions = new Float32Array(satrecs.length * 3);
        const altitudes = new Float32Array(satrecs.length);
        const classes = new Uint8Array(satrecs.length);

        for (let i = 0; i < satrecs.length; i++) {
            const pv = satellite.propagate(satrecs[i].satrec, now);
            if (!pv.position) {
                positions[i * 3] = 0; positions[i * 3 + 1] = 0; positions[i * 3 + 2] = 0;
                altitudes[i] = 0; classes[i] = 0;
                continue;
            }
            const p = pv.position;
            positions[i * 3]     = p.x / 1000;
            positions[i * 3 + 1] = p.y / 1000;
            positions[i * 3 + 2] = p.z / 1000;

            const alt = Math.sqrt(p.x**2 + p.y**2 + p.z**2) - 6371;
            altitudes[i] = alt;
            classes[i] = alt < 2000 ? 0 : alt < 35786 ? 1 : 2;
        }

        self.postMessage(
            { type: "positions", positions, altitudes, classes },
            [positions.buffer, altitudes.buffer, classes.buffer]
        );
    }
};
