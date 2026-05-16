import math

POSITION_UNCERTAINTY_KM = 1

def distance_between_satellites(satellite_a, satellite_b):
    dx = satellite_b["x"] - satellite_a["x"]
    dy = satellite_b["y"] - satellite_a["y"]
    dz = satellite_b["z"] - satellite_a["z"]

    distance = math.sqrt(
        dx ** 2 +
        dy ** 2 +
        dz ** 2
    )

    return distance

def relataive_velocity_between_satellites(satellite_a, satellite_b):
    dvx = satellite_b["vx"] - satellite_a["vx"]
    dvy = satellite_b["vy"] - satellite_a["vy"]
    dvz = satellite_b["vz"] - satellite_a["vz"]

    velocity = math.sqrt(
        dvx ** 2 +
        dvy ** 2 +
        dvz ** 2
    )

    return velocity

def predict_satellite_position(satellite, seconds):
    future_x = (
        satellite["x"] +
        satellite["vx"] * seconds
    )

    future_y = (
        satellite["y"] +
        satellite["vy"] * seconds
    )

    future_z = (
        satellite["z"] +
        satellite["vz"] * seconds
    )

    return {
        "x": future_x,
        "y": future_y,
        "z": future_z
    }

def closest_satellite_approach(
    satellite_a,
    satellite_b,
):
    minimum_distance = float("inf")
    closest_time = 0

    for seconds in range(0, duration_seconds, step_seconds):
        future_a = predict_satellite_position(satellite_a, seconds)
        future_b = predict_satellite_position(satellite_b, seconds)

        distance = distance_between_satellites(future_a, future_b)

        if distance < minimum_distance:
            minimum_distance = distance
            closest_time = seconds
        
    return {
        "distance_km": minimum_distance,
        "time_seconds": closest_time,
        "approaching": approaching
    }

def classify_satellite_conjunction_risk(distance_km):
    if distance_km < 1:
        return "CRITICAL"
    elif distance_km < 5:
        return "HIGH"
    elif distance_km < 20:
        return "MODERATE"
    return "LOW"

approach = closest_approach(
    satellite_a, satellite_b
)

risk = classify_satellite_conjunction_risk(
    approach["distance_km"]
)

def possible_conjunction_candidate(
    satellite_a, satellite_b,
    altitude_threshold=200
):
    altitude_difference = abs(
        satellite_a["altitude"] - satellite_b["altitude"]
    )
    return altitude_difference < altitude_threshold

def satellites_are_approaching(
    satellite_a, satellite_b
):
    dx = satellite_b["x"] - satellite_a["x"]
    dy = satellite_b["y"] - satellite_a["y"]
    dz = satellite_b["z"] - satellite_a["z"]

    dvx = satellite_b["vx"] - satellite_a["vx"]
    dvy = satellite_b["vy"] - satellite_a["vy"]
    dvz = satellite_b["vz"] - satellite_a["vz"]

    dot_product = (
        dx * dvx +
        dy * dvy +
        dz * dvz
    )

    return dot_product < 0

effective_distance = (
    approach["distance_km"] - POSITION_UNCERTAINTY_KM
)