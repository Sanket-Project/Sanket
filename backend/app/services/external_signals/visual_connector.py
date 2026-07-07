"""Visual-platform signal connectors: Pinterest, TikTok, Instagram.

Pinterest — uses the Pinterest v5 REST API to measure search freshness for
industry-relevant keywords. Requires a Pinterest business OAuth2 Bearer token
(`PINTEREST_ACCESS_TOKEN`). Falls back to synthetic when unconfigured.

TikTok — synthetic only. The TikTok Research API requires formal academic or
business-program approval from TikTok; there is no general-access endpoint for
trending content. Wire in real data by overriding `_fetch_tiktok_real` once an
approved token is obtained.

Instagram — synthetic only. Meta's Graph API exposes per-account analytics but
not platform-wide trending topics. Requires a Business/Creator account with
approved permissions; wire in via `_fetch_instagram_real` once available.

All three connectors emit kind="social_buzz" so the TrendScorer's existing
social_buzz weight applies without any fusion-layer changes.
"""

from __future__ import annotations

import asyncio
import os
import random
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.services.external_signals.base import (
    SignalConnector,
    SignalSample,
    clip,
    z_to_score,
)

log = structlog.get_logger(__name__)

PINTEREST_BASE = "https://api.pinterest.com/v5"

# Industry-specific search terms — Pinterest skews towards aspirational/lifestyle
PINTEREST_KEYWORDS: dict[str, list[tuple[str, list[str]]]] = {
    "fashion": [
        ("summer outfits 2025", ["seasonal", "womens"]),
        ("streetwear aesthetic", ["streetwear"]),
        ("sustainable fashion", ["sustainable"]),
        ("sneakers style", ["footwear"]),
        ("minimalist wardrobe", ["lifestyle"]),
    ],
    "electronics": [
        ("smart home setup", ["iot", "home"]),
        ("gaming desk setup", ["gaming", "computing"]),
        ("wireless earbuds review", ["audio"]),
        ("home office tech", ["computing", "wfh"]),
    ],
    "pharma": [
        ("wellness morning routine", ["wellness"]),
        ("vitamins supplements guide", ["supplement"]),
        ("skincare routine steps", ["otc", "cosmetic"]),
        ("mental health tips", ["wellness", "otc"]),
    ],
    "agrocenter": [
        ("organic farming ideas", ["sustainable", "crop"]),
        ("vegetable garden planting", ["consumer", "seasonal"]),
        ("farm to table", ["lifestyle", "crop"]),
        ("backyard chickens", ["feed", "smallholder"]),
    ],
}

# TikTok trending hashtag seeds per industry (used for synthetic simulation)
TIKTOK_HASHTAGS: dict[str, list[tuple[str, list[str]]]] = {
    "fashion": [
        ("#OOTD", ["editorial", "general"]),
        ("#FashionTikTok", ["general"]),
        ("#SneakerHead", ["footwear"]),
        ("#ThriftFlip", ["sustainable", "resale"]),
        ("#FashionHaul", ["fast_fashion"]),
    ],
    "electronics": [
        ("#TechTok", ["general"]),
        ("#GamingSetup", ["gaming"]),
        ("#SmartHome", ["iot"]),
        ("#PhoneReview", ["mobile"]),
    ],
    "pharma": [
        ("#WellnessTok", ["wellness"]),
        ("#HealthTips", ["otc"]),
        ("#SkincareRoutine", ["cosmetic", "otc"]),
        ("#MentalHealthMatters", ["wellness"]),
    ],
    "agrocenter": [
        ("#FarmTok", ["general", "agriculture"]),
        ("#AgTech", ["technology", "input"]),
        ("#PlantingSeason", ["seasonal", "crop"]),
        ("#LivestockFarming", ["feed", "livestock"]),
    ],
}

# Instagram content keyword seeds per industry (used for synthetic simulation)
INSTAGRAM_KEYWORDS: dict[str, list[tuple[str, list[str]]]] = {
    "fashion": [
        ("fashion week", ["luxury", "trade"]),
        ("street style", ["streetwear"]),
        ("outfit of the day", ["general"]),
        ("sustainable brands", ["sustainable"]),
    ],
    "electronics": [
        ("unboxing", ["reviews", "consumer"]),
        ("tech review", ["reviews"]),
        ("gaming room", ["gaming"]),
    ],
    "pharma": [
        ("wellness lifestyle", ["wellness"]),
        ("skincare", ["cosmetic", "otc"]),
        ("healthy living", ["wellness"]),
    ],
    "agrocenter": [
        ("harvest season", ["seasonal", "crop"]),
        ("sustainable agriculture", ["sustainable", "general"]),
        ("farm inputs supply", ["pesticide", "fertilizer"]),
    ],
}


# ── Pinterest ─────────────────────────────────────────────────────────────────


class PinterestConnector(SignalConnector):
    """Measures trend momentum on Pinterest via search-result freshness scoring.

    For each keyword, we query `/v5/search/pins` and compute the ratio of pins
    created in the last 7 days vs the last 30 days.  A rising ratio signals
    accelerating interest; a falling ratio signals cooling.

    freshness_ratio ∈ [0, 1]; mapped to [-1, +1] via tanh centred at 0.30
    (expected baseline share for a flat trend).
    """

    name = "pinterest"

    def __init__(
        self,
        access_token: str | None = None,
        timeout_s: float = 12.0,
        results_per_keyword: int = 50,
    ):
        self.access_token = access_token or os.environ.get("PINTEREST_ACCESS_TOKEN")
        self.timeout_s = timeout_s
        self.results_per_keyword = results_per_keyword

    async def fetch(self, industry: str) -> list[SignalSample]:
        keywords = PINTEREST_KEYWORDS.get(industry, [])
        if not keywords:
            return []
        if not self.access_token:
            return []
        try:
            return await asyncio.wait_for(
                self._fetch_async(industry, keywords),
                timeout=self.timeout_s,
            )
        except Exception as exc:
            log.warning("pinterest.fetch.failed", industry=industry, error=str(exc))
            return []

    async def _fetch_async(
        self,
        industry: str,
        keywords: list[tuple[str, list[str]]],
    ) -> list[SignalSample]:
        try:
            import httpx
        except ImportError:
            return []

        now = datetime.now(UTC)
        cutoff_7d = now - timedelta(days=7)
        cutoff_30d = now - timedelta(days=30)
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        out: list[SignalSample] = []

        async with httpx.AsyncClient(headers=headers, timeout=self.timeout_s) as client:
            for kw, tags in keywords:
                try:
                    resp = await client.get(
                        f"{PINTEREST_BASE}/search/pins",
                        params={"query": kw, "count": self.results_per_keyword},
                    )
                    if resp.status_code == 401:
                        log.warning("pinterest.auth.failed — token invalid or expired")
                        return []
                    if resp.status_code != 200:
                        log.debug("pinterest.search.non200", status=resp.status_code, kw=kw)
                        continue
                    items: list[dict[str, Any]] = resp.json().get("items", [])
                except Exception as exc:
                    log.debug("pinterest.kw.failed", kw=kw, error=str(exc))
                    continue

                count_7d = count_30d = 0
                for pin in items:
                    created_raw = pin.get("created_at") or pin.get("created_time")
                    if not created_raw:
                        continue
                    try:
                        created = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
                        if created >= cutoff_30d:
                            count_30d += 1
                            if created >= cutoff_7d:
                                count_7d += 1
                    except Exception:
                        continue

                if count_30d == 0:
                    continue

                freshness_ratio = count_7d / count_30d
                # tanh centred at 0.30 (flat-trend baseline for a 7/30-day share)
                score = clip(z_to_score((freshness_ratio - 0.30) / 0.15, scale=1.0))
                confidence = clip(0.50 + min(count_30d, 50) / 200.0, 0.50, 0.80)

                out.append(
                    SignalSample(
                        source="pinterest",
                        kind="social_buzz",
                        series_key=f"pinterest:{kw.replace(' ', '_')}",
                        industry=industry,
                        captured_at=now,
                        raw_value=round(freshness_ratio, 6),
                        normalized_score=score,
                        confidence=confidence,
                        category_tags=tags,
                        region="WW",
                        payload={
                            "keyword": kw,
                            "pins_7d": count_7d,
                            "pins_30d": count_30d,
                            "freshness_ratio": round(freshness_ratio, 4),
                        },
                    )
                )

        if not out:
            return []
        return out

    def _synthetic(
        self,
        industry: str,
        keywords: list[tuple[str, list[str]]],
    ) -> list[SignalSample]:
        now = datetime.now(UTC)
        rng = random.Random(hash((industry, now.date().isoformat(), "pinterest")) & 0xFFFFFFFF)
        return [
            SignalSample(
                source="pinterest",
                kind="social_buzz",
                series_key=f"pinterest:{kw.replace(' ', '_')}",
                industry=industry,
                captured_at=now,
                raw_value=None,
                normalized_score=clip(rng.gauss(0, 0.35)),
                confidence=0.30,
                category_tags=tags,
                region="WW",
                payload={"synthetic": True, "keyword": kw},
            )
            for kw, tags in keywords
        ]


# ── TikTok ────────────────────────────────────────────────────────────────────


class TikTokConnector(SignalConnector):
    """TikTok trend signals — currently synthetic.

    The TikTok Research API (research.tiktok.com) requires formal academic or
    business-program approval; there is no open endpoint for trending hashtag
    metrics. When an approved token becomes available, implement `_fetch_real`
    using the `/research/hashtag/query/` endpoint and wire it into `fetch`.
    """

    name = "tiktok"

    def __init__(self, access_token: str | None = None):
        # Future: read from TIKTOK_ACCESS_TOKEN once approved
        self.access_token = access_token or os.environ.get("TIKTOK_ACCESS_TOKEN")

    async def fetch(self, industry: str) -> list[SignalSample]:
        hashtags = TIKTOK_HASHTAGS.get(industry, [])
        if not hashtags:
            return []
        # Real implementation would call _fetch_real when access_token is set.
        # Until TikTok Research API access is granted, emit synthetic samples.
        return []

    def _synthetic(
        self,
        industry: str,
        hashtags: list[tuple[str, list[str]]],
    ) -> list[SignalSample]:
        now = datetime.now(UTC)
        # Fashion and electronics trend higher on TikTok → bias synthetic upward
        industry_bias = {"fashion": 0.15, "electronics": 0.10, "pharma": -0.05}
        bias = industry_bias.get(industry, 0.0)
        rng = random.Random(hash((industry, now.date().isoformat(), "tiktok")) & 0xFFFFFFFF)
        return [
            SignalSample(
                source="tiktok",
                kind="social_buzz",
                series_key=f"tiktok:{tag.lstrip('#').lower()}",
                industry=industry,
                captured_at=now,
                raw_value=None,
                normalized_score=clip(rng.gauss(bias, 0.40)),
                confidence=0.25,
                category_tags=tags,
                region="WW",
                payload={"synthetic": True, "hashtag": tag},
            )
            for tag, tags in hashtags
        ]


# ── Instagram ─────────────────────────────────────────────────────────────────


class InstagramConnector(SignalConnector):
    """Instagram engagement signals — currently synthetic.

    Meta's Graph API exposes per-business-account analytics (impressions, reach,
    engagement) but not platform-wide trending topics or hashtag volumes. A
    business account with `instagram_basic`, `pages_read_engagement`, and
    `instagram_manage_insights` permissions can surface account-level data; that
    can be wired into `_fetch_real` when available. Hashtag search via
    `/ig_hashtag_search` + `/media_count` is available but rate-limited to
    30 unique hashtags per account per week, making it unsuitable for a 15-min
    polling pipeline without careful quota management.
    """

    name = "instagram"

    def __init__(self, access_token: str | None = None):
        # Future: read from INSTAGRAM_ACCESS_TOKEN once a business account is wired
        self.access_token = access_token or os.environ.get("INSTAGRAM_ACCESS_TOKEN")

    async def fetch(self, industry: str) -> list[SignalSample]:
        keywords = INSTAGRAM_KEYWORDS.get(industry, [])
        if not keywords:
            return []
        return []

    def _synthetic(
        self,
        industry: str,
        keywords: list[tuple[str, list[str]]],
    ) -> list[SignalSample]:
        now = datetime.now(UTC)
        rng = random.Random(hash((industry, now.date().isoformat(), "instagram")) & 0xFFFFFFFF)
        return [
            SignalSample(
                source="instagram",
                kind="social_buzz",
                series_key=f"instagram:{kw.replace(' ', '_')}",
                industry=industry,
                captured_at=now,
                raw_value=None,
                normalized_score=clip(rng.gauss(0, 0.30)),
                confidence=0.25,
                category_tags=tags,
                region="WW",
                payload={"synthetic": True, "keyword": kw},
            )
            for kw, tags in keywords
        ]
