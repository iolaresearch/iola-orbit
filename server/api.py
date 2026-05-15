from fastapi import FastAPI
from state import satellite_cache
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://orbit.ikirere.com", "https://iola-orbit.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/satellites")
def get_satellites():
    return satellite_cache