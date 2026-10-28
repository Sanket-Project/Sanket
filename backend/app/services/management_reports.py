"""Factual management artifacts. No recipient or monetary figure comes from an LLM."""

from __future__ import annotations

import hashlib
import io
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape

from app.services.notifications.localization import translate

LANGUAGES = {"en", "hi", "te", "ta"}
TITLES = {
    "en": (
        "Management ROI report",
        "Not measurable yet",
        "Derived; do not add",
        "Sources",
        "Snapshot",
        "Selected period (days)",
    ),
    "hi": (
        "प्रबंधन आरओआई रिपोर्ट",
        "अभी मापना संभव नहीं",
        "व्युत्पन्न; जोड़ें नहीं",
        "स्रोत",
        "स्नैपशॉट",
        "चयनित अवधि (दिन)",
    ),
    "te": (
        "నిర్వహణ ఆర్ఓఐ నివేదిక",
        "ఇంకా కొలవలేము",
        "ఉత్పన్నం; కలపవద్దు",
        "మూలాలు",
        "స్నాప్‌షాట్",
        "ఎంచుకున్న కాలం (రోజులు)",
    ),
    "ta": (
        "நிர்வாக ஆர்ஓஐ அறிக்கை",
        "இன்னும் அளவிட முடியவில்லை",
        "பெறப்பட்டது; கூட்ட வேண்டாம்",
        "ஆதாரங்கள்",
        "தரவு நிலை",
        "தேர்ந்தெடுத்த காலம் (நாட்கள்)",
    ),
}
_FONT_LOCK = Lock()
_FONT_FILES = {
    "en": "NotoSans",
    "hi": "SanketReportSansDevanagari",
    "te": "SanketReportSansTelugu",
    "ta": "SanketReportSansTamil",
}


def _register_fonts(language):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    with _FONT_LOCK:
        for locale in {"en", language}:
            name = f"Sanket-{locale}"
            if name not in pdfmetrics.getRegisteredFontNames():
                filename = (
                    Path(__file__).parents[1]
                    / "assets"
                    / "fonts"
                    / f"{_FONT_FILES[locale]}-Regular.ttf"
                )
                pdfmetrics.registerFont(TTFont(name, str(filename), shapable=locale != "en"))


def pdf_markup(text: str, language: str) -> str:
    """One Latin/Indic font avoids glyph collisions across shaped font fragments."""
    _register_fonts(language)
    return f'<font name="Sanket-{language}">{escape(str(text))}</font>'


def _digest(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def _source_url(path):
    from app.config import get_settings

    # The origin is configured by the operator, never accepted from request/model data.
    return get_settings().billing_callback_base.rstrip("/") + path


def project_report(summary: dict, *, now: datetime | None = None) -> dict:
    """Copy the actual ROI ledger, preserving nulls and separate currencies/tiers."""
    report = deepcopy(
        {
            key: summary[key]
            for key in ("window_days", "currency", "currencies", "tiers", "lines", "caveat")
        }
    )
    if len(report["lines"]) > 100:
        raise ValueError("Report exceeds the supported size")
    report["snapshot"] = _digest(report)
    report["as_of"] = (now or datetime.now(UTC)).isoformat()
    report["sources"] = ["/workspace/roi", "/workspace/decisions"]
    report["label"] = "Factual report"
    return report


def report_email(report: dict, *, language="en") -> tuple[str, str]:
    if language not in LANGUAGES:
        raise ValueError("Unsupported language")
    title, missing, derived, sources, snapshot, period = TITLES[language]
    rows = [title, f"{snapshot}: {report['as_of']}", f"{period}: {report['window_days']}", ""]
    for tier in report["tiers"].values():
        rows.append(translate(tier["label"], language))
        for line in tier["lines"]:
            currencies = line.get("values_by_currency") or {}
            value = (
                "; ".join(f"{code} {amount:,.2f}" for code, amount in sorted(currencies.items()))
                if currencies
                else (
                    missing
                    if line["value"] is None
                    else f"{line['value']} {translate(line['unit'], language)}"
                )
            )
            rows.append(
                f"{translate(line['label'], language)}: {value}"
                + (f" ({derived})" if not line.get("additive", True) else "")
            )
            rows.append(translate(line["basis"], language))
        rows.append("")
    rows += [
        translate(report["caveat"], language),
        f"{sources}: " + ", ".join(_source_url(path) for path in report["sources"]),
    ]
    return title, "\n".join(rows)


def supplier_draft(rec, sku_code: str, *, language="en", now=None) -> dict:
    now = now or datetime.now(UTC)
    if language not in LANGUAGES:
        raise ValueError("Unsupported language")
    if (
        str(rec.kind) != "purchase_order"
        or str(rec.status) != "accepted"
        or rec.expires_at is not None
        and rec.expires_at <= now
        or rec.accepted_units is None
        or rec.accepted_units < 0
    ):
        raise ValueError(
            "An accepted, unexpired purchase-order recommendation with an approved quantity is required"
        )
    identity = {
        "id": str(rec.id),
        "sku_id": str(rec.sku_id),
        "sku_code": sku_code,
        "quantity": rec.accepted_units,
        "currency": rec.currency,
        "updated_at": rec.updated_at.isoformat(),
        "expires_at": str(rec.expires_at),
    }
    qty, currency = rec.accepted_units, rec.currency
    templates = {
        "en": (
            f"Purchase order request: {sku_code}",
            f"Please confirm availability and delivery for {qty} units of SKU {sku_code}. Currency: {currency}. Please provide a quotation and delivery date. This is a draft based on the approved recommendation; it does not record a supplier order.",
        ),
        "hi": (
            f"खरीद आदेश अनुरोध: {sku_code}",
            f"कृपया SKU {sku_code} की {qty} इकाइयों की उपलब्धता और डिलीवरी की पुष्टि करें। मुद्रा: {currency}। कृपया मूल्य प्रस्ताव और डिलीवरी की तारीख दें। यह स्वीकृत अनुशंसा पर आधारित मसौदा है; यह आपूर्तिकर्ता आदेश दर्ज नहीं करता।",
        ),
        "te": (
            f"కొనుగోలు ఆర్డర్ అభ్యర్థన: {sku_code}",
            f"దయచేసి SKU {sku_code} యొక్క {qty} యూనిట్ల లభ్యత మరియు డెలివరీని నిర్ధారించండి. కరెన్సీ: {currency}. దయచేసి ధర మరియు డెలివరీ తేదీని తెలియజేయండి. ఇది ఆమోదించిన సిఫార్సు ఆధారంగా రూపొందించిన ముసాయిదా; సరఫరాదారు ఆర్డర్‌ను నమోదు చేయదు.",
        ),
        "ta": (
            f"கொள்முதல் ஆணை கோரிக்கை: {sku_code}",
            f"SKU {sku_code} இன் {qty} அலகுகளின் இருப்பு மற்றும் விநியோகத்தை உறுதிப்படுத்தவும். நாணயம்: {currency}. விலை மற்றும் விநியோகத் தேதியை வழங்கவும். இது அங்கீகரிக்கப்பட்ட பரிந்துரையின் வரைவு; வழங்குநர் ஆணையைப் பதிவு செய்யாது.",
        ),
    }
    subject, body = templates[language]
    return {
        **identity,
        "revision": _digest(identity),
        "recipient": None,
        "subject": subject,
        "body": body,
        "whatsapp_text": body,
        "label": "Factual template",
        "source": "/workspace/decisions",
        "language": language,
    }


def render_report_pdf(report: dict, *, language="en") -> bytes:
    if language not in LANGUAGES:
        raise ValueError("Unsupported language")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    font = f"Sanket-{language}"
    _register_fonts(language)
    styles = {
        "title": ParagraphStyle(
            "title",
            fontName=font,
            fontSize=23,
            leading=33,
            textColor=colors.HexColor("#17352c"),
            spaceAfter=18,
            shaping=1,
        ),
        "heading": ParagraphStyle(
            "heading",
            fontName=font,
            fontSize=13,
            leading=21,
            textColor=colors.HexColor("#17352c"),
            spaceBefore=16,
            spaceAfter=7,
            shaping=1,
        ),
        "body": ParagraphStyle(
            "body", fontName=font, fontSize=9, leading=15, spaceAfter=7, shaping=1
        ),
        "source": ParagraphStyle(
            "source", fontName="Sanket-en", fontSize=9, leading=15, spaceAfter=7, shaping=0
        ),
    }
    title, missing, derived, sources, snapshot, period = TITLES[language]

    def paragraph(text, style="body"):
        return Paragraph(pdf_markup(text, language), styles[style])

    story = [
        paragraph(title, "title"),
        paragraph(f"{snapshot}: {report['as_of']}"),
        paragraph(f"{period}: {report['window_days']}"),
        Spacer(1, 8),
    ]
    for tier in report["tiers"].values():
        story.append(paragraph(translate(tier["label"], language), "heading"))
        for line in tier["lines"]:
            currencies = line.get("values_by_currency") or {}
            value = (
                "; ".join(f"{code} {amount:,.2f}" for code, amount in sorted(currencies.items()))
                if currencies
                else (
                    missing
                    if line["value"] is None
                    else f"{line['value']} {translate(line['unit'], language)}"
                )
            )
            label = f"{translate(line['label'], language)}: {value}" + (
                f" ({derived})" if not line.get("additive", True) else ""
            )
            story.append(
                KeepTogether([paragraph(label), paragraph(translate(line["basis"], language))])
            )
    story += [Spacer(1, 14), paragraph(translate(report["caveat"], language))]
    source_block = [paragraph(sources, "heading")]
    for path in report["sources"]:
        url = _source_url(path)
        source_block.append(
            Paragraph(
                f'<link href="{escape(url)}" color="#28785b">{escape(url)}</link>', styles["source"]
            )
        )
    story.append(KeepTogether(source_block))
    buf = io.BytesIO()
    SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=42,
        bottomMargin=42,
        title=title,
        author="SANKET",
        invariant=1,
    ).build(story)
    return buf.getvalue()


async def artifact_summary(db, ai, ctx, artifact, *, language="en") -> dict:
    """Only the ordering/selection is model-assisted; the ledger renders all facts."""
    from app.services.llm.context import Ledger
    from app.services.llm.facts import render_narrative
    from app.services.llm.policy import PolicyStore
    from app.services.llm.tasks import request_for

    policy = await PolicyStore(db).load(ctx)
    if not policy.enabled or not policy.task_enabled:
        return {"state": "disabled", "blocks": []}
    if policy.sharing == "disabled" or not policy.aggregate_context:
        return {"state": "policy_blocked", "blocks": []}
    if ai is None:
        return {"state": "unavailable", "blocks": []}
    ledger = Ledger()
    if ctx.task_name == "roi_report":
        for line in artifact["lines"]:
            currencies = line.get("values_by_currency") or {}
            if currencies:
                for code, amount in sorted(currencies.items()):
                    ledger.add(f"{line['key']}_{code}", line["label"], amount, code, "/roi")
            else:
                ledger.add(
                    line["key"],
                    line["label"],
                    line["value"],
                    "" if line["unit"] == "currency" else line["unit"],
                    "/roi",
                )
    else:
        # No supplier contact, recipient, SKU code, or free-form text reaches the provider.
        ledger.add(
            "approved_quantity",
            "Approved order quantity",
            artifact["quantity"],
            "units",
            "/decisions",
        )
    if not ledger.rows:
        return {"state": "unavailable", "blocks": []}
    data = ledger.finish(language)
    result = await ai.run(ctx, request_for(ctx.task_name, data.model_dump(mode="json")))
    return {
        "state": result.state,
        "label": "AI-generated",
        "snapshot": data.snapshot,
        "blocks": render_narrative(data, result.value) if result.state == "success" else [],
    }
