"""
IKIRERE ORBITAL LABS AFRICA — PHASE 2
Orbital Intelligence Infrastructure

=======================================================================
PURPOSE
=======================================================================
This file answers the questions Phase 1 cannot:

  "Will these satellites collide?"
  "When can I talk to my satellite from the ground?"
  "How long before this orbit decays?"
  "Which satellites have overlapping coverage right now?"

Phase 1 (propagate.py) answers: "Where are the satellites right now?"
Phase 2 (this file) answers:    "What is their orbital relationship?"
Phase 3 (ikirere_mesh.py) will answer: "What should they do about it?"

=======================================================================
PHASE 2 SCOPE (from docs/phase2)
=======================================================================
  - Conjunction assessment (closest approach, TCA, miss distance)
  - Risk scoring (composite score, collision probability)
  - Eclipse and sunlight cycle modelling
  - Coverage footprint estimation
  - Communication window prediction
  - Line-of-sight determination
  - Orbital decay estimation
  - Fleet state awareness
  - Conjunction Data Message (CDM) generation
  - Maneuver recommendations
  - Mission planning primitives

=======================================================================
IMPLEMENTATION PHILOSOPHY
=======================================================================
First-principles implementation. No orbital mechanics abstraction
libraries. All mathematics derived directly from physical definitions
using pure Python. No numpy. Readable by any physicist or engineer
without knowing Python idioms.

Naming: every variable and function name reads as plain English.
No single letters. No abbreviations. If you cannot read it aloud,
rename it. Senior aerospace engineers will read this code.

=======================================================================
NOVELTY BOUNDARY
=======================================================================
The propagation and vector math are standard (Keplerian two-body
problem, well-published). The novel components are:
  - compute_composite_risk_score()   — IOLA's weighted risk formula
  - compute_collision_probability()  — IOLA's Gaussian approximation
  - generate_conjunction_data_message() — IOLA's CDM schema
These are Phase 2's IP contribution and the precursor to Phase 3.

=======================================================================
INPUTS / OUTPUTS
=======================================================================
Inputs  : ECI state vectors { x, y, z km | vx, vy, vz km/s }
          as produced by Phase 1 propagate.py / GET /satellites

Outputs : conjunction data, eclipse windows, coverage footprints,
          communication windows, decay estimates, fleet risk scores,
          maneuver recommendations, mission planning primitives.

Paper target: Deep Learning Indaba 2026 / IEEE Aerospace
=======================================================================
"""

import math
from datetime import datetime, timedelta, timezone


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

EARTH_GRAVITATIONAL_PARAMETER    = 398600.4418   # km³/s²
EARTH_MEAN_RADIUS_KM             = 6371.0        # km
EARTH_J2_OBLATENESS              = 1.08263e-3    # dimensionless
EARTH_ROTATION_RATE_RAD_PER_SEC  = 7.2921150e-5  # rad/s
ONE_ASTRONOMICAL_UNIT_KM         = 149_597_870.7 # km
EARTH_AXIAL_TILT_RADIANS         = math.radians(23.439281)

# Piecewise exponential atmosphere: (base altitude km, base density kg/m³, scale height km)
ATMOSPHERE_LAYERS = [
    (   0, 1.225,      8.44),
    (  25, 3.899e-2,   6.49),
    (  50, 1.027e-3,   7.91),
    ( 100, 5.604e-7,   8.00),
    ( 200, 2.541e-10, 11.51),
    ( 300, 1.916e-11, 17.65),
    ( 400, 2.803e-12, 21.55),
    ( 500, 5.215e-13, 26.30),
    ( 600, 8.770e-14, 33.90),
    ( 700, 3.614e-14, 53.30),
    ( 800, 1.963e-14, 53.30),
    ( 900, 5.759e-15, 58.50),
    (1000, 3.561e-15, 268.0),
]

POSITION_UNCERTAINTY_KM          = 1.0   # 1-sigma combined position uncertainty

CONJUNCTION_RISK_CRITICAL_KM     =  1.0  # TCA distance thresholds
CONJUNCTION_RISK_HIGH_KM         =  5.0
CONJUNCTION_RISK_MODERATE_KM     = 20.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. VECTOR MATH — pure Python, no numpy
# ═══════════════════════════════════════════════════════════════════════════════

def add_vectors(first_vector, second_vector):
    return (
        first_vector[0] + second_vector[0],
        first_vector[1] + second_vector[1],
        first_vector[2] + second_vector[2],
    )

def subtract_vectors(first_vector, second_vector):
    return (
        first_vector[0] - second_vector[0],
        first_vector[1] - second_vector[1],
        first_vector[2] - second_vector[2],
    )

def scale_vector(vector, scalar):
    return (vector[0] * scalar, vector[1] * scalar, vector[2] * scalar)

def dot_product(first_vector, second_vector):
    return (
        first_vector[0] * second_vector[0] +
        first_vector[1] * second_vector[1] +
        first_vector[2] * second_vector[2]
    )

def cross_product(first_vector, second_vector):
    return (
        first_vector[1] * second_vector[2] - first_vector[2] * second_vector[1],
        first_vector[2] * second_vector[0] - first_vector[0] * second_vector[2],
        first_vector[0] * second_vector[1] - first_vector[1] * second_vector[0],
    )

def vector_magnitude(vector):
    return math.sqrt(vector[0]**2 + vector[1]**2 + vector[2]**2)

def normalize_vector(vector):
    magnitude = vector_magnitude(vector)
    if magnitude < 1e-12:
        return (0.0, 0.0, 0.0)
    return (vector[0] / magnitude, vector[1] / magnitude, vector[2] / magnitude)

def distance_between_points(point_a, point_b):
    """
    Euclidean distance between two 3D positions.
    displacement = point_b - point_a
    distance = ||displacement|| = sqrt(dx² + dy² + dz²)
    """
    displacement_x = point_b[0] - point_a[0]
    displacement_y = point_b[1] - point_a[1]
    displacement_z = point_b[2] - point_a[2]
    return math.sqrt(displacement_x**2 + displacement_y**2 + displacement_z**2)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ORBITAL MECHANICS — KEPLERIAN TWO-BODY PROPAGATION
#
# Satellites orbit under gravity alone (two-body problem).
# We convert ECI state vectors to classical orbital elements,
# advance time through Kepler's equation, then convert back.
# No perturbations. Good to ~1 km over 24h for circular LEO.
# ═══════════════════════════════════════════════════════════════════════════════

def convert_state_vector_to_orbital_elements(position, velocity):
    """
    Given where a satellite is (position) and how fast it is moving (velocity),
    compute the six classical orbital elements that describe its orbit shape.

    position : (x, y, z) km  — ECI frame
    velocity : (vx, vy, vz) km/s — ECI frame

    Derivation:
      Specific energy      ε = v²/2 − μ/r        → semi_major_axis
      Angular momentum     h = position × velocity → inclination
      Node vector          N = ẑ × h              → right_ascension_of_ascending_node
      Eccentricity vector  e = (v × h)/μ − r̂     → argument_of_perigee, true_anomaly
      Kepler's equation    M = E − e·sin(E)        → mean_anomaly
    """
    position_magnitude = vector_magnitude(position)
    velocity_magnitude = vector_magnitude(velocity)

    # How much energy does this orbit have? Negative = bound orbit (good).
    specific_orbital_energy = (velocity_magnitude**2 / 2.0) - (EARTH_GRAVITATIONAL_PARAMETER / position_magnitude)

    # Semi-major axis: the average of the closest and farthest orbital distances.
    semi_major_axis = -EARTH_GRAVITATIONAL_PARAMETER / (2.0 * specific_orbital_energy)

    # Angular momentum: perpendicular to the orbital plane.
    angular_momentum_vector    = cross_product(position, velocity)
    angular_momentum_magnitude = vector_magnitude(angular_momentum_vector)

    # Node vector: points toward the ascending node (where orbit crosses equator going north).
    zenith_unit_vector = (0.0, 0.0, 1.0)
    node_vector        = cross_product(zenith_unit_vector, angular_momentum_vector)
    node_magnitude     = vector_magnitude(node_vector)

    # Eccentricity vector: points from Earth center toward orbit periapsis.
    velocity_cross_angular_momentum = cross_product(velocity, angular_momentum_vector)
    position_unit_vector            = normalize_vector(position)
    eccentricity_vector             = subtract_vectors(
        scale_vector(velocity_cross_angular_momentum, 1.0 / EARTH_GRAVITATIONAL_PARAMETER),
        position_unit_vector
    )
    eccentricity = vector_magnitude(eccentricity_vector)

    # Inclination: tilt of the orbital plane relative to equator.
    inclination = math.acos(max(-1.0, min(1.0,
        angular_momentum_vector[2] / angular_momentum_magnitude
    )))

    # Right Ascension of Ascending Node: where the orbit crosses the equator going north.
    if node_magnitude > 1e-10:
        right_ascension_of_ascending_node = math.acos(max(-1.0, min(1.0,
            node_vector[0] / node_magnitude
        )))
        if node_vector[1] < 0:
            right_ascension_of_ascending_node = 2 * math.pi - right_ascension_of_ascending_node
    else:
        right_ascension_of_ascending_node = 0.0

    # Argument of Perigee: angle from ascending node to the orbit's closest point.
    if node_magnitude > 1e-10 and eccentricity > 1e-10:
        argument_of_perigee = math.acos(max(-1.0, min(1.0,
            dot_product(node_vector, eccentricity_vector) / (node_magnitude * eccentricity)
        )))
        if eccentricity_vector[2] < 0:
            argument_of_perigee = 2 * math.pi - argument_of_perigee
    else:
        argument_of_perigee = 0.0

    # True Anomaly: where the satellite is in its orbit right now.
    if eccentricity > 1e-10:
        true_anomaly = math.acos(max(-1.0, min(1.0,
            dot_product(eccentricity_vector, position) / (eccentricity * position_magnitude)
        )))
        if dot_product(position, velocity) < 0:
            true_anomaly = 2 * math.pi - true_anomaly
    else:
        true_anomaly = 0.0

    # Eccentric Anomaly: an intermediate angle used to compute mean anomaly.
    eccentric_anomaly = 2.0 * math.atan2(
        math.sqrt(1.0 - eccentricity) * math.sin(true_anomaly / 2.0),
        math.sqrt(1.0 + eccentricity) * math.cos(true_anomaly / 2.0)
    )

    # Mean Anomaly: the "clock" of the orbit — advances uniformly with time.
    mean_anomaly = eccentric_anomaly - eccentricity * math.sin(eccentric_anomaly)

    # Mean Motion: how many radians per second the satellite sweeps.
    mean_motion = math.sqrt(EARTH_GRAVITATIONAL_PARAMETER / semi_major_axis**3)

    return {
        "semi_major_axis":                   semi_major_axis,
        "eccentricity":                      eccentricity,
        "inclination":                       inclination,
        "right_ascension_of_ascending_node": right_ascension_of_ascending_node,
        "argument_of_perigee":               argument_of_perigee,
        "true_anomaly":                      true_anomaly,
        "mean_anomaly":                      mean_anomaly,
        "mean_motion":                       mean_motion,
        "orbital_period":                    2.0 * math.pi / mean_motion,
        "angular_momentum_vector":           angular_momentum_vector,
        "eccentricity_vector":               eccentricity_vector,
    }


def solve_keplers_equation(mean_anomaly, eccentricity, tolerance=1e-10):
    """
    Solve M = E − e·sin(E) for the eccentric anomaly E, given mean anomaly M.

    We use Newton-Raphson iteration:
      function_value(E)           = E − e·sin(E) − M      (we want this to be zero)
      function_derivative(E)      = 1 − e·cos(E)
      next_guess = current_guess − function_value / function_derivative

    Converges in fewer than 10 iterations for any bound orbit.
    """
    current_guess = mean_anomaly if eccentricity < 0.8 else math.pi

    for _ in range(50):
        correction = (
            (mean_anomaly - current_guess + eccentricity * math.sin(current_guess)) /
            (1.0 - eccentricity * math.cos(current_guess))
        )
        current_guess += correction
        if abs(correction) < tolerance:
            break

    return current_guess


def convert_orbital_elements_to_state_vector(semi_major_axis, eccentricity,
                                              inclination,
                                              right_ascension_of_ascending_node,
                                              argument_of_perigee, true_anomaly):
    """
    Given the six orbital elements, compute the ECI position and velocity.

    Steps:
      1. Compute position and velocity in the perifocal (orbit-plane) frame.
      2. Rotate from orbit plane into the ECI frame using three angles:
         argument_of_perigee, inclination, right_ascension_of_ascending_node.

    Returns position (km), velocity (km/s) as 3-tuples.
    """
    semi_latus_rectum  = semi_major_axis * (1.0 - eccentricity**2)
    orbital_radius     = semi_latus_rectum / (1.0 + eccentricity * math.cos(true_anomaly))
    velocity_scale     = math.sqrt(EARTH_GRAVITATIONAL_PARAMETER / semi_latus_rectum)

    # Position and velocity in the perifocal frame (orbit plane, x-axis toward periapsis)
    position_in_perifocal_frame = (
        orbital_radius * math.cos(true_anomaly),
        orbital_radius * math.sin(true_anomaly),
        0.0
    )
    velocity_in_perifocal_frame = (
        -velocity_scale * math.sin(true_anomaly),
         velocity_scale * (eccentricity + math.cos(true_anomaly)),
         0.0
    )

    # Precompute trig values for the three rotation angles
    cosine_raan        = math.cos(right_ascension_of_ascending_node)
    sine_raan          = math.sin(right_ascension_of_ascending_node)
    cosine_argp        = math.cos(argument_of_perigee)
    sine_argp          = math.sin(argument_of_perigee)
    cosine_inclination = math.cos(inclination)
    sine_inclination   = math.sin(inclination)

    # Rotation matrix: perifocal → ECI  (R = Rz(−Ω) · Rx(−i) · Rz(−ω))
    rotation_matrix = [
        [
            cosine_raan * cosine_argp - sine_raan * sine_argp * cosine_inclination,
           -cosine_raan * sine_argp   - sine_raan * cosine_argp * cosine_inclination,
            sine_raan * sine_inclination,
        ],
        [
            sine_raan * cosine_argp + cosine_raan * sine_argp * cosine_inclination,
           -sine_raan * sine_argp   + cosine_raan * cosine_argp * cosine_inclination,
           -cosine_raan * sine_inclination,
        ],
        [
            sine_argp  * sine_inclination,
            cosine_argp * sine_inclination,
            cosine_inclination,
        ],
    ]

    def apply_rotation(vector):
        return (
            rotation_matrix[0][0]*vector[0] + rotation_matrix[0][1]*vector[1] + rotation_matrix[0][2]*vector[2],
            rotation_matrix[1][0]*vector[0] + rotation_matrix[1][1]*vector[1] + rotation_matrix[1][2]*vector[2],
            rotation_matrix[2][0]*vector[0] + rotation_matrix[2][1]*vector[1] + rotation_matrix[2][2]*vector[2],
        )

    return (
        apply_rotation(position_in_perifocal_frame),
        apply_rotation(velocity_in_perifocal_frame),
    )


def propagate_orbit_forward(initial_position, initial_velocity, seconds_to_advance):
    """
    Given a satellite's current ECI position and velocity,
    compute where it will be seconds_to_advance seconds from now.

    Steps:
      1. Convert current state to orbital elements.
      2. Advance the mean anomaly: new_mean_anomaly = mean_anomaly + mean_motion × Δt
      3. Solve Kepler's equation to get the eccentric anomaly at the new time.
      4. Convert eccentric anomaly → true anomaly.
      5. Convert orbital elements back to ECI state vector.
    """
    orbital_elements = convert_state_vector_to_orbital_elements(initial_position, initial_velocity)

    mean_anomaly_at_new_time = (
        orbital_elements["mean_anomaly"] +
        orbital_elements["mean_motion"] * seconds_to_advance
    ) % (2.0 * math.pi)

    eccentric_anomaly_at_new_time = solve_keplers_equation(
        mean_anomaly_at_new_time,
        orbital_elements["eccentricity"]
    )

    true_anomaly_at_new_time = 2.0 * math.atan2(
        math.sqrt(1.0 + orbital_elements["eccentricity"]) * math.sin(eccentric_anomaly_at_new_time / 2.0),
        math.sqrt(1.0 - orbital_elements["eccentricity"]) * math.cos(eccentric_anomaly_at_new_time / 2.0)
    )

    return convert_orbital_elements_to_state_vector(
        orbital_elements["semi_major_axis"],
        orbital_elements["eccentricity"],
        orbital_elements["inclination"],
        orbital_elements["right_ascension_of_ascending_node"],
        orbital_elements["argument_of_perigee"],
        true_anomaly_at_new_time,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CONJUNCTION ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════════

def distance_between_satellites(satellite_a, satellite_b):
    """
    Euclidean distance between two satellite ECI positions (km).
    displacement = position_b - position_a
    distance = ||displacement||
    """
    return distance_between_points(
        (satellite_a["x"], satellite_a["y"], satellite_a["z"]),
        (satellite_b["x"], satellite_b["y"], satellite_b["z"]),
    )


def relative_velocity_between_satellites(satellite_a, satellite_b):
    """Speed at which two satellites are moving relative to each other (km/s)."""
    relative_velocity_vector = (
        satellite_b["vx"] - satellite_a["vx"],
        satellite_b["vy"] - satellite_a["vy"],
        satellite_b["vz"] - satellite_a["vz"],
    )
    return vector_magnitude(relative_velocity_vector)


def satellites_are_approaching(satellite_a, satellite_b):
    """
    True if the gap between these two satellites is shrinking right now.
    dot(range_vector, relative_velocity_vector) < 0 means closing geometry.
    """
    range_vector = (
        satellite_b["x"] - satellite_a["x"],
        satellite_b["y"] - satellite_a["y"],
        satellite_b["z"] - satellite_a["z"],
    )
    relative_velocity_vector = (
        satellite_b["vx"] - satellite_a["vx"],
        satellite_b["vy"] - satellite_a["vy"],
        satellite_b["vz"] - satellite_a["vz"],
    )
    return dot_product(range_vector, relative_velocity_vector) < 0


def satellites_could_be_in_conjunction(satellite_a, satellite_b,
                                        altitude_difference_threshold_km=200.0):
    """
    Fast pre-filter. If two satellites are more than 200 km apart in altitude,
    they physically cannot conjunct. This eliminates most pairs before
    running the expensive time-stepping scan.
    """
    def altitude_of(satellite):
        return math.sqrt(satellite["x"]**2 + satellite["y"]**2 + satellite["z"]**2) - EARTH_MEAN_RADIUS_KM

    return abs(altitude_of(satellite_a) - altitude_of(satellite_b)) < altitude_difference_threshold_km


def find_closest_approach(satellite_a, satellite_b,
                           scan_duration_seconds=86400,
                           time_step_seconds=60):
    """
    Find the Time of Closest Approach (TCA) and minimum separation
    between two satellites over a future time window.

    A conjunction problem is: given two satellites,
    how close will they get within a future time window?

    We propagate both orbits forward one step at a time and record
    the minimum distance found. That minimum is the TCA.
    """
    initial_position_a = (satellite_a["x"], satellite_a["y"], satellite_a["z"])
    initial_velocity_a = (satellite_a["vx"], satellite_a["vy"], satellite_a["vz"])
    initial_position_b = (satellite_b["x"], satellite_b["y"], satellite_b["z"])
    initial_velocity_b = (satellite_b["vx"], satellite_b["vy"], satellite_b["vz"])

    minimum_distance_found   = float("inf")
    time_of_closest_approach = 0

    for elapsed_seconds in range(0, scan_duration_seconds, time_step_seconds):
        future_position_a, _ = propagate_orbit_forward(initial_position_a, initial_velocity_a, elapsed_seconds)
        future_position_b, _ = propagate_orbit_forward(initial_position_b, initial_velocity_b, elapsed_seconds)
        distance_at_this_step = distance_between_points(future_position_a, future_position_b)

        if distance_at_this_step < minimum_distance_found:
            minimum_distance_found   = distance_at_this_step
            time_of_closest_approach = elapsed_seconds

    return {
        "distance_km":  minimum_distance_found,
        "time_seconds": time_of_closest_approach,
        "approaching":  satellites_are_approaching(satellite_a, satellite_b),
    }


def classify_risk_from_distance(miss_distance_km):
    """Assign a risk tier from the TCA distance."""
    if miss_distance_km < CONJUNCTION_RISK_CRITICAL_KM:  return "CRITICAL"
    if miss_distance_km < CONJUNCTION_RISK_HIGH_KM:      return "HIGH"
    if miss_distance_km < CONJUNCTION_RISK_MODERATE_KM:  return "MODERATE"
    return "LOW"


def generate_conjunction_data_message(satellite_a, satellite_b, approach_result, epoch):
    """
    Generate a Conjunction Data Message (CDM).
    Field structure loosely follows CCSDS 508.0-B-1.
    """
    time_of_closest_approach_epoch = epoch + timedelta(seconds=approach_result["time_seconds"])
    closing_speed                  = relative_velocity_between_satellites(satellite_a, satellite_b)
    miss_distance                  = approach_result["distance_km"]
    probability_of_collision       = compute_collision_probability(miss_distance, closing_speed)

    return {
        "CDM_VERSION":                "1.0",
        "CREATION_DATE":              epoch.isoformat(),
        "ORIGINATOR":                 "IOLA/IkirereMesh",
        "TIME_OF_CLOSEST_APPROACH":   time_of_closest_approach_epoch.isoformat(),
        "MISS_DISTANCE_KM":           round(miss_distance, 4),
        "EFFECTIVE_MISS_DISTANCE_KM": round(miss_distance - POSITION_UNCERTAINTY_KM, 4),
        "RELATIVE_SPEED_KMS":         round(closing_speed, 4),
        "COLLISION_PROBABILITY":      round(probability_of_collision, 8),
        "RISK_CLASSIFICATION":        classify_risk_from_distance(miss_distance),
        "OBJECT_1_ID":                satellite_a.get("id", "SAT-A"),
        "OBJECT_1_POSITION_KM":       [satellite_a["x"], satellite_a["y"], satellite_a["z"]],
        "OBJECT_1_VELOCITY_KMS":      [satellite_a["vx"], satellite_a["vy"], satellite_a["vz"]],
        "OBJECT_2_ID":                satellite_b.get("id", "SAT-B"),
        "OBJECT_2_POSITION_KM":       [satellite_b["x"], satellite_b["y"], satellite_b["z"]],
        "OBJECT_2_VELOCITY_KMS":      [satellite_b["vx"], satellite_b["vy"], satellite_b["vz"]],
        "POSITION_UNCERTAINTY_KM":    POSITION_UNCERTAINTY_KM,
        "RECOMMENDED_ACTION":         generate_maneuver_recommendation(miss_distance, closing_speed, approach_result["time_seconds"]),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ECLIPSE & SUNLIGHT CYCLE MODELLING
# ═══════════════════════════════════════════════════════════════════════════════

def sun_position_in_eci_frame(epoch):
    """
    Approximate position of the Sun in the ECI frame (km).
    Simplified circular ecliptic orbit. Error < 1° per year.
    Based on: Vallado, "Fundamentals of Astrodynamics and Applications", Ch. 5
    """
    if epoch.tzinfo is None:
        epoch = epoch.replace(tzinfo=timezone.utc)

    j2000_reference_epoch = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    days_since_j2000      = (epoch - j2000_reference_epoch).total_seconds() / 86400.0

    mean_longitude_degrees  = (280.460  + 0.9856474 * days_since_j2000) % 360.0
    mean_anomaly_radians    = math.radians((357.528 + 0.9856003 * days_since_j2000) % 360.0)
    ecliptic_longitude      = math.radians(
        mean_longitude_degrees
        + 1.915 * math.sin(mean_anomaly_radians)
        + 0.020 * math.sin(2 * mean_anomaly_radians)
    )
    obliquity_of_ecliptic   = math.radians(23.439 - 0.0000004 * days_since_j2000)

    return (
        ONE_ASTRONOMICAL_UNIT_KM * math.cos(ecliptic_longitude),
        ONE_ASTRONOMICAL_UNIT_KM * math.cos(obliquity_of_ecliptic) * math.sin(ecliptic_longitude),
        ONE_ASTRONOMICAL_UNIT_KM * math.sin(obliquity_of_ecliptic) * math.sin(ecliptic_longitude),
    )


def satellite_is_in_eclipse(satellite_position, sun_position):
    """
    Cylindrical shadow model. Is this satellite in Earth's shadow?

    Two conditions must both be true:
      (1) Satellite is on the anti-sun side of Earth:
          dot(satellite_position, sun_direction) < 0
      (2) Its perpendicular distance from the Earth-Sun axis < R_EARTH:
          perpendicular_component = satellite_position − projection_onto_sun_axis
          eclipsed if ||perpendicular_component|| < R_EARTH
    """
    sun_direction_unit_vector     = normalize_vector(sun_position)
    projection_onto_sun_direction = dot_product(satellite_position, sun_direction_unit_vector)

    if projection_onto_sun_direction > 0:
        return False  # satellite is on the sunlit side

    projection_vector         = scale_vector(sun_direction_unit_vector, projection_onto_sun_direction)
    perpendicular_component   = subtract_vectors(satellite_position, projection_vector)

    return vector_magnitude(perpendicular_component) < EARTH_MEAN_RADIUS_KM


def fraction_of_orbit_in_eclipse(altitude_km):
    """
    What fraction of each orbit is spent in darkness?
    nadir_angle_to_horizon = arcsin(R_EARTH / (R_EARTH + altitude))
    eclipse_fraction = nadir_angle / π
    """
    nadir_angle_to_earths_horizon = math.asin(EARTH_MEAN_RADIUS_KM / (EARTH_MEAN_RADIUS_KM + altitude_km))
    return nadir_angle_to_earths_horizon / math.pi


def compute_sunlight_and_eclipse_windows(satellite, epoch,
                                          scan_duration_seconds=86400,
                                          time_step_seconds=60):
    """Walk through time and record every SUNLIT and ECLIPSE window."""
    initial_position = (satellite["x"], satellite["y"], satellite["z"])
    initial_velocity = (satellite["vx"], satellite["vy"], satellite["vz"])

    windows       = []
    current_state = None
    window_start  = epoch

    for elapsed_seconds in range(0, scan_duration_seconds + time_step_seconds, time_step_seconds):
        current_epoch           = epoch + timedelta(seconds=elapsed_seconds)
        current_position, _     = propagate_orbit_forward(initial_position, initial_velocity, elapsed_seconds)
        sun_at_this_epoch       = sun_position_in_eci_frame(current_epoch)
        state = "ECLIPSE" if satellite_is_in_eclipse(current_position, sun_at_this_epoch) else "SUNLIT"

        if state != current_state:
            if current_state is not None:
                windows.append({
                    "state":      current_state,
                    "start":      window_start.isoformat(),
                    "end":        current_epoch.isoformat(),
                    "duration_s": elapsed_seconds - int((window_start - epoch).total_seconds()),
                })
            current_state = state
            window_start  = current_epoch

    return windows


# ═══════════════════════════════════════════════════════════════════════════════
# 6. COVERAGE FOOTPRINT
# ═══════════════════════════════════════════════════════════════════════════════

def compute_coverage_footprint_radius(altitude_km, minimum_elevation_angle_deg=5.0):
    """
    How large is the circle on Earth's surface that this satellite can see?

    Spherical Earth geometry:
      earth_central_angle = π/2 − elevation_angle − arcsin(R_EARTH·cos(elevation) / (R_EARTH + h))
      footprint_radius    = R_EARTH × earth_central_angle   (arc length in km)
    """
    minimum_elevation_angle_radians = math.radians(minimum_elevation_angle_deg)

    earth_central_angle = (
        math.pi / 2
        - minimum_elevation_angle_radians
        - math.asin(
            EARTH_MEAN_RADIUS_KM * math.cos(minimum_elevation_angle_radians) /
            (EARTH_MEAN_RADIUS_KM + altitude_km)
        )
    )
    return EARTH_MEAN_RADIUS_KM * earth_central_angle


def satellite_footprints_overlap(satellite_a, satellite_b, minimum_elevation_angle_deg=5.0):
    """
    Do two satellite coverage footprints overlap on Earth's surface?

    angular_separation between sub-satellite points → surface distance.
    Overlap if surface_distance < footprint_radius_a + footprint_radius_b.
    """
    position_a = (satellite_a["x"], satellite_a["y"], satellite_a["z"])
    position_b = (satellite_b["x"], satellite_b["y"], satellite_b["z"])
    altitude_a = vector_magnitude(position_a) - EARTH_MEAN_RADIUS_KM
    altitude_b = vector_magnitude(position_b) - EARTH_MEAN_RADIUS_KM

    cosine_of_angular_separation = max(-1.0, min(1.0,
        dot_product(normalize_vector(position_a), normalize_vector(position_b))
    ))
    surface_separation_km = EARTH_MEAN_RADIUS_KM * math.acos(cosine_of_angular_separation)

    footprint_radius_a = compute_coverage_footprint_radius(altitude_a, minimum_elevation_angle_deg)
    footprint_radius_b = compute_coverage_footprint_radius(altitude_b, minimum_elevation_angle_deg)

    return {
        "overlap":           surface_separation_km < (footprint_radius_a + footprint_radius_b),
        "separation_km":     round(surface_separation_km, 2),
        "footprint_a_km":    round(footprint_radius_a, 2),
        "footprint_b_km":    round(footprint_radius_b, 2),
        "overlap_margin_km": round((footprint_radius_a + footprint_radius_b) - surface_separation_km, 2),
    }


def compute_fleet_coverage_overlaps(satellites, minimum_elevation_angle_deg=5.0):
    """Coverage overlap for every satellite pair in the fleet."""
    results       = []
    satellite_ids = [satellite.get("id", f"SAT-{index}") for index, satellite in enumerate(satellites)]

    for index_a in range(len(satellites)):
        for index_b in range(index_a + 1, len(satellites)):
            overlap        = satellite_footprints_overlap(satellites[index_a], satellites[index_b], minimum_elevation_angle_deg)
            overlap["pair"] = (satellite_ids[index_a], satellite_ids[index_b])
            results.append(overlap)

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 7. ORBITAL DECAY ESTIMATION
# ═══════════════════════════════════════════════════════════════════════════════

def atmospheric_density_at_altitude(altitude_km):
    """
    Air density at altitude using piecewise exponential model.
    density(h) = base_density × exp(−(h − base_altitude) / scale_height)
    Returns kg/m³.
    """
    best_matching_layer = ATMOSPHERE_LAYERS[0]
    for layer in ATMOSPHERE_LAYERS:
        if altitude_km >= layer[0]:
            best_matching_layer = layer
        else:
            break

    base_altitude, base_density, scale_height = best_matching_layer
    return base_density * math.exp(-(altitude_km - base_altitude) / scale_height)


def compute_orbital_decay_rate(altitude_km,
                                drag_coefficient=2.2,
                                cross_section_area_m2=0.03,
                                satellite_mass_kg=4.0):
    """
    How fast is the semi-major axis shrinking due to atmospheric drag? (km/s)

    ballistic_coefficient = satellite_mass / (drag_coefficient × area)   kg/m²
    drag_deceleration     = −0.5 × air_density × velocity² / ballistic_coefficient
    decay_rate            = 2 × semi_major_axis × drag_deceleration / velocity

    Negative result = orbit is losing altitude.
    """
    semi_major_axis              = EARTH_MEAN_RADIUS_KM + altitude_km
    air_density_kg_per_km3       = atmospheric_density_at_altitude(altitude_km) * 1e-9
    ballistic_coefficient_kg_per_km2 = (satellite_mass_kg / (drag_coefficient * cross_section_area_m2)) * 1e6
    circular_velocity            = math.sqrt(EARTH_GRAVITATIONAL_PARAMETER / semi_major_axis)
    drag_deceleration            = -0.5 * air_density_kg_per_km3 * circular_velocity**2 / ballistic_coefficient_kg_per_km2
    decay_rate                   = 2.0 * semi_major_axis * drag_deceleration / circular_velocity

    return decay_rate


def estimate_orbital_lifetime(altitude_km,
                               drag_coefficient=2.2,
                               cross_section_area_m2=0.03,
                               satellite_mass_kg=4.0):
    """
    Step altitude down 1 km at a time, accumulating the time spent at each layer.
    Reentry begins around 80 km.
    """
    current_altitude   = altitude_km
    total_time_seconds = 0.0

    while current_altitude > 80.0:
        decay_rate = compute_orbital_decay_rate(current_altitude, drag_coefficient, cross_section_area_m2, satellite_mass_kg)
        if decay_rate >= 0:
            break
        total_time_seconds += abs(1.0 / decay_rate)
        current_altitude   -= 1.0

    return {
        "initial_altitude_km":     altitude_km,
        "estimated_lifetime_days": round(total_time_seconds / 86400.0, 1),
        "decay_rate_km_per_day":   round(abs(compute_orbital_decay_rate(altitude_km, drag_coefficient, cross_section_area_m2, satellite_mass_kg)) * 86400.0, 5),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 8. COMMUNICATION WINDOW PREDICTION
# ═══════════════════════════════════════════════════════════════════════════════

def greenwich_mean_sidereal_time(epoch):
    """
    Earth's rotation angle at this moment (radians).
    Required to convert between ECI (fixed to stars) and ECEF (fixed to Earth).
    θ_GMST = 280.46061837 + 360.98564736629 × (JD − J2000)
    """
    if epoch.tzinfo is None:
        epoch = epoch.replace(tzinfo=timezone.utc)

    j2000_reference_epoch  = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    julian_date            = 2451545.0 + (epoch - j2000_reference_epoch).total_seconds() / 86400.0
    sidereal_angle_degrees = 280.46061837 + 360.98564736629 * (julian_date - 2451545.0)

    return math.radians(sidereal_angle_degrees % 360.0)


def rotate_eci_to_ecef(eci_position, epoch):
    """
    Rotate an ECI position into ECEF by applying Earth's current rotation angle.
    x_ecef =  cos(θ) · x_eci + sin(θ) · y_eci
    y_ecef = −sin(θ) · x_eci + cos(θ) · y_eci
    z_ecef =  z_eci
    """
    sidereal_angle  = greenwich_mean_sidereal_time(epoch)
    cosine_sidereal = math.cos(sidereal_angle)
    sine_sidereal   = math.sin(sidereal_angle)

    return (
         cosine_sidereal * eci_position[0] + sine_sidereal   * eci_position[1],
        -sine_sidereal   * eci_position[0] + cosine_sidereal * eci_position[1],
         eci_position[2],
    )


def rotate_ecef_to_eci(ecef_position, epoch):
    """Reverse rotation: ECEF → ECI."""
    sidereal_angle  = greenwich_mean_sidereal_time(epoch)
    cosine_sidereal = math.cos(sidereal_angle)
    sine_sidereal   = math.sin(sidereal_angle)

    return (
        cosine_sidereal * ecef_position[0] - sine_sidereal   * ecef_position[1],
        sine_sidereal   * ecef_position[0] + cosine_sidereal * ecef_position[1],
        ecef_position[2],
    )


def ground_station_position_in_ecef(latitude_deg, longitude_deg, altitude_km=0.0):
    """ECEF position of a point on Earth's surface (km)."""
    latitude_radians  = math.radians(latitude_deg)
    longitude_radians = math.radians(longitude_deg)
    surface_radius    = EARTH_MEAN_RADIUS_KM + altitude_km

    return (
        surface_radius * math.cos(latitude_radians) * math.cos(longitude_radians),
        surface_radius * math.cos(latitude_radians) * math.sin(longitude_radians),
        surface_radius * math.sin(latitude_radians),
    )


def compute_elevation_angle(satellite_ecef_position, ground_station_ecef_position,
                             ground_station_latitude_deg, ground_station_longitude_deg):
    """
    Elevation of the satellite above the ground station's horizon (degrees).

    range_vector      = satellite_position − ground_station_position
    zenith_direction  = upward unit vector at the ground station's lat/lon
    elevation         = arcsin(range_unit_vector · zenith_direction)
    """
    range_vector      = subtract_vectors(satellite_ecef_position, ground_station_ecef_position)
    range_unit_vector = normalize_vector(range_vector)

    latitude_radians  = math.radians(ground_station_latitude_deg)
    longitude_radians = math.radians(ground_station_longitude_deg)

    zenith_direction = (
        math.cos(latitude_radians) * math.cos(longitude_radians),
        math.cos(latitude_radians) * math.sin(longitude_radians),
        math.sin(latitude_radians),
    )

    sine_of_elevation = dot_product(range_unit_vector, zenith_direction)
    elevation_degrees = math.degrees(math.asin(max(-1.0, min(1.0, sine_of_elevation))))

    return {
        "elevation_deg": round(elevation_degrees, 3),
        "range_km":      round(vector_magnitude(range_vector), 3),
    }


def predict_communication_windows(satellite, ground_station, epoch,
                                   scan_duration_seconds=86400,
                                   time_step_seconds=30,
                                   minimum_elevation_deg=5.0):
    """
    Find every window when this satellite is above the ground station's horizon
    at a usable elevation angle.

    ground_station: {lat, lon, alt_km, name}
    Returns list of {start, end, duration_s, max_elevation_deg, ground_station}.
    """
    initial_position = (satellite["x"], satellite["y"], satellite["z"])
    initial_velocity = (satellite["vx"], satellite["vy"], satellite["vz"])

    ground_station_ecef = ground_station_position_in_ecef(
        ground_station["lat"], ground_station["lon"], ground_station.get("alt_km", 0.0)
    )
    latitude  = ground_station["lat"]
    longitude = ground_station["lon"]

    windows             = []
    currently_in_window = False
    window_start_second = 0
    maximum_elevation   = -90.0

    for elapsed_seconds in range(0, scan_duration_seconds + time_step_seconds, time_step_seconds):
        current_epoch            = epoch + timedelta(seconds=elapsed_seconds)
        current_eci_position, _  = propagate_orbit_forward(initial_position, initial_velocity, elapsed_seconds)
        current_ecef_position    = rotate_eci_to_ecef(current_eci_position, current_epoch)
        elevation_data           = compute_elevation_angle(current_ecef_position, ground_station_ecef, latitude, longitude)
        current_elevation        = elevation_data["elevation_deg"]

        if current_elevation >= minimum_elevation_deg:
            if not currently_in_window:
                currently_in_window = True
                window_start_second = elapsed_seconds
                maximum_elevation   = current_elevation
            else:
                maximum_elevation = max(maximum_elevation, current_elevation)
        else:
            if currently_in_window:
                windows.append({
                    "start":             (epoch + timedelta(seconds=window_start_second)).isoformat(),
                    "end":               current_epoch.isoformat(),
                    "duration_s":        elapsed_seconds - window_start_second,
                    "max_elevation_deg": round(maximum_elevation, 2),
                    "ground_station":    ground_station.get("name", "GS"),
                })
                currently_in_window = False
                maximum_elevation   = -90.0

    return windows


# ═══════════════════════════════════════════════════════════════════════════════
# 9. LINE-OF-SIGHT
# ═══════════════════════════════════════════════════════════════════════════════

def earth_blocks_line_of_sight(position_a, position_b):
    """
    Does Earth sit between two points in space?

    Draw a line from A to B. Find the point on that line closest to Earth's center.
    If that closest point is inside Earth, the line of sight is blocked.

    Parametric line: P(t) = A + t × (B − A), t ∈ [0, 1]
    Closest point parameter: t_closest = −(A · direction) / |direction|²
    Blocked if ||closest_point|| < R_EARTH.
    """
    direction_vector            = subtract_vectors(position_b, position_a)
    direction_magnitude_squared = dot_product(direction_vector, direction_vector)

    if direction_magnitude_squared < 1e-12:
        return False

    parameter_of_closest_point = max(0.0, min(1.0,
        -dot_product(position_a, direction_vector) / direction_magnitude_squared
    ))
    closest_point_on_line = add_vectors(position_a, scale_vector(direction_vector, parameter_of_closest_point))

    return vector_magnitude(closest_point_on_line) < EARTH_MEAN_RADIUS_KM


def check_satellite_to_satellite_line_of_sight(satellite_a, satellite_b):
    """Can these two satellites see each other directly?"""
    position_a = (satellite_a["x"], satellite_a["y"], satellite_a["z"])
    position_b = (satellite_b["x"], satellite_b["y"], satellite_b["z"])
    blocked    = earth_blocks_line_of_sight(position_a, position_b)

    return {
        "line_of_sight_available": not blocked,
        "blocked_by_earth":        blocked,
        "range_km":                round(distance_between_points(position_a, position_b), 3),
    }


def check_satellite_to_ground_line_of_sight(satellite, latitude_deg, longitude_deg, epoch):
    """Can this satellite see this point on the ground?"""
    satellite_eci_position = (satellite["x"], satellite["y"], satellite["z"])
    ground_ecef_position   = ground_station_position_in_ecef(latitude_deg, longitude_deg)
    ground_eci_position    = rotate_ecef_to_eci(ground_ecef_position, epoch)
    blocked = earth_blocks_line_of_sight(satellite_eci_position, ground_eci_position)

    return {
        "line_of_sight_available": not blocked,
        "blocked_by_earth":        blocked,
        "range_km":                round(distance_between_points(satellite_eci_position, ground_eci_position), 3),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 10. RISK SCORING & COLLISION PROBABILITY
# ═══════════════════════════════════════════════════════════════════════════════

def compute_collision_probability(miss_distance_km, relative_velocity_kms,
                                   position_uncertainty_km=POSITION_UNCERTAINTY_KM):
    """
    Simplified Gaussian collision probability.

    Full Chan formula requires 3D covariance matrices.
    This first-principles version gives the correct order of magnitude.

    probability ≈ (hard_body_radius² / (2 × uncertainty²)) × exp(−distance² / (2 × uncertainty²))

    hard_body_radius : combined satellite + debris radius (~10 m for a CubeSat)
    """
    combined_hard_body_radius_km = 0.010  # 10 metres expressed in km

    probability = (
        (combined_hard_body_radius_km**2 / (2.0 * position_uncertainty_km**2)) *
        math.exp(-(miss_distance_km**2) / (2.0 * position_uncertainty_km**2))
    )
    return min(1.0, probability)


def compute_composite_risk_score(satellite_a, satellite_b, approach_result, epoch):
    """
    One number [0, 1] representing how dangerous this conjunction is.

    Four components weighted by importance:
      45% — distance risk:   closer TCA = more dangerous
      25% — velocity risk:   higher relative speed = less time to react
      20% — time urgency:    TCA within 2 hours = full urgency
      10% — probability contribution

    Extra 0.1 added if the satellites are confirmed closing right now.
    """
    miss_distance            = approach_result["distance_km"]
    time_to_closest_approach = approach_result["time_seconds"]
    relative_velocity        = relative_velocity_between_satellites(satellite_a, satellite_b)
    probability_of_collision  = compute_collision_probability(miss_distance, relative_velocity)

    distance_risk_component  = max(0.0, 1.0 - miss_distance / 50.0)
    velocity_risk_component  = min(1.0, relative_velocity / 15.0)
    time_urgency_component   = max(0.0, 1.0 - time_to_closest_approach / 7200.0)
    probability_component    = min(1.0, probability_of_collision * 1e5)

    total_risk_score = (
        0.45 * distance_risk_component +
        0.25 * velocity_risk_component +
        0.20 * time_urgency_component  +
        0.10 * probability_component
    )

    if approach_result["approaching"]:
        total_risk_score += 0.1

    return {
        "composite_score":                   round(min(1.0, total_risk_score), 4),
        "risk_level":                        classify_risk_from_distance(miss_distance),
        "probability_of_collision":          round(probability_of_collision, 8),
        "distance_risk_component":           round(distance_risk_component, 4),
        "velocity_risk_component":           round(velocity_risk_component, 4),
        "time_urgency_component":            round(time_urgency_component, 4),
        "time_to_closest_approach_seconds":  time_to_closest_approach,
        "relative_velocity_kms":             round(relative_velocity, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 11. MANEUVER RECOMMENDATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_avoidance_delta_v(miss_distance_km, time_to_closest_approach_seconds,
                                target_safe_separation_km=25.0):
    """
    How much velocity change (m/s) is needed to safely clear this conjunction?

    Simplified impulsive estimate:
    delta_v = (target_separation − miss_distance) / time_to_TCA

    Real maneuver planning needs numerical integration.
    This is the order-of-magnitude figure for operator decision-making.
    """
    if time_to_closest_approach_seconds <= 0:
        return float("inf")

    required_additional_separation = max(0.0, target_safe_separation_km - miss_distance_km)
    delta_v_in_km_per_second       = required_additional_separation / time_to_closest_approach_seconds

    return round(delta_v_in_km_per_second * 1000.0, 4)  # convert to m/s


def generate_maneuver_recommendation(miss_distance_km, relative_velocity_kms,
                                      time_to_closest_approach_seconds):
    """What should the operator do? Deterministic answer based on risk tier."""
    risk_tier  = classify_risk_from_distance(miss_distance_km)

    if risk_tier == "LOW":
        return {"action": "MONITOR", "urgency": "ROUTINE", "delta_v_ms": None}

    delta_v_ms = estimate_avoidance_delta_v(miss_distance_km, time_to_closest_approach_seconds)

    if risk_tier == "MODERATE":
        return {
            "action":                  "MONITOR_CLOSELY",
            "urgency":                 "ELEVATED",
            "delta_v_ms":              delta_v_ms,
            "maneuver_window_seconds": time_to_closest_approach_seconds,
        }

    if risk_tier == "HIGH":
        return {
            "action":                      "MANEUVER_RECOMMENDED",
            "urgency":                     "HIGH",
            "delta_v_ms":                  delta_v_ms,
            "maneuver_window_seconds":     time_to_closest_approach_seconds,
            "latest_maneuver_time_seconds": time_to_closest_approach_seconds * 0.5,
        }

    # CRITICAL
    return {
        "action":                      "MANEUVER_IMMEDIATE",
        "urgency":                     "CRITICAL",
        "delta_v_ms":                  delta_v_ms,
        "maneuver_window_seconds":     time_to_closest_approach_seconds,
        "latest_maneuver_time_seconds": min(time_to_closest_approach_seconds * 0.25, 900.0),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 12. FLEET STATE AWARENESS
# ═══════════════════════════════════════════════════════════════════════════════

def get_satellite_altitude(satellite):
    orbital_radius = math.sqrt(satellite["x"]**2 + satellite["y"]**2 + satellite["z"]**2)
    return orbital_radius - EARTH_MEAN_RADIUS_KM

def get_satellite_speed(satellite):
    return math.sqrt(satellite["vx"]**2 + satellite["vy"]**2 + satellite["vz"]**2)


def generate_fleet_state_snapshot(satellites, epoch, ground_stations=None):
    """
    A complete picture of the entire fleet at this moment.

    For every satellite  : altitude, speed, eclipse, decay rate, lifetime, footprint.
    For every pair       : TCA distance, risk score, collision probability, line-of-sight.
    Fleet summary        : critical/high conjunctions, eclipse count, coverage overlaps.

    CDMs are generated automatically for any pair rated MODERATE or above.
    Returns a dict ready for the IOLA Command Center dashboard.
    """
    current_sun_position = sun_position_in_eci_frame(epoch)

    fleet_snapshot = {
        "epoch":             epoch.isoformat(),
        "fleet_size":        len(satellites),
        "satellites":        [],
        "conjunctions":      [],
        "coverage_overlaps": [],
        "fleet_summary":     {},
    }

    for satellite in satellites:
        altitude         = get_satellite_altitude(satellite)
        speed            = get_satellite_speed(satellite)
        satellite_position = (satellite["x"], satellite["y"], satellite["z"])
        is_eclipsed      = satellite_is_in_eclipse(satellite_position, current_sun_position)
        lifetime_data    = estimate_orbital_lifetime(altitude)

        satellite_state = {
            "id":                  satellite.get("id", "UNKNOWN"),
            "altitude_km":         round(altitude, 2),
            "speed_kms":           round(speed, 4),
            "eclipsed":            is_eclipsed,
            "decay_rate_km_day":   lifetime_data["decay_rate_km_per_day"],
            "lifetime_days":       lifetime_data["estimated_lifetime_days"],
            "footprint_radius_km": round(compute_coverage_footprint_radius(altitude), 2),
            "eclipse_fraction":    round(fraction_of_orbit_in_eclipse(altitude), 4),
        }

        if ground_stations:
            satellite_state["communication_windows_next_6h"] = []
            for ground_station in ground_stations:
                windows = predict_communication_windows(
                    satellite, ground_station, epoch,
                    scan_duration_seconds=21600, time_step_seconds=30
                )
                satellite_state["communication_windows_next_6h"].extend(windows)

        fleet_snapshot["satellites"].append(satellite_state)

    satellite_ids = [satellite.get("id", f"SAT-{index}") for index, satellite in enumerate(satellites)]

    for index_a in range(len(satellites)):
        for index_b in range(index_a + 1, len(satellites)):
            satellite_a = satellites[index_a]
            satellite_b = satellites[index_b]

            if not satellites_could_be_in_conjunction(satellite_a, satellite_b):
                continue

            approach  = find_closest_approach(satellite_a, satellite_b, scan_duration_seconds=86400, time_step_seconds=120)
            risk      = compute_composite_risk_score(satellite_a, satellite_b, approach, epoch)
            los       = check_satellite_to_satellite_line_of_sight(satellite_a, satellite_b)

            conjunction_record = {
                "pair":                  (satellite_ids[index_a], satellite_ids[index_b]),
                "tca_distance_km":       round(approach["distance_km"], 3),
                "tca_time_seconds":      approach["time_seconds"],
                "risk_level":            risk["risk_level"],
                "risk_score":            risk["composite_score"],
                "collision_probability": risk["probability_of_collision"],
                "line_of_sight":         los["line_of_sight_available"],
                "approaching":           approach["approaching"],
            }

            if risk["risk_level"] in ("CRITICAL", "HIGH", "MODERATE"):
                conjunction_record["conjunction_data_message"] = generate_conjunction_data_message(
                    satellite_a, satellite_b, approach, epoch
                )

            fleet_snapshot["conjunctions"].append(conjunction_record)

    fleet_snapshot["coverage_overlaps"] = compute_fleet_coverage_overlaps(satellites)

    number_of_critical_conjunctions  = sum(1 for c in fleet_snapshot["conjunctions"] if c["risk_level"] == "CRITICAL")
    number_of_high_risk_conjunctions = sum(1 for c in fleet_snapshot["conjunctions"] if c["risk_level"] == "HIGH")
    number_of_eclipsed_satellites    = sum(1 for s in fleet_snapshot["satellites"]   if s["eclipsed"])

    fleet_snapshot["fleet_summary"] = {
        "critical_conjunctions":      number_of_critical_conjunctions,
        "high_risk_conjunctions":     number_of_high_risk_conjunctions,
        "satellites_eclipsed":        number_of_eclipsed_satellites,
        "satellites_sunlit":          len(satellites) - number_of_eclipsed_satellites,
        "total_pairs_scanned":        len(fleet_snapshot["conjunctions"]),
        "overlapping_coverage_pairs": sum(1 for overlap in fleet_snapshot["coverage_overlaps"] if overlap["overlap"]),
    }

    return fleet_snapshot


# ═══════════════════════════════════════════════════════════════════════════════
# 13. MISSION PLANNING PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════════

def predict_imaging_windows(satellite, target_latitude, target_longitude, epoch,
                             scan_duration_seconds=86400, time_step_seconds=30,
                             minimum_elevation_for_useful_imagery_deg=30.0):
    """
    When is this satellite directly above the target location at a steep enough
    angle to capture usable imagery? 30° minimum is a reasonable starting point
    for agricultural imaging.
    """
    return predict_communication_windows(
        satellite,
        {
            "lat":    target_latitude,
            "lon":    target_longitude,
            "alt_km": 0.0,
            "name":   f"IMAGING_TARGET({target_latitude:.2f}, {target_longitude:.2f})",
        },
        epoch,
        scan_duration_seconds,
        time_step_seconds,
        minimum_elevation_for_useful_imagery_deg,
    )


def generate_downlink_schedule(satellite, ground_stations, epoch,
                                scan_duration_seconds=86400, time_step_seconds=30):
    """
    Merged, time-sorted list of all downlink opportunities
    across every ground station for this satellite.
    """
    all_communication_windows = []
    for ground_station in ground_stations:
        windows = predict_communication_windows(satellite, ground_station, epoch,
                                                scan_duration_seconds, time_step_seconds)
        all_communication_windows.extend(windows)

    all_communication_windows.sort(key=lambda window: window["start"])
    return all_communication_windows


def compute_orbital_period(satellite):
    """Orbital period in seconds from the satellite's current state vector."""
    orbital_elements = convert_state_vector_to_orbital_elements(
        (satellite["x"], satellite["y"], satellite["z"]),
        (satellite["vx"], satellite["vy"], satellite["vz"]),
    )
    return round(orbital_elements["orbital_period"], 2)


def compute_passes_per_day(satellite):
    """How many complete orbits does this satellite complete in 24 hours?"""
    return round(86400.0 / compute_orbital_period(satellite), 3)


def generate_orbital_forecast(satellite, epoch,
                               number_of_forecast_steps=10,
                               minutes_between_forecast_steps=90):
    """
    Where will this satellite be at regular intervals from now?
    Default: every 90 minutes for 10 steps — roughly one step per orbit.
    """
    initial_position = (satellite["x"], satellite["y"], satellite["z"])
    initial_velocity = (satellite["vx"], satellite["vy"], satellite["vz"])
    forecast         = []

    for step_number in range(number_of_forecast_steps):
        seconds_ahead      = step_number * minutes_between_forecast_steps * 60
        epoch_at_this_step = epoch + timedelta(seconds=seconds_ahead)

        future_position, future_velocity = propagate_orbit_forward(
            initial_position, initial_velocity, seconds_ahead
        )
        altitude_at_this_step = vector_magnitude(future_position) - EARTH_MEAN_RADIUS_KM
        sun_at_this_step      = sun_position_in_eci_frame(epoch_at_this_step)

        forecast.append({
            "epoch":            epoch_at_this_step.isoformat(),
            "seconds_from_now": seconds_ahead,
            "position_km":      [round(coordinate, 3) for coordinate in future_position],
            "velocity_kms":     [round(component,   6) for component  in future_velocity],
            "altitude_km":      round(altitude_at_this_step, 2),
            "speed_kms":        round(vector_magnitude(future_velocity), 4),
            "eclipsed":         satellite_is_in_eclipse(future_position, sun_at_this_step),
        })

    return forecast
