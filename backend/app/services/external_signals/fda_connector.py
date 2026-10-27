"""FDA drug regulatory and safety signal connector.

Pulls global safety recalls from openFDA. Indian CDSCO alerts are not wired: there
is no machine-readable CDSCO feed, so no CDSCO sample is emitted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from app.services.external_signals.base import SignalConnector, SignalSample, clip

log = structlog.get_logger(__name__)

OPEN_FDA_RECALLS_URL = "https://api.fda.gov/drug/enforcement.json"


class FdaConnector(SignalConnector):
    """Fetches public recalls from openFDA and publishes a US compliance risk index."""

    name = "fda"

    async def fetch(self, industry: str) -> list[SignalSample]:
        # Regulatory safety signals only apply to the pharmaceutical vertical in SANKET
        if industry != "pharma":
            return []

        try:
            import httpx

            samples: list[SignalSample] = []
            now = datetime.now(UTC)

            # 1. Fetch Global FDA Recalls
            async with httpx.AsyncClient(timeout=12.0) as client:
                try:
                    resp = await client.get(
                        OPEN_FDA_RECALLS_URL,
                        params={
                            "search": 'classification:"Class I" OR classification:"Class II"',
                            "limit": 50,
                        },
                    )

                    if resp.status_code == 404:
                        # No recalls found (which is a perfect safety signal!)
                        samples.append(self._create_empty_recall_sample(industry, now))
                    else:
                        resp.raise_for_status()
                        data = resp.json()
                        fda_sample = self._parse_fda(data, industry, now)
                        if fda_sample:
                            samples.append(fda_sample)
                except Exception as exc:
                    log.warning("fda.api.failed", error=str(exc))

            return samples
        except ImportError:
            return []
        except Exception as exc:
            log.warning("fda.fetch.failed", industry=industry, error=str(exc))
            return []

    def _parse_fda(self, data: dict[str, Any], industry: str, now: datetime) -> SignalSample | None:
        results = data.get("results", [])
        if not results:
            return self._create_empty_recall_sample(industry, now)

        class_1_count = 0
        class_2_count = 0
        manufacturers = set()
        states = set()

        for item in results:
            classification = item.get("classification", "").strip()
            if classification == "Class I":
                class_1_count += 1
            elif classification == "Class II":
                class_2_count += 1

            firm = item.get("recalling_firm")
            if firm:
                manufacturers.add(firm)

            state = item.get("state")
            if state:
                states.add(state)

        # Compute dynamic FDA score:
        score = 0.8 - (0.25 * class_1_count + 0.10 * class_2_count)
        normalized = clip(score)

        return SignalSample(
            source="fda",
            kind="news_sentiment",
            series_key="fda:drug_recalls:risk_index",
            industry=industry,
            captured_at=now,
            raw_value=float(class_1_count + class_2_count),
            normalized_score=round(normalized, 4),
            confidence=0.95,
            category_tags=["regulatory", "compliance", "fda", "recalls"],
            region="US",
            payload={
                "class_1_recalls": class_1_count,
                "class_2_recalls": class_2_count,
                "total_recalls_analyzed": len(results),
                "unique_recalling_firms": list(manufacturers)[:10],
                "affected_states_count": len(states),
            },
        )

    def _create_empty_recall_sample(self, industry: str, now: datetime) -> SignalSample:
        return SignalSample(
            source="fda",
            kind="news_sentiment",
            series_key="fda:drug_recalls:risk_index",
            industry=industry,
            captured_at=now,
            raw_value=0.0,
            normalized_score=1.0,
            confidence=0.95,
            category_tags=["regulatory", "compliance", "fda", "recalls"],
            region="US",
            payload={
                "class_1_recalls": 0,
                "class_2_recalls": 0,
                "total_recalls_analyzed": 0,
                "msg": "No Class I or Class II drug recalls registered recently.",
            },
        )
