import os
import httpx
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("CELESTRAK_URL")

headers = {
    "User-Agent": "iola-orbit/1.0"
}


def fetch_tle():

    response = httpx.get(
        url,
        headers=headers,
        follow_redirects=True
    )

    tle_data = response.text

    with open("../data/active.tle", "w") as file:
        file.write(tle_data)

    lines = tle_data.strip().split("\n")

    satellite_count = len(lines) // 3

    print(
        f"TLE catalog refreshed: "
        f"{satellite_count} satellites"
    )


fetch_tle()