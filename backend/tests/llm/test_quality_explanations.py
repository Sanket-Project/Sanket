from dataclasses import replace

from test_rls import seed_workspace


async def test_quality_context_contains_real_findings_and_allowlisted_fix_actions(app_role_db):
    from app.services.llm.context import build_context
    ctx = replace(await seed_workspace(app_role_db), task_name="data_quality")
    data = await build_context(app_role_db, ctx)
    assert any(f.id == "health_score" for f in data.facts)
    assert any(f.id == "issues_found" for f in data.facts)
    assert all(f.source == "/data-quality" for f in data.facts)
    assert any(f.kind == "advice" for f in data.facts)
