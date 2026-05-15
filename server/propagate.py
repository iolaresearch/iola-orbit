import math
from sgp4.api import Satrec, jday
from datetime import datetime, timezone
from state import satellite_cache

EARTH_RADIUS_KM = 6371
LEO_MAX_ALTITUDE = 2000
MEO_MAX_ALTITUDE = 35786

def propagate_satellites():
    with open("../data/active.tle", "r") as file:
        lines = file.readlines()
        current_time = datetime.now(timezone.utc)

        jd, fr = jday(
            current_time.year,
            current_time.month,
            current_time.day,
            current_time.hour,
            current_time.minute,
            current_time.second
        )

        satellites = []

        for i in range(0, len(lines), 3):
            try:
                name = lines[i].strip()
                tle_line1 = lines[i + 1].strip()
                tle_line2 = lines[i + 2].strip()
                norad_id = tle_line1[2:7].strip()

                satellite = Satrec.twoline2rv(tle_line1, tle_line2)

                error, position, velocity = satellite.sgp4(jd, fr)

                if error == 0:
                    altitude = (
                        math.sqrt(
                            position[0] ** 2 +
                            position[1] ** 2 +
                            position[2] ** 2
                        ) - EARTH_RADIUS_KM
                    )
                    if altitude < LEO_MAX_ALTITUDE:
                        orbit_class = "LEO"
                    elif altitude < MEO_MAX_ALTITUDE:
                        orbit_class = "MEO"
                    else:
                        orbit_class = "GEO"

                    satellite_data = {
                        "name": name,
                        "norad_id": norad_id,

                        "x": position[0],
                        "y": position[1],
                        "z": position[2],

                        "altitude": altitude,
                        "orbital_class": orbit_class,
                        
                        "vx": velocity[0],
                        "vy": velocity[1],
                        "vz": velocity[2]
                    }

                    satellites.append(satellite_data)
            except Exception as e:
                print(f"propagation failed for satellite block {i // 3}: {e}")
                continue
    
    if not satellites:
        print("Propagation Produced satellites: Keeping existing cache.")
        return

    satellite_cache.clear()
    satellite_cache.extend(satellites)