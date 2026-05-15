from sgp4.api import Satrec, jday
from datetime import datetime, timezone
from state import satellite_cache

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

                satellite = Satrec.twoline2rv(tle_line1, tle_line2)

                error, position, velocity = satellite.sgp4(jd, fr)

                if error == 0:
                    satellite_data = {
                        "name": name,
                        "x": position[0],
                        "y": position[1],
                        "z": position[2],
                        "vx": velocity[0],
                        "vy": velocity[1],
                        "vz": velocity[2]
                    }

                    satellites.append(satellite_data)
            except:
                continue

    satellite_cache.clear()
    satellite_cache.extend(satellites)