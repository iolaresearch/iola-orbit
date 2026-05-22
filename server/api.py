"""
IKIRERE ORBITAL LABS AFRICA — PHASE 1
Operational Telemetry API

=======================================================================
PURPOSE
=======================================================================
Exposes the Phase 1 orbital state to two distinct consumers:

  GET /tles       → Raw TLE catalog (plain text)
                    Consumed by the frontend visualization layer.
                    The client runs satellite.js SGP4 locally for
                    exact real-time display positions.

  GET /satellites → Propagated orbital state (JSON)
                    Consumed by research tools, Phase 2 conjunction
                    engine, and future API customers.
                    Positions are accurate to the last propagation
                    cycle (every 15 seconds).

=======================================================================
CORS POLICY
=======================================================================
Restricted to known origins only. No wildcard. Adding a new origin
requires an explicit entry here — not a configuration change.

=======================================================================
ALLOWED METHODS
=======================================================================
GET only. This API exposes read-only orbital state.
No mutation endpoints exist in Phase 1.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
import state

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
    Return the current propagated orbital state for all satellites.
    Includes propagated_at — the UTC timestamp of the last propagation
    run — so consumers can epoch-match their own reference computations.
    """
    return {
        "propagated_at": state.last_propagated_at,
        "satellites":    state.satellite_cache,
    }
