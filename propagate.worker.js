importScripts("https://cdn.jsdelivr.net/npm/satellite.js@4.1.3/dist/satellite.min.js");

let satrecs = [];

function parseTLEs(raw) {
    // Handles both 3LE (name + line1 + line2, from CelesTrak active payloads)
    // and 2LE (line1 + line2, from Space-Track debris and rocket bodies).
    // The catalog combines both formats since the debris fetch returns 2LE.
    const lines = raw.split("\n").map(l => l.trim()).filter(Boolean);
    const records = [];
    let i = 0;
    while (i < lines.length - 1) {
        let name, line1, line2;
        if (lines[i].startsWith("1 ")) {
            // 2LE format: current line is TLE line 1, next is line 2
            name  = lines[i].substring(2, 7).trim();  // use NORAD ID as name
            line1 = lines[i];
            line2 = lines[i + 1];
            i += 2;
        } else {
            // 3LE format: current line is name, next two are TLE lines
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

self.onmessage = (e) => {
    if (e.data.type === "init") {
        satrecs = parseTLEs(e.data.raw);
        self.postMessage({ type: "ready", count: satrecs.length });
        return;
    }

    if (e.data.type === "propagate") {
        // Accept a simulated timestamp (ms) so time modes work for all satellites.
        // Falls back to Date.now() for realtime mode.
        const now = e.data.timestamp ? new Date(e.data.timestamp) : new Date();

        const positions = new Float32Array(satrecs.length * 3);
        const altitudes = new Float32Array(satrecs.length);
        const classes   = new Uint8Array(satrecs.length);

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
