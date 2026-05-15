import os
import time
import threading
import uvicorn
from api import app
from propagate import propagate_satellites
from fetch_tle import fetch_tle

def propagation_loop():
    while True:
        print("Updating satellite positions...")
        propagate_satellites()
        time.sleep(15)

def tle_refresh_loop():
    while True:
        print("Refreshing TLE catalog...")
        fetch_tle()
        time.sleep(7700)

fetch_tle()
propagate_satellites()

thread = threading.Thread(
    target=propagation_loop,
    daemon=True
)
thread.start()

tle_thread = threading.Thread(
    target=tle_refresh_loop,
    daemon=True
)
tle_thread.start()

uvicorn.run(app,
            host="0.0.0.0",
            port=int(os.getenv("PORT", 8000))
        )