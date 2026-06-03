# IOLA Orbit Client — Engineering Notes
## Visual Command Center / Frontend Visualiser

**Status:** Phase 3 command center deployed, spawn pending fix  
**Period:** 2026-05-15 onward  
**Engineers:** Jason Quist (Founder & CEO) · Claude (Chief Research Scientist / Systems Architect)  
**Repository:** iolaresearch/iola-orbit (PUBLIC)  
**Deployed at:** orbit.ikirere.com (Vercel)

---

## Architecture

**Single-file static app.** `index.html` contains all JavaScript. No build step, no npm, no framework. Deploys instantly to Vercel as a static site.

```
client/
  index.html          — Three.js scene + IkirereMesh command center
  propagate.worker.js — Web Worker running satellite.js SGP4 for all 15k satellites
  styles.css          — UI styles
  api/satellites.js   — Vercel serverless proxy → iola-orbit-server.onrender.com/tles
  vercel.json         — outputDirectory: "."  (repo root IS the client root)
```

**Data flow:**
```
CelesTrak TLEs → /api/satellites (Vercel proxy) → propagate.worker.js (satellite.js SGP4)
                                                  → Three.js Points per orbit class

iola-orbit-server.onrender.com → /mesh/spawn → background thread
                               → /mesh/spawn/status (poll) → agent state
                               → /mesh/stream (WebSocket) → real-time steps
```

---

## Environment Variables

`IOLA_ORB_API_URL` must be set in Vercel project settings:
```
IOLA_ORB_API_URL=https://iola-orbit-server.onrender.com
```

The serverless function `api/satellites.js` reads this to proxy TLE requests.

The Three.js frontend detects API base URL at runtime:
```js
const API_BASE = window.location.hostname === "localhost"
    ? "http://localhost:8000"
    : "https://iola-orbit-server.onrender.com";
```

---

## Three.js Scene

**Earth radius:** 6.371 scene units (= 6,371 km at 1:1000 scale)  
**Satellite position scale:** ECI km ÷ 1000 = scene units  
**LEO satellite at 550km altitude:** ~6.921 scene units from origin

**Earth rotation:**
```js
const earthAngle = (Date.now() / 86164100) * Math.PI * 2;  // sidereal day
earth.rotation.y = earthAngle;
```

**Ground station coordinate system:**
```
x =  R·cos(lat)·cos(lon)
y =  R·sin(lat)
z = -R·cos(lat)·sin(lon)
```
Ground stations are `earth.add(dot)` — children of Earth mesh, rotate with it.
Accra: 5.6037°N, -0.1870°W  
Kigali: -1.9415°S, 30.0574°E

---

## Satellite Worker

`propagate.worker.js` accepts:
```js
{ type: "init", raw: "<TLE text>" }  // parse TLEs
{ type: "propagate", timestamp: ms } // propagate to ms (optional, defaults to Date.now())
```

The `timestamp` parameter enables time mode simulation. LIVE mode passes `Date.now()`. PASS mode passes an advancing simulated clock at 60× speed.

---

## IkirereMesh Command Center

### Spawn Flow

1. Click SPAWN FLEET
2. Frontend pings `/health` (warmup, handles cold starts)
3. `POST /mesh/spawn?fleet_size=N&seed=42` — returns `{state: "running"}` immediately
4. Frontend polls `GET /mesh/spawn/status` every 3s
5. When `state === "ready"`, renders agents and opens WebSocket stream

**Known issue:** `env.reset()` takes 90-180s on Render free tier — spawn never completes. Fix required (see Section 41.2 of phase3_engineering_notes.md).

### Time Modes

| Mode | simTimeMs update | Worker timestamp | Speed |
|---|---|---|---|
| LIVE | `= Date.now()` on every tick | current real time | 1× |
| PASS | `+= elapsed × 60` | simulated future time | 60× (90min in 90s) |
| STEP | `+= 60000` per click | +60s per click | manual |

### Agent Rendering

IOLA agents: `THREE.Mesh` with `SphereGeometry(0.18)` and `MeshPhongMaterial({ emissive: color })`.  
Color-coded by operational mode:
```js
IMAGING: 0x00ff88    DOWNLINK: 0x00bbff    YIELD_COVERAGE: 0xffaa00
SAFE_MODE: 0xff4444  IDLE: 0xff3a6e        REQUEST_RELAY: 0xcc88ff
HOLD_POSITION: 0xffffff
```

---

## Known Issues and TODO

### Critical
- **Spawn timeout on Render free tier:** `env.reset()` requires SGP4 precompute for 15,428 sats × 90 steps. Takes 90-180s on 0.1 shared CPU. Fix: pre-warm environment at server startup, cache it, serve cached state on spawn request. See `server/docs/phase3_engineering_notes.md` Section 41.2.

### Medium
- **WebSocket not tested end-to-end:** `/mesh/stream` implemented but never reached in production due to spawn timeout. Needs testing once spawn works.
- **Agent click detection:** raycaster threshold may need tuning for small sphere size (0.18 scene units). Test at various zoom levels.
- **Conjunction alerts:** Not yet overlaid on scene. Phase 2 `/conjunction/high-risk` exists on server, needs periodic polling and red alert marker rendering.

### Minor  
- **Orbit path arcs:** No trajectory line for IOLA agents (just current position). Would improve situational awareness.
- **Contact window cones:** Accra/Kigali visibility cones not visualised. Could draw transparent cylinders when `in_contact_window=true`.
- **Multi-user:** One global spawn state on server. Concurrent users overwrite each other. Fix: session-scoped environments.

---

## Deployment

**Vercel** auto-deploys on push to `main` branch of `iolaresearch/iola-orbit`.

Vercel settings:
- Root Directory: ` ` (empty — repo root is client root)
- Framework: Other
- Output Directory: `.`
- No build command needed (static files)

`vercel.json` in repo root ensures `outputDirectory: "."` is always set.

---

## Security

All external data rendered via `textContent` or DOM construction — no `innerHTML` with API data. Protects against XSS from malicious satellite names in the orbital catalog.

CORS: the Vercel proxy (`api/satellites.js`) handles the TLE fetch. The Three.js frontend fetches from the same Vercel origin via `/api/satellites`.

---

*Signed: Jason Quist (Founder & CEO) · Claude (Chief Research Scientist / Systems Architect)*  
*Last updated: 2026-06-02*

---

## Section 2 — Spawn Pre-Warm Fix (2026-06-02)

**Root cause of 500 errors:** Three bugs found and fixed in sequence:
1. `_spawn_status` dict used before module-level initialization — `NameError`
2. `logging` module not imported — `log` variable undefined, 500 on spawn
3. Render free tier 0.1 CPU: `env.reset()` (15,428 × 90 SGP4 steps) takes 5 minutes

**Solution: pre-warm at startup.** `main.py` runs `_prewarm_mesh()` in a background thread immediately after server starts. Caches `env`, `policy`, `obs` via `set_prewarm()`. Spawn returns `state=ready` in **0.46s** from cache.

**Behavior:**
- Cold start (Render wakes): pre-warm runs ~5 min in background. Server serves other requests meanwhile. `/health` reports `prewarm_ready=false`.
- After pre-warm: `/mesh/spawn` returns `state=ready` instantly. Self-ping every 60s keeps warm.
- On AWS (real CPU): pre-warm completes in ~2 seconds.

**Verified 2026-06-02:** Three LEO agents spawned — TPA-1 (514km), ONEWEB-0227 (1218km), BISONSAT (502km). Spawn in 0.46s.
Note: these were real catalog satellites elevated to agent status. Fixed in Section 3 (2026-06-03) — agents are now IOLA-SAT-1/2/3.

**Frontend polling:** Button shows "WAKING SERVER…" → pings `/health` → "SPAWNING…" → polls `/mesh/spawn/status` every 3s → shows agents when `state=ready`.

---

## Section 3 — Earth Rotation Sync, Agent Smoothing, Arc, Locate (2026-06-03)

### Four issues fixed

**1. Agent identity:** `_initialise_agent_states()` now assigns `name=IOLA-SAT-N`, `norad_id=IOLA-N`. Real catalog satellites are orbital mechanics templates only, not promoted agents. See phase3_engineering_notes Section 43.2.

**2. Earth rotation vs simulation epoch (geographic correctness bug):**
The server now returns `sim_epoch_utc` in every step response — the simulation's current UTC time (`snapshot_utc + step × 60s`). The frontend `animate()` computes GMST from this epoch using the IAU formula:
```
θ_GMST = (280.46061837 + 360.98564736629 × (JD - 2451545.0)) mod 360°
```
Earth now rotates at simulation speed, not wall-clock speed. An agent over Africa at simulation time T appears over Africa on the globe.

**3. Agent position smoothing:**
The server also returns `vx, vy, vz` per agent. Between server steps, `animate()` extrapolates: `pos_display = (x + vx×Δt_sim, y + vy×Δt_sim, z + vz×Δt_sim) / 1000`. No more jumps. Same principle as Phase 1 BUG-005 fix.

**4. Orbital arc + LOCATE button:**
- Clicking an agent sphere calls `showArc(idx)` — draws a `THREE.Line` of 91 points tracing 90×60s linear extrapolation steps. Color `#00ffaa`, 35% opacity.
- Each agent card has a LOCATE button: pans `OrbitControls.target` to the agent and shows its arc.
- Known limitation: arc is linear extrapolation, not true Keplerian ellipse. Visual error <15km over 90min. Phase 4: replace with Keplerian JS propagator.

### API additions (server)
- `_agent_to_dict()` adds `vx, vy, vz`
- `_env_state()` adds `sim_epoch_utc`
