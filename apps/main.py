from fastapi import FastAPI
from .routers.health import router as health_router
from .routers.gmail_webhook import router as gmail_router
from .routers.crm import router as crm_router

app = FastAPI(title="StegOps Orchestrator", version="0.1.0")
app.include_router(health_router)
app.include_router(gmail_router, prefix="/v1/webhooks/gmail")
app.include_router(crm_router, prefix="/v1/crm")
