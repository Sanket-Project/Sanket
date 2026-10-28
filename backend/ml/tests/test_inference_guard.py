"""Distributed tenant admission stays owned by the actual compute thread."""

import uuid
from contextlib import contextmanager

import pytest


class Connection:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.calls = []

    def execution_options(self, **kwargs):
        self.options = kwargs
        return self

    def scalar(self, sql, params):
        self.calls.append((str(sql), params))
        return self.acquired


class Engine:
    def __init__(self, acquired=True):
        self.connection = Connection(acquired)

    @contextmanager
    def connect(self):
        yield self.connection


def test_session_lock_is_autocommit_and_released_after_compute_error():
    from sanket_ml.inference.guard import tenant_inference_slot
    engine = Engine()
    def compute():
        with tenant_inference_slot(engine, uuid.uuid4()):
            assert len(engine.connection.calls) == 1
            assert engine.connection.options == {"isolation_level": "AUTOCOMMIT"}
            raise ValueError("model failed")
    with pytest.raises(ValueError, match="model failed"):
        compute()
    assert "pg_try_advisory_lock" in engine.connection.calls[0][0]
    assert "pg_advisory_unlock" in engine.connection.calls[1][0]
    assert engine.connection.calls[0][1] == engine.connection.calls[1][1]


def test_contended_lock_rejects_without_unlocking_another_owner():
    from sanket_ml.inference.guard import TenantInferenceBusyError, tenant_inference_slot
    engine = Engine(acquired=False)
    with pytest.raises(TenantInferenceBusyError):
        with tenant_inference_slot(engine, uuid.uuid4()):
            pytest.fail("contended call entered inference")
    assert len(engine.connection.calls) == 1


def test_lock_key_is_stable_and_tenant_specific():
    from sanket_ml.inference.guard import tenant_inference_slot
    tenant = uuid.uuid4()
    keys = []
    for value in [tenant, tenant, uuid.uuid4()]:
        engine = Engine()
        with tenant_inference_slot(engine, value):
            keys.append(engine.connection.calls[0][1])
    assert keys[0] == keys[1]
    assert keys[0] != keys[2]
