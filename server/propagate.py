"""
IKIRERE ORBITAL LABS AFRICA — PHASE 1
Orbital Propagation Engine

=======================================================================
PURPOSE
=======================================================================
This file is the mathematical foundation of the IOLA platform.
It answers one question: "Where are the satellites right now?"

Every downstream system — conjunction assessment (Phase 2), IkirereMesh
coordination (Phase 3), and the API consumed by operators and researchers
— depends on the orbital state produced here.

This file must never be deleted, replaced by a frontend library, or
treated as infrastructure glue. It is the beginning of IOLA's
proprietary mathematical stack.

=======================================================================
PHASE 1 SCOPE (from docs/phase1)
=======================================================================
Core Direction:
  Build the foundational orbital state engine capable of ingesting,
  propagating, synchronizing, and visualizing real-world satellite
  behavior deterministically.

Mathematical / Physics Foundations implemented here:
  - Cartesian orbital coordinate systems (ECI — Earth-Centered Inertial)
  - Earth-centered inertial positioning (x, y, z in km)
  - Relative velocity vectors (vx, vy, vz in km/s)
  - Orbital state propagation (SGP4 via sgp4 library)
  - TLE orbital element interpretation
  - Temporal state evolution (epoch → current UTC)
  - Orbital shell classification (LEO / MEO / GEO)
  - Sunlight / eclipse determination (conical shadow model)
  - Atmospheric drag coefficient extraction (B*)

=======================================================================
COORDINATE SYSTEM
=======================================================================
All positions and velocities are in the ECI (Earth-Centered Inertial)
frame, with origin at Earth's center of mass.

  x-axis: points toward the vernal equinox
  y-axis: 90° east in the equatorial plane
  z-axis: points toward the North Pole

Units:
  position  — km
  velocity  — km/s
  altitude  — km above mean Earth surface (EARTH_RADIUS_KM = 6371 km)

=======================================================================
NOVELTY BOUNDARY
=======================================================================
SGP4 propagation uses the sgp4 library (standard, not novel).
The conical shadow model (_is_sunlit) and the Sun position almanac
(_sun_position_eci) are IOLA's own implementations — no external
library, derived from first principles using Vallado's formulation.
Phase 2 and Phase 3 introduce IOLA's novel algorithms.

=======================================================================
OUTPUT CONTRACT (every satellite record)
=======================================================================
  name           — satellite name as given in TLE catalog
  norad_id       — NORAD catalog number (5-digit string)
  epoch          — ISO 8601 UTC time of TLE measurement
  x, y, z        — ECI position in km
  vx, vy, vz     — ECI velocity in km/s
  speed_km_s     — scalar orbital speed (magnitude of velocity vector)
  altitude_km    — altitude above Earth surface in km
  orbital_class  — LEO / MEO / GEO
  bstar          — atmospheric drag coefficient (B*) from TLE
  sunlit         — True if satellite is in direct sunlight, False if in shadow
"""

import math
from sgp4.api import Satrec, jday
from datetime import datetime, timezone, timedelta
from state import satellite_cache

# -----------------------------------------------------------------------
# Physical constants
# -----------------------------------------------------------------------
EARTH_RADIUS_KM = 6371.0   # Mean Earth radius, km

# -----------------------------------------------------------------------
# Orbital shell classification boundaries (km altitude)
# LEO: Low Earth Orbit     < 2,000 km
# MEO: Medium Earth Orbit  2,000 – 35,786 km
# GEO: Geostationary Orbit ≥ 35,786 km
# -----------------------------------------------------------------------
LEO_MAX_ALTITUDE_KM = 2000.0
MEO_MAX_ALTITUDE_KM = 35786.0

# -----------------------------------------------------------------------
# Minimum acceptable propagation output.
# If a run produces fewer satellites than this, the existing cache is
# preserved. Prevents partial or corrupt propagation from replacing
# valid operational state.
# -----------------------------------------------------------------------
MIN_VALID_SATELLITE_COUNT = 1000


def _sun_position_eci(julian_date, julian_date_fraction):
    """
    Compute the Sun's position vector in ECI coordinates (km).

    Uses the low-precision solar almanac formulation from:
      Vallado, D.A., "Fundamentals of Astrodynamics and Applications",
      4th edition, Algorithm 29.

    Accuracy: ~0.01 degrees in ecliptic longitude.
    No external library required — computed from Julian date alone.

    Parameters
    ----------
    julian_date          : float — integer part of Julian date
    julian_date_fraction : float — fractional part of Julian date

    Returns
    -------
    tuple (sun_x_km, sun_y_km, sun_z_km) in ECI frame
    """
    # Julian centuries elapsed since J2000.0 epoch (2000-Jan-1.5 TT)
    julian_centuries_from_j2000 = (julian_date + julian_date_fraction - 2451545.0) / 36525.0

    # Mean longitude of the Sun (degrees → radians)
    mean_longitude_rad = math.radians(
        280.460 + 36000.771 * julian_centuries_from_j2000
    )

    # Mean anomaly of the Sun (degrees → radians)
    mean_anomaly_rad = math.radians(
        357.528 + 35999.050 * julian_centuries_from_j2000
    )

    # Ecliptic longitude: corrects mean longitude for orbital eccentricity
    # via the equation of center (first two harmonic terms)
    ecliptic_longitude_rad = mean_longitude_rad + math.radians(
        1.915 * math.sin(mean_anomaly_rad)
        + 0.020 * math.sin(2.0 * mean_anomaly_rad)
    )

    # Obliquity of the ecliptic: tilt of Earth's equator relative to
    # the ecliptic plane, slowly decreasing with time
    obliquity_of_ecliptic_rad = math.radians(
        23.439 - 0.0130 * julian_centuries_from_j2000
    )

    # Sun–Earth distance in astronomical units, then converted to km
    sun_distance_astronomical_units = (
        1.000140
        - 0.016708 * math.cos(mean_anomaly_rad)
        - 0.000141 * math.cos(2.0 * mean_anomaly_rad)
    )
    sun_distance_km = sun_distance_astronomical_units * 1.495978707e8

    # Project onto ECI axes using ecliptic coordinates
    sun_x_km = sun_distance_km * math.cos(ecliptic_longitude_rad)
    sun_y_km = sun_distance_km * math.cos(obliquity_of_ecliptic_rad) * math.sin(ecliptic_longitude_rad)
    sun_z_km = sun_distance_km * math.sin(obliquity_of_ecliptic_rad) * math.sin(ecliptic_longitude_rad)

    return (sun_x_km, sun_y_km, sun_z_km)


def _is_sunlit(satellite_position_km, sun_position_eci_km):
    """
    Determine whether a satellite is in direct sunlight or Earth's shadow.

    Uses a conical umbra shadow model. A satellite is in shadow when its
    ECI position vector falls inside the cone formed by Earth's shadow
    projected opposite the Sun direction.

    The cylindrical approximation (simpler) is not used here because it
    misclassifies satellites in the penumbra transition zone, which would
    corrupt power-availability training data fed to IkirereMesh in Phase 3.

    Parameters
    ----------
    satellite_position_km   : tuple (x, y, z) — satellite ECI position in km
    sun_position_eci_km     : tuple (x, y, z) — Sun ECI position in km

    Returns
    -------
    bool — True if sunlit, False if in shadow
    """
    sat_x, sat_y, sat_z = satellite_position_km
    sun_x, sun_y, sun_z = sun_position_eci_km

    # Normalise Sun position vector to unit vector (direction only)
    sun_vector_magnitude_km = math.sqrt(sun_x**2 + sun_y**2 + sun_z**2)
    sun_unit_vector = (
        sun_x / sun_vector_magnitude_km,
        sun_y / sun_vector_magnitude_km,
        sun_z / sun_vector_magnitude_km,
    )

    # Scalar projection of satellite position onto the Sun direction axis.
    # Positive: satellite is on the Sun-facing hemisphere — always sunlit.
    # Negative: satellite is on the anti-Sun hemisphere — may be in shadow.
    projection_onto_sun_axis = (
        sat_x * sun_unit_vector[0]
        + sat_y * sun_unit_vector[1]
        + sat_z * sun_unit_vector[2]
    )

    if projection_onto_sun_axis > 0:
        return True

    # Perpendicular distance squared from satellite to the Sun-Earth axis.
    # If this exceeds Earth's radius squared, the satellite is outside the
    # shadow cone and remains sunlit despite being on the anti-Sun side.
    perpendicular_distance_squared = (
        (sat_x**2 + sat_y**2 + sat_z**2) - projection_onto_sun_axis**2
    )

    return perpendicular_distance_squared > EARTH_RADIUS_KM**2


def _epoch_to_iso(tle_epoch_year, tle_epoch_days):
    """
    Convert TLE epoch (two-digit year + day-of-year fraction) to ISO 8601 UTC.

    TLE epoch year convention:
      57–99 → 1957–1999 (Sputnik era onward)
      00–56 → 2000–2056

    Parameters
    ----------
    tle_epoch_year : float — two-digit year from TLE
    tle_epoch_days : float — day of year with fractional day

    Returns
    -------
    str — ISO 8601 UTC datetime string
    """
    full_year = int(tle_epoch_year) + (2000 if tle_epoch_year < 57 else 1900)
    epoch_datetime = (
        datetime(full_year, 1, 1, tzinfo=timezone.utc)
        + timedelta(days=tle_epoch_days - 1)
    )
    return epoch_datetime.isoformat()


def propagate_satellites():
    """
    Propagate all satellites in the TLE catalog to the current UTC time.

    Reads active.tle, applies SGP4 to every satellite, computes derived
    orbital state, and atomically replaces the satellite cache if the
    result passes the minimum count threshold.

    Called:
      - Once synchronously at startup (before threads start)
      - Every 15 seconds by the propagation background thread
      - Immediately after every successful TLE refresh
    """
    with open("../data/active.tle", "r") as tle_file:
        tle_lines = [line for line in tle_file.readlines() if line.strip()]

    current_utc = datetime.now(timezone.utc)
    julian_date, julian_date_fraction = jday(
        current_utc.year, current_utc.month, current_utc.day,
        current_utc.hour, current_utc.minute, current_utc.second
    )

    # Compute Sun position once for this propagation epoch.
    # Used for all sunlit/shadow determinations in this batch.
    sun_position_eci = _sun_position_eci(julian_date, julian_date_fraction)

    propagated_satellites = []

    for index in range(0, len(tle_lines) - 2, 3):
        tle_line1 = tle_lines[index + 1].strip()
        tle_line2 = tle_lines[index + 2].strip()
        norad_id  = tle_line1[2:7].strip()

        try:
            satrec = Satrec.twoline2rv(tle_line1, tle_line2)
            sgp4_error, position_km, velocity_km_s = satrec.sgp4(
                julian_date, julian_date_fraction
            )

            if sgp4_error != 0:
                print(f"SGP4 error code {sgp4_error} for NORAD {norad_id} — skipped")
                continue

            orbital_radius_km = math.sqrt(
                position_km[0]**2 + position_km[1]**2 + position_km[2]**2
            )
            altitude_km = orbital_radius_km - EARTH_RADIUS_KM
            speed_km_s  = math.sqrt(
                velocity_km_s[0]**2 + velocity_km_s[1]**2 + velocity_km_s[2]**2
            )

            if altitude_km < LEO_MAX_ALTITUDE_KM:
                orbital_class = "LEO"
            elif altitude_km < MEO_MAX_ALTITUDE_KM:
                orbital_class = "MEO"
            else:
                orbital_class = "GEO"

            propagated_satellites.append({
                "name":          tle_lines[index].strip(),
                "norad_id":      norad_id,
                "epoch":         _epoch_to_iso(satrec.epochyr, satrec.epochdays),
                "x":             position_km[0],
                "y":             position_km[1],
                "z":             position_km[2],
                "vx":            velocity_km_s[0],
                "vy":            velocity_km_s[1],
                "vz":            velocity_km_s[2],
                "speed_km_s":    speed_km_s,
                "altitude_km":   altitude_km,
                "orbital_class": orbital_class,
                "bstar":         satrec.bstar,
                "sunlit":        _is_sunlit(position_km, sun_position_eci),
            })

        except Exception as error:
            print(f"Propagation failed for NORAD {norad_id}: {error}")
            continue

    if len(propagated_satellites) < MIN_VALID_SATELLITE_COUNT:
        print(
            f"WARNING: propagation yielded {len(propagated_satellites)} satellites "
            f"(minimum required: {MIN_VALID_SATELLITE_COUNT}). "
            f"Keeping existing cache — state unchanged."
        )
        return

    satellite_cache[:] = propagated_satellites
    print(
        f"Propagation complete: {len(propagated_satellites)} satellites "
        f"at {current_utc.isoformat()}"
    )
