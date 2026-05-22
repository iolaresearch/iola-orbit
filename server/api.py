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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from propagate import propagate_satellites

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
