import uuid


class SessionStore:
    def __init__(self) -> None:
        self._store: set[str] = set()

    def create(self) -> str:
        session_id = str(uuid.uuid4())
        self._store.add(session_id)
        return session_id

    def exists(self, session_id: str) -> bool:
        return session_id in self._store
    
    def delete(self, session_id: str) -> None:
        self._store.discard(session_id)