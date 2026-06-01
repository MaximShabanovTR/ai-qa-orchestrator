from fastapi import FastAPI
from api.session_store import SessionStore
from api.routes import sessions
from orchestrator.pipeline import Pipeline

app = FastAPI(title="AI QA Orchestrator", version="0.1.0")

app.state.store = SessionStore()
app.state.pipeline = Pipeline()

app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
