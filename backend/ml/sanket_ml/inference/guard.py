"""Cross-replica tenant lock, owned by the synchronous inference thread.

Session locks use an autocommit connection: long inference never leaves an
idle transaction open. A disconnected HTTP caller cannot release this lock
while its compute thread is still running. PostgreSQL releases it if the ML
process dies.
"""

import uuid
from contextlib import contextmanager
from hashlib import blake2b

from sqlalchemy import text


class TenantInferenceBusyError(Exception):
    """This tenant already has inference executing on an ML replica."""


@contextmanager
def tenant_inference_slot(engine, tenant_id: uuid.UUID):
    key = int.from_bytes(
        blake2b(b"sanket:forecast:" + tenant_id.bytes, digest_size=8).digest(),
        byteorder="big", signed=True,
    )
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        params = {"key": key}
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), params)
        if not acquired:
            raise TenantInferenceBusyError("A forecast is already running for this tenant")
        try:
            yield
        finally:
            try:
                connection.scalar(text("SELECT pg_advisory_unlock(:key)"), params)
            except BaseException:
                # Never return a connection holding a session lock to the pool.
                connection.invalidate()
                raise
