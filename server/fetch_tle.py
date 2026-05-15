import os
import httpx
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("CELESTRAK_URL")
TLE_PATH = "../data/active.tle"
TEMP_TLE_PATH = "../data/active.tle.tmp"
MIN_SATELLITES = 100
CELESTRAK_COOLDOWN_MSG = ("GP data has not been updated")

headers = {
    "User-Agent": "iola-orbit/1.0"
}

def validate_refreshed_tle_file(tle_data):
    lines = [
        line
        for line in tle_data.strip().splitlines()
        if line.strip()
    ]

    if len(lines) < MIN_SATELLITES * 3:
        return False
    if len(lines) % 3 != 0:
        return False

    for i in range(0, len(lines), 3):
        if not lines[i + 1].startswith("1 "):
            return False
        if not lines[i + 2].startswith("2 "):
            return False
    return True

def fetch_tle():

    response = httpx.get(
        url,
        headers=headers,
        follow_redirects=True
    )

    tle_data = response.text

    if CELESTRAK_COOLDOWN_MSG in tle_data:
        print(
            "TLE Refreshed skipped: "
            "CelesTrak cooldown active."
        )
        return
    
    if not validate_refreshed_tle_file(tle_data):
        print(
            "TLE refresh skipped: "
            "invalid TLE structure."
        )

    with open(TEMP_TLE_PATH, "w") as file:
        file.write(tle_data)
    os.replace(
        TEMP_TLE_PATH,
        TLE_PATH
    )

    lines = tle_data.strip().split("\n")

    satellite_count = len(lines) // 3

    print(
        f"TLE catalog refreshed: "
        f"{satellite_count} satellites"
    )