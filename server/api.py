"""
IKIRERE ORBITAL LABS AFRICA — PHASE 1
Operational Telemetry API

=======================================================================
PURPOSE
=======================================================================
Exposes the Phase 1 orbital state to two distinct consumers:

  GET /tles       -> Raw TLE catalog (plain text)
                    Consumed by the frontend visualization layer.
                    The client runs satellite.js SGP4 locally for
                    exact real-time display positions.

  GET /satellites -> Propagated orbital state (JSON)
                    Consumed by research tools, Phase 2 conjunction
                    engine, and future API customers.
                    Positions are computed on-demand for the exact
                    UTC moment of the request. Zero staleness.

=======================================================================
ON-DEMAND PROPAGATION
=======================================================================
propagate_satellites() is called on every GET /satellites request.
It evaluates all 15,000+ Satrec objects against datetime.now().
Measured cost: ~9ms on Render free tier.

This replaced the 15-second background cache cycle which introduced:
  - Up to 15s + network latency of position staleness
  - BUG-012: empty-cache window between clear() and extend()
  - Test 1 timing artifact requiring propagated_at workaround

=======================================================================
CORS POLICY
=======================================================================
Restricted to known origins only. No wildcard. New origins require
an explicit code change, not a configuration change.

=======================================================================
ALLOWED METHODS
=======================================================================
GET only. This API exposes read-only orbital state.
No mutation endpoints exist in Phase 1.
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from propagate import propagate_satellites
from conjunction import screen_catalog, find_closest_approach, generate_cdm
from conjunction import compute_composite_risk_score, distance_between_satellites
import state
from datetime import datetime, timezone

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://orbit.ikirere.com",
        "https://iola-orbit.vercel.app",
        "http://localhost:8000",
    ],
    allow_methods=["GET"],
    allow_headers=["*"]
)

TLE_FILE_PATH = "../data/active.tle"


@app.get("/tles", response_class=PlainTextResponse)
def get_raw_tle_catalog():
    """
    Return the full active TLE catalog as plain text.
    Consumed by the frontend Web Worker (satellite.js SGP4).
    """
    with open(TLE_FILE_PATH, "r") as tle_file:
        return tle_file.read()


@app.get("/satellites")
def get_propagated_satellite_state():
    """
    Propagate all satellites to datetime.now() and return the result.
    propagated_at in the response is the exact UTC second of this call.
    """
    return propagate_satellites()


# ===========================================================================
# PHASE 2 — CONJUNCTION INTELLIGENCE ENDPOINTS
#
# HUMAN-IN-THE-LOOP BOUNDARY: these endpoints produce advisory intelligence.
# They do not issue commands. They do not execute maneuvers.
# Every output is for human review. The operator decides.
# ===========================================================================

@app.get("/conjunction/screen")
def screen_for_conjunctions(
    threshold_km:    float = Query(default=50.0,   description="Separation threshold to trigger TCA scan (km)"),
    window_hours:    float = Query(default=24.0,   description="Look-ahead window for TCA computation (hours)"),
):
    """
    Screen the full catalog for conjunction candidates.

    Runs the three-stage pipeline:
      1. Altitude pre-filter (O(n))
      2. Current separation filter
      3. Full TCA computation + risk scoring for survivors

    Returns all detected conjunctions sorted by composite risk score.
    This is a research-grade operation — expect 30-120 seconds for
    15,000 satellites at default threshold.
    """
    satellites      = propagate_satellites()["satellites"]
    window_seconds  = int(window_hours * 3600)
    return screen_catalog(satellites, threshold_km=threshold_km,
                          scan_window_seconds=window_seconds)


@app.get("/conjunction/pair/{norad_id_1}/{norad_id_2}")
def get_pair_conjunction(norad_id_1: str, norad_id_2: str,
                         window_hours: float = Query(default=24.0)):
    """
    Full conjunction report for a specific satellite pair.
    Returns TCA, miss distance, risk score, and CDM.
    """
    result     = propagate_satellites()
    satellites = result["satellites"]
    epoch      = datetime.now(timezone.utc)

    sat_a = next((s for s in satellites if s["norad_id"] == norad_id_1), None)
    sat_b = next((s for s in satellites if s["norad_id"] == norad_id_2), None)

    if sat_a is None:
        return {"error": f"NORAD {norad_id_1} not found in catalog"}
    if sat_b is None:
        return {"error": f"NORAD {norad_id_2} not found in catalog"}

    approach = find_closest_approach(sat_a, sat_b,
                                     scan_duration_seconds=int(window_hours * 3600))
    risk     = compute_composite_risk_score(sat_a, sat_b, approach, epoch,
                                            all_satellites=satellites)
    cdm      = generate_cdm(sat_a, sat_b, approach, risk, epoch)

    return {
        "queried_at":            epoch.isoformat(),
        "object_1":              {"norad_id": norad_id_1, "name": sat_a.get("name")},
        "object_2":              {"norad_id": norad_id_2, "name": sat_b.get("name")},
        "current_separation_km": round(distance_between_satellites(sat_a, sat_b), 3),
        "approach":              approach,
        "risk":                  risk,
        "cdm":                   cdm,
    }


@app.get("/conjunction/high-risk")
def get_high_risk_conjunctions(
    threshold_km: float = Query(default=10.0,  description="Miss distance threshold (km)"),
    window_hours: float = Query(default=24.0,  description="Look-ahead window (hours)"),
):
    """
    Return only conjunctions with composite_risk_score > 0.7.
    Tighter threshold_km and faster response than full screen.
    """
    satellites     = propagate_satellites()["satellites"]
    window_seconds = int(window_hours * 3600)
    full_screen    = screen_catalog(satellites, threshold_km=threshold_km,
                                    scan_window_seconds=window_seconds)

    high_risk_events = [
        event for event in full_screen["conjunctions"]
        if event["risk"]["composite_score"] > 0.7
    ]

    return {
        "screened_at":     full_screen["screened_at"],
        "high_risk_count": len(high_risk_events),
        "conjunctions":    high_risk_events,
    }
