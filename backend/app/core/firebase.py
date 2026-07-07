from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

# Firebase is not used in this project. All data resides in Postgres.
# MockFirestoreClient and other mocks have been removed to eliminate dummy data.


class _LazyFirebaseDB:
    def __getattr__(self, name):
        raise NotImplementedError("Firebase is disabled in this project. Use PostgreSQL instead.")


firebase_db = _LazyFirebaseDB()
