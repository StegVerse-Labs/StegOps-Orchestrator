from fastapi import FastAPI
from .routers.health import router as health_router
from .routers.gmail_webhook import router as gmail_webhook_router
from .routers.gmail_ops import router as gmail_ops_router
from .routers.auth_google import router as auth_google_router
from .routers.crm import router as crm_router

app = FastAPI(title="StegOps Orchestrator", version="0.2.0")

app.include_router(health_router)
app.include_router(auth_google_router, prefix="/v1/auth", tags=["auth"])
app.include_router(gmail_webhook_router, prefix="/v1/webhooks/gmail", tags=["gmail-webhook"])
app.include_router(gmail_ops_router, prefix="/v1/gmail", tags=["gmail"])
app.include_router(crm_router, prefix="/v1/crm", tags=["crm"])
