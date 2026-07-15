from fastapi import FastAPI

from launch_intel.api.routes import feedback, health, launches

app = FastAPI(title="Launch Intelligence API")

app.include_router(health.router)
app.include_router(launches.router)
app.include_router(feedback.router)
