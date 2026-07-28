from fastapi import FastAPI

from launch_intel.api.routes import feedback, health, insights, launches, monitoring

app = FastAPI(title="Launch Intelligence API")

app.include_router(health.router)
app.include_router(launches.router)
app.include_router(feedback.router)
app.include_router(insights.router)
app.include_router(monitoring.router)
