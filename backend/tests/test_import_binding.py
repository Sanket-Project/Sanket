import uuid

import pytest


def test_analysis_token_is_bound_to_actor_workspace_file_and_kind():
    from app.services.integrations.import_profiles import issue_analysis, verify_analysis
    tid, uid = uuid.uuid4(), uuid.uuid4()
    token = issue_analysis("test-key-32-characters-long-123456", tid, uid, "sales", b"file", ["t1"])
    assert verify_analysis(token, "test-key-32-characters-long-123456", tid, uid, "sales", b"file")["tables"] == ["t1"]
    for changes in [{"tenant": uuid.uuid4()}, {"actor": uuid.uuid4()}, {"kind": "inventory"}, {"content": b"changed"}]:
        args = dict(tenant=tid, actor=uid, kind="sales", content=b"file")
        with pytest.raises(ValueError, match="analysis"):
            verify_analysis(token, "test-key-32-characters-long-123456", **{**args, **changes})
    with pytest.raises(ValueError):
        verify_analysis(token + "modified", "test-key-32-characters-long-123456", tid, uid, "sales", b"file")


def test_expired_analysis_never_imports():
    from app.services.integrations.import_profiles import issue_analysis, verify_analysis
    tid, uid = uuid.uuid4(), uuid.uuid4()
    token = issue_analysis("test-key-32-characters-long-123456", tid, uid, "sales", b"file", ["t1"], lifetime_s=-1)
    with pytest.raises(ValueError, match="analysis"):
        verify_analysis(token, "test-key-32-characters-long-123456", tid, uid, "sales", b"file")
