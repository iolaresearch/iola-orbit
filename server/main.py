import time
import threading
import uvicorn
from api import app
from propagate import propagate_satellites

def propagation_loop():
    while True:
        print("Updating satellite positions...")
        propagate_satellites()
        time.sleep(15)

thread = threading.Thread(
    target=propagation_loop,
    daemon=True
)
thread.start()

uvicorn.run(app,
            host="127.0.0.1",
            port=8000
        )