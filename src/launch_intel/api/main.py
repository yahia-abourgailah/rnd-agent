from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from launch_intel.api.routes import feedback, health, insights, launches, monitoring
from launch_intel.api.security import require_api_key

app = FastAPI(title="Launch Intelligence API")

# The CRM dashboard (React/Next.js, built by the full-stack team) runs on a
# different origin and calls these endpoints from the browser — which the
# browser blocks unless the API opts in via CORS. Read-only GET API with no
# credentials, so any origin is fine in dev. Restrict allow_origins to the
# CRM's domain in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# /health stays open (liveness/monitoring). Everything that returns data is
# gated behind the API key.
_auth = [Depends(require_api_key)]

app.include_router(health.router)
app.include_router(launches.router, dependencies=_auth)
app.include_router(feedback.router, dependencies=_auth)
app.include_router(insights.router, dependencies=_auth)
app.include_router(monitoring.router, dependencies=_auth)
