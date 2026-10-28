"""Reports preserve the ledger; supplier drafts never invent an order."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.management_reports import project_report, render_report_pdf, supplier_draft


def sample_summary():
    line = {
        "key": "realized",
        "label": "Realized savings",
        "value": None,
        "unit": "currency",
        "values_by_currency": {},
        "additive": False,
        "tier": "observed",
        "basis": "Not measured",
        "evidence_count": 0,
    }
    return {
        "window_days": 90,
        "currency": None,
        "currencies": ["INR", "USD"],
        "tiers": {
            "observed": {"label": "Observed outcomes", "status": "not_measurable", "lines": [line]}
        },
        "lines": [line],
        "caveat": "Approvals are not savings",
    }


def test_report_keeps_nulls_tiers_currencies_and_source():
    report = project_report(sample_summary(), now=datetime(2026, 10, 27, tzinfo=UTC))
    assert report["tiers"]["observed"]["lines"][0]["value"] is None
    assert report["currencies"] == ["INR", "USD"]
    assert report["sources"] == ["/workspace/roi", "/workspace/decisions"]
    assert report["window_days"] == 90
    assert report["snapshot"] == project_report(sample_summary())["snapshot"]
    assert "grand_total" not in report


def recommendation(**overrides):
    return SimpleNamespace(
        id=uuid.uuid4(),
        sku_id=uuid.uuid4(),
        kind="purchase_order",
        status="accepted",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        accepted_units=37,
        recommended_units=50,
        currency="INR",
        updated_at=datetime.now(UTC),
        **overrides,
    )


def test_supplier_uses_accepted_units_and_keeps_recipient_missing():
    draft = supplier_draft(recommendation(), "TEST-SKU")
    assert "37" in draft["body"]
    assert "50" not in draft["body"]
    assert draft["recipient"] is None
    assert draft["quantity"] == 37
    assert draft["source"].startswith("/workspace/decisions")
    assert draft["label"] == "Factual template"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "allocation"),
        ("status", "open"),
        ("expires_at", datetime.now(UTC) - timedelta(seconds=1)),
        ("accepted_units", None),
    ],
)
def test_supplier_rejects_ineligible_recommendation(field, value):
    rec = recommendation()
    setattr(rec, field, value)
    with pytest.raises(ValueError, match="accepted, unexpired"):
        supplier_draft(rec, "TEST-SKU")


def test_supplier_revision_changes_with_accepted_quantity():
    rec = recommendation()
    first = supplier_draft(rec, "TEST-SKU")
    rec.accepted_units = 38
    assert first["revision"] != supplier_draft(rec, "TEST-SKU")["revision"]


def test_pdf_has_valid_document_structure_and_links():
    content = render_report_pdf(project_report(sample_summary()), language="en")
    assert content.startswith(b"%PDF-")
    assert b"/URI" in content
    assert b"/workspace/roi" in content


def test_pdf_render_is_stable_for_idempotent_reviewed_delivery():
    report = project_report(sample_summary())
    assert render_report_pdf(report) == render_report_pdf(report)


def test_report_export_links_use_trusted_server_origin(monkeypatch):
    from app.config import get_settings
    from app.services.management_reports import report_email

    monkeypatch.setattr(get_settings(), "app_base_url", "https://synthetic.example.test")
    _, body = report_email(project_report(sample_summary()))
    assert "https://synthetic.example.test/workspace/roi" in body
    assert b"https://synthetic.example.test/workspace/roi" in render_report_pdf(
        project_report(sample_summary())
    )


def test_indic_pdf_text_keeps_latin_codes_and_source_urls_readable():
    from app.services.management_reports import pdf_markup

    for language in ("hi", "te", "ta"):
        marked = pdf_markup("INR 100.00 https://synthetic.example.test/workspace/roi", language)
        assert "INR" in marked
    assert "&lt;" in pdf_markup("<script>", "en")


def test_ascii_tokens_are_not_split_between_font_shaping_runs():
    from app.services.management_reports import pdf_markup

    marked = pdf_markup("P90 INR https://example.test/roi", "te")
    assert "P90 INR https://example.test/roi" in marked
    assert marked.count("<font ") == 1


def test_a_single_pdf_font_covers_each_complete_mixed_script_paragraph():
    from reportlab.pdfbase import pdfmetrics

    from app.services.management_reports import pdf_markup

    for language, sample in {
        "hi": "INR P90 (दिन)",
        "te": "INR P90 (రోజులు)",
        "ta": "INR P90 (நாட்கள்)",
    }.items():
        pdf_markup(sample, language)
        cmap = pdfmetrics.getFont(f"Sanket-{language}").face.charToGlyph
        assert all(ord(character) in cmap for character in sample), (language, sample)


async def test_report_ai_off_does_not_dispatch_provider(monkeypatch):
    from unittest.mock import AsyncMock

    from app.models.enums import IndustryCode
    from app.services.llm.policy import AIContext, Policy, PolicyStore
    from app.services.management_reports import artifact_summary

    monkeypatch.setattr(
        PolicyStore, "load", AsyncMock(return_value=Policy(False, False, "headers_only"))
    )
    ai = SimpleNamespace(run=AsyncMock())
    ctx = AIContext(uuid.uuid4(), uuid.uuid4(), IndustryCode.fashion, task_name="roi_report")
    result = await artifact_summary(None, ai, ctx, project_report(sample_summary()), language="en")
    assert result["state"] == "disabled"
    ai.run.assert_not_awaited()


async def test_supplier_model_selects_engine_fact_without_receiving_recipient(monkeypatch):
    from unittest.mock import AsyncMock

    from app.models.enums import IndustryCode
    from app.services.llm.facts import NarrativeOutput
    from app.services.llm.policy import AIContext, Policy, PolicyStore
    from app.services.management_reports import artifact_summary

    monkeypatch.setattr(
        PolicyStore, "load", AsyncMock(return_value=Policy(True, True, "headers_only", True))
    )
    ai = SimpleNamespace(
        run=AsyncMock(
            return_value=SimpleNamespace(
                state="success",
                reason=None,
                value=NarrativeOutput(
                    blocks=[{"proposition": "fact", "fact_ids": ["approved_quantity"]}]
                ),
            )
        )
    )
    ctx = AIContext(uuid.uuid4(), uuid.uuid4(), IndustryCode.fashion, task_name="supplier_draft")
    result = await artifact_summary(
        None, ai, ctx, supplier_draft(recommendation(), "TEST-SKU"), language="en"
    )
    assert result["state"] == "success"
    assert "37" in result["blocks"][0]["text"]
    sent = ai.run.call_args.args[1].input.model_dump_json()
    assert "recipient" not in sent
    assert "TEST-SKU" not in sent


def test_unknown_language_rejected():
    with pytest.raises(ValueError, match="Unsupported language"):
        render_report_pdf(project_report(sample_summary()), language="xx")


async def test_roi_download_is_authenticated_factual_and_not_cached(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    response = await client.get("/api/v1/export/roi.pdf?window_days=90", headers=headers)
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF-")
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]


async def test_roi_preview_requires_fresh_review_before_send(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    preview = await client.post(
        "/api/v1/management/roi/preview", headers=headers, json={"window_days": 90}
    )
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["report"]["label"] == "Factual report"
    denied = await client.post(
        "/api/v1/management/roi/email",
        headers=headers,
        json={
            "window_days": 90,
            "preview_token": data["preview_token"],
            "recipient": "synthetic@example.test",
            "subject": data["subject"],
            "body": data["body"],
            "delivery_key": "test-review",
            "confirm": False,
        },
    )
    assert denied.status_code == 409


async def test_report_preview_token_cannot_be_used_by_another_workspace(
    client, signed_in_workspace
):
    _, first = await signed_in_workspace()
    _, second = await signed_in_workspace()
    preview = await client.post("/api/v1/management/roi/preview", headers=first, json={})
    assert preview.status_code == 200, preview.text
    data = preview.json()
    response = await client.post(
        "/api/v1/management/roi/email",
        headers=second,
        json={
            "preview_token": data["preview_token"],
            "recipient": "synthetic@example.test",
            "subject": data["subject"],
            "body": data["body"],
            "delivery_key": "foreign-review",
            "confirm": True,
        },
    )
    assert response.status_code == 409


async def test_supplier_foreign_or_missing_recommendation_returns_404(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    response = await client.post(
        f"/api/v1/management/supplier/{uuid.uuid4()}/preview", headers=headers, json={}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Recommendation is unavailable"


async def _stored_order(session, tenant):
    from app.models.product import Product, Sku
    from app.models.recommendation import Recommendation

    product = Product(tenant_id=tenant, industry="fashion", name="Synthetic only", category="Test")
    session.add(product)
    await session.flush()
    sku = Sku(
        tenant_id=tenant,
        product_id=product.id,
        industry="fashion",
        sku_code=f"SYN-{uuid.uuid4().hex[:10]}",
        currency="INR",
    )
    session.add(sku)
    await session.flush()
    order = Recommendation(
        tenant_id=tenant,
        industry="fashion",
        sku_id=sku.id,
        kind="purchase_order",
        status="accepted",
        urgency="normal",
        headline="Synthetic test only",
        recommended_units=50,
        accepted_units=37,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(order)
    await session.commit()
    return order


async def test_supplier_actual_rls_and_stale_review(
    app_role_db, db_session, signed_in_workspace, client
):
    from fastapi import HTTPException
    from sqlalchemy import select

    from app.models.tenant import User
    from app.routers.management_reports import current_draft

    first, headers = await signed_in_workspace()
    second, _ = await signed_in_workspace()
    order = await _stored_order(db_session, first)
    user_id = await db_session.scalar(select(User.id).where(User.tenant_id == first))
    foreign_user = await db_session.scalar(select(User.id).where(User.tenant_id == second))
    assert (await current_draft(app_role_db, first, user_id, "fashion", order.id, "en"))[
        "quantity"
    ] == 37
    with pytest.raises(HTTPException) as exc:
        await current_draft(app_role_db, second, foreign_user, "fashion", order.id, "en")
    assert exc.value.status_code == 404
    preview = await client.post(
        f"/api/v1/management/supplier/{order.id}/preview", headers=headers, json={}
    )
    assert preview.status_code == 200, preview.text
    data = preview.json()
    order.accepted_units = 38
    await db_session.commit()
    response = await client.post(
        f"/api/v1/management/supplier/{order.id}/email",
        headers=headers,
        json={
            "preview_token": data["preview_token"],
            "recipient": "synthetic@example.test",
            "subject": data["subject"],
            "body": data["body"],
            "delivery_key": "stale-supplier",
            "confirm": True,
        },
    )
    assert response.status_code == 409
    assert "Decision changed" in response.json()["detail"]


async def test_reviewed_roi_email_attaches_pdf_and_replay_does_not_redispatch(
    client, signed_in_workspace, monkeypatch
):
    from unittest.mock import Mock

    from app.config import get_settings

    _, headers = await signed_in_workspace()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "synthetic-mail-sink")
    monkeypatch.setattr(settings, "smtp_sender", "test@example.test")
    transport = Mock(return_value="sent")
    monkeypatch.setattr("app.services.notifications.communications.send_email", transport)
    preview = await client.post("/api/v1/management/roi/preview", headers=headers, json={})
    assert preview.status_code == 200, preview.text
    data = preview.json()
    message = {
        "preview_token": data["preview_token"],
        "recipient": "synthetic@example.test",
        "subject": data["subject"],
        "body": data["body"],
        "delivery_key": "synthetic-report",
        "confirm": True,
    }
    first = await client.post("/api/v1/management/roi/email", headers=headers, json=message)
    second = await client.post("/api/v1/management/roi/email", headers=headers, json=message)
    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert first.json()["state"] == second.json()["state"] == "sent"
    assert second.json()["replayed"] is True
    transport.assert_called_once()
    assert transport.call_args.args[4].startswith(b"%PDF-")


async def test_removed_member_gets_explicit_refusal_before_report_projection(monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from app.routers.management_reports import current_report

    @asynccontextmanager
    async def session(_):
        yield object()

    monkeypatch.setattr(
        "app.routers.management_reports.load_member",
        AsyncMock(side_effect=ValueError("Membership removed")),
    )
    with pytest.raises(HTTPException) as exc:
        await current_report(
            SimpleNamespace(session=session), uuid.uuid4(), uuid.uuid4(), "fashion", 90
        )
    assert exc.value.status_code == 403


async def test_supplier_revalidates_version_inside_delivery_claim(
    client, signed_in_workspace, db_session, monkeypatch
):
    from unittest.mock import Mock

    from app.config import get_settings
    from app.services.notifications.communications import deliver_email as actual_delivery

    tenant, headers = await signed_in_workspace()
    order = await _stored_order(db_session, tenant)
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "synthetic-mail-sink")
    monkeypatch.setattr(settings, "smtp_sender", "test@example.test")
    transport = Mock(return_value="sent")
    monkeypatch.setattr("app.services.notifications.communications.send_email", transport)
    preview = await client.post(
        f"/api/v1/management/supplier/{order.id}/preview", headers=headers, json={}
    )
    assert preview.status_code == 200, preview.text
    data = preview.json()

    async def change_between_check_and_claim(*args, **kwargs):
        order.accepted_units = 38
        await db_session.commit()
        return await actual_delivery(*args, **kwargs)

    monkeypatch.setattr(
        "app.routers.management_reports.deliver_email", change_between_check_and_claim
    )
    response = await client.post(
        f"/api/v1/management/supplier/{order.id}/email",
        headers=headers,
        json={
            "preview_token": data["preview_token"],
            "recipient": "synthetic@example.test",
            "subject": data["subject"],
            "body": data["body"],
            "delivery_key": "synthetic-race",
            "confirm": True,
        },
    )
    assert response.status_code == 409, response.text
    transport.assert_not_called()


@pytest.mark.parametrize("artifact", ["roi", "supplier"])
async def test_reviewed_artifact_api_delivers_to_actual_local_tls_sink(
    artifact, client, signed_in_workspace, db_session, tmp_path
):
    from email import policy
    from email.parser import BytesParser
    from unittest.mock import patch

    from test_email_sink import start_sink

    tenant, headers = await signed_in_workspace()
    if artifact == "supplier":
        order = await _stored_order(db_session, tenant)
        prefix = f"/api/v1/management/supplier/{order.id}"
    else:
        prefix = "/api/v1/management/roi"
    preview = await client.post(f"{prefix}/preview", headers=headers, json={})
    assert preview.status_code == 200, preview.text
    data = preview.json()
    config, client_context, captured, errors, thread = start_sink(tmp_path)
    with (
        patch("app.routers.management_reports.EmailConfig.from_settings", return_value=config),
        patch("ssl.create_default_context", return_value=client_context),
    ):
        response = await client.post(
            f"{prefix}/email",
            headers=headers,
            json={
                "preview_token": data["preview_token"],
                "recipient": "synthetic@example.test",
                "subject": data["subject"],
                "body": data["body"],
                "delivery_key": f"synthetic-tls-{artifact}",
                "confirm": True,
            },
        )
    thread.join(timeout=5)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "sent"
    assert not errors
    assert len(captured) == 1
    message = BytesParser(policy=policy.default).parsebytes(captured[0])
    assert message["To"] == "synthetic@example.test"
    body = message.get_body(preferencelist=("plain",)).get_content()
    if artifact == "supplier":
        assert "37 units" in body
        assert "50 units" not in body
        assert not list(message.iter_attachments())
    else:
        attachment = next(message.iter_attachments())
        assert attachment.get_content_type() == "application/pdf"
        assert attachment.get_payload(decode=True).startswith(b"%PDF-")
        assert "/workspace/roi" in body
        assert "Not measurable yet" in body
    (tmp_path / f"synthetic-{artifact}.eml").write_bytes(captured[0])
