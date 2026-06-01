import uuid
from orchestrator.session import Session


class SessionStore:
    def __init__(self) -> None:
        self._store: dict[str, Session] = {}

    def create(self, raw_input: str) -> tuple[str, Session]:
        session_id = str(uuid.uuid4())
        session = Session(raw_input=raw_input)
        self._store[session_id] = session
        return session_id, session

    def get(self, session_id: str) -> Session | None:
        return self._store.get(session_id)
