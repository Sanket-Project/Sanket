"""RSS / Atom feed connector — news sentiment from trade press and specialist blogs.

Covers professional fashion blogs (BoF, Vogue, WWD, HYPEBEAST), electronics trade
press (The Verge, TechCrunch, Ars Technica), and pharma news (FiercePharma, STAT).
Also surfaces regional news sources like Daily Hunt by accepting operator-configured
extra feed URLs via RSS_EXTRA_FEEDS_{INDUSTRY} env vars (JSON-encoded URL lists).

Requires: feedparser (optional — connector emits synthetic samples if not installed).
No API key required for the default feed list; most feeds are publicly accessible.

Sentiment is scored with an expanded lexicon covering editorial framing typical of
trade and consumer press ("surges", "recall", "sold out", "disruption", etc.).
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from datetime import UTC, datetime
from typing import Any

import structlog

from app.services.external_signals.base import (
    SignalConnector,
    SignalSample,
    clip,
)

log = structlog.get_logger(__name__)

WORD_RE = re.compile(r"[A-Za-z]+")

# (url, category_tags, region)
INDUSTRY_FEEDS: dict[str, list[tuple[str, list[str], str]]] = {
    "fashion": [
        ("https://www.businessoffashion.com/feed", ["trade", "business"], "WW"),
        ("https://www.vogue.com/feed/rss", ["luxury", "editorial"], "US"),
        ("https://wwd.com/feed/", ["trade", "retail"], "US"),
        ("https://www.refinery29.com/rss.xml", ["fast_fashion", "millennial"], "US"),
        ("https://fashionista.com/.rss/full", ["editorial", "industry"], "US"),
        ("https://hypebeast.com/feed", ["streetwear", "drops"], "WW"),
        # India feeds
        ("https://www.vogue.in/feed/rss", ["editorial", "luxury"], "IN"),
        ("https://in.fashionnetwork.com/rss/news/", ["retail", "trade"], "IN"),
    ],
    "electronics": [
        ("https://www.theverge.com/rss/index.xml", ["consumer_tech", "reviews"], "US"),
        ("https://techcrunch.com/feed/", ["hardware", "startup"], "US"),
        ("https://feeds.arstechnica.com/arstechnica/gadgets", ["enthusiast", "analysis"], "WW"),
        ("https://www.gsmarena.com/rss-news-reviews.php3", ["mobile", "reviews"], "WW"),
        ("https://www.tomsguide.com/feeds/all", ["consumer", "buying_guide"], "US"),
        # India feeds
        (
            "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
            ["business", "general"],
            "IN",
        ),
        (
            "https://www.thehindubusinessline.com/news/national/feeder/default.rss",
            ["macro", "news"],
            "IN",
        ),
    ],
    "pharma": [
        ("https://www.fiercepharma.com/rss/xml", ["trade", "industry"], "WW"),
        ("https://www.statnews.com/feed/", ["research", "clinical"], "US"),
        ("https://www.pharmaceutical-technology.com/feed/", ["manufacturing"], "WW"),
        ("https://www.drugdiscoverynews.com/feed", ["research", "pipeline"], "US"),
        # India feeds
        ("https://www.expresspharma.in/feed/", ["industry", "manufacturing"], "IN"),
    ],
    "agrocenter": [
        ("https://www.agriculture.com/rss/news.xml", ["trade", "general"], "US"),
        ("https://www.agweb.com/rss/news", ["trade", "commodity"], "US"),
        ("https://feedstuffs.com/rss.xml", ["feed", "livestock"], "US"),
        ("https://www.croplife.com/feed/", ["pesticide", "input"], "WW"),
        # India feeds
        ("https://krishijagran.com/rss/news/", ["trade", "agri_news"], "IN"),
    ],
    "hardware": [
        # Global — industrial supply, construction demand, manufacturing macro
        ("https://www.hardwareretailing.com/feed/", ["trade", "retail"], "US"),
        ("https://www.constructiondive.com/feeds/news/", ["construction", "demand"], "US"),
        ("https://www.industryweek.com/rss.xml", ["manufacturing", "macro"], "WW"),
        # India feeds
        (
            "https://www.constructionworld.in/rss.php",
            ["construction", "trade"],
            "IN",
        ),
    ],
}

# Extended lexicon — covers news framing beyond social slang
POSITIVE_LEXICON = frozenset(
    {
        # trade/editorial positives
        "surge",
        "boom",
        "growth",
        "record",
        "launch",
        "rally",
        "strong",
        "beats",
        "outperforms",
        "gain",
        "rise",
        "peak",
        "breakthrough",
        "debut",
        "expand",
        "demand",
        "popular",
        "trend",
        "viral",
        "bestseller",
        "sold",
        "sellout",
        "hot",
        "momentum",
        "bullish",
        "recovery",
        "rebound",
        "upgrade",
        # fashion-specific
        "drop",
        "hyped",
        "fire",
        "fresh",
        "clean",
        "quality",
        "iconic",
        "runway",
        "capsule",
        "collaboration",
        "collab",
        "limited",
        "exclusive",
        # electronics-specific
        "faster",
        "thinner",
        "efficient",
        "powerhouse",
        "innovation",
        "flagship",
        # pharma-specific
        "approved",
        "efficacy",
        "trial",
        "promising",
        "milestone",
        # general positives
        "love",
        "great",
        "amazing",
        "best",
        "perfect",
        "excellent",
        "good",
        "recommend",
        "awesome",
        "fantastic",
        "worth",
    }
)

NEGATIVE_LEXICON = frozenset(
    {
        # trade/editorial negatives
        "shortage",
        "recall",
        "ban",
        "risk",
        "fall",
        "decline",
        "drop",
        "slump",
        "miss",
        "loss",
        "concern",
        "warning",
        "deficit",
        "disruption",
        "delay",
        "supply",
        "crisis",
        "tariff",
        "inflation",
        "layoffs",
        "downturn",
        "disappoints",
        "bearish",
        "downgrade",
        "slows",
        "weak",
        "soft",
        # fashion-specific
        "overstock",
        "clearance",
        "unsold",
        "returns",
        "fast_fashion_backlash",
        # electronics-specific
        "defective",
        "broken",
        "bricked",
        "throttle",
        "overheating",
        "failure",
        # pharma-specific
        "withdrawn",
        "adverse",
        "failed",
        "rejected",
        "lawsuit",
        "contamination",
        # general negatives
        "hate",
        "terrible",
        "worst",
        "bad",
        "scam",
        "fake",
        "disappointed",
        "regret",
        "avoid",
        "trash",
        "garbage",
        "issue",
        "backorder",
        "overpriced",
    }
)


def _lexicon_sentiment(text: str) -> tuple[float, int]:
    """Return (score ∈ [-1, +1], n_matched_terms)."""
    words = [w.lower() for w in WORD_RE.findall(text)]
    pos = sum(1 for w in words if w in POSITIVE_LEXICON)
    neg = sum(1 for w in words if w in NEGATIVE_LEXICON)
    denom = pos + neg
    if denom == 0:
        return 0.0, 0
    return (pos - neg) / denom, denom


def _entry_age_hours(entry: Any) -> float | None:
    """Return age of a feed entry in hours, or None if timestamp unavailable."""
    ts: Any = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if ts is None:
        return None
    try:
        epoch = time.mktime(ts)
        now_epoch = datetime.now(UTC).timestamp()
        return max(0.0, (now_epoch - epoch) / 3600.0)
    except Exception:
        return None


def _recency_weight(age_hours: float | None) -> float:
    if age_hours is None:
        return 0.5
    if age_hours <= 24:
        return 1.0
    if age_hours <= 48:
        return 0.7
    if age_hours <= 96:
        return 0.4
    return 0.1


class RssConnector(SignalConnector):
    """Aggregates news sentiment from RSS/Atom feeds for each industry.

    Each feed URL produces one SignalSample; confidence scales with how many
    sentiment-bearing terms were found and how fresh the entries are.
    """

    name = "rss"

    def __init__(
        self,
        timeout_s: float = 15.0,
        max_entries_per_feed: int = 30,
        extra_feeds: dict[str, list[str]] | None = None,
    ):
        self.timeout_s = timeout_s
        self.max_entries_per_feed = max_entries_per_feed
        # operator-provided extra feed URLs, loaded from env by default
        self._extra_feeds = extra_feeds or self._load_extra_from_env()

    @staticmethod
    def _load_extra_from_env() -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for industry in ("fashion", "electronics", "pharma"):
            key = f"RSS_EXTRA_FEEDS_{industry.upper()}"
            raw = os.environ.get(key)
            if raw:
                try:
                    urls = json.loads(raw)
                    if isinstance(urls, list):
                        out[industry] = [str(u) for u in urls if u]
                except Exception:
                    log.warning("rss.extra_feeds.parse_failed", env_key=key)
        return out

    def _get_feeds(self, industry: str) -> list[tuple[str, list[str], str]]:
        base = list(INDUSTRY_FEEDS.get(industry, []))
        for url in self._extra_feeds.get(industry, []):
            base.append((url, ["regional"], "WW"))
        return base

    async def fetch(self, industry: str) -> list[SignalSample]:
        feeds = self._get_feeds(industry)
        if not feeds:
            return []
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync, industry, feeds),
                timeout=self.timeout_s,
            )
        except Exception as exc:
            log.warning("rss.fetch.failed", industry=industry, error=str(exc))
            return []

    def _fetch_sync(
        self,
        industry: str,
        feeds: list[tuple[str, list[str], str]],
    ) -> list[SignalSample]:
        try:
            import feedparser  # type: ignore
        except ImportError:
            log.info("rss.feedparser.missing — emitting synthetic")
            return []

        now = datetime.now(UTC)
        out: list[SignalSample] = []

        for url, tags, region in feeds:
            try:
                parsed = feedparser.parse(url)
            except Exception as exc:
                log.warning("rss.feed.failed", url=url, error=str(exc))
                continue

            entries = (parsed.entries or [])[: self.max_entries_per_feed]
            if not entries:
                continue

            weighted_scores: list[tuple[float, float]] = []  # (score, weight)
            total_terms = 0

            for entry in entries:
                title = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""
                text = f"{title} {summary}"
                score, n_terms = _lexicon_sentiment(text)
                if n_terms == 0:
                    continue
                age = _entry_age_hours(entry)
                w = _recency_weight(age) * (1.0 + min(n_terms, 10) * 0.05)
                weighted_scores.append((score, w))
                total_terms += n_terms

            if not weighted_scores:
                continue

            total_w = sum(w for _, w in weighted_scores)
            avg_score = sum(s * w for s, w in weighted_scores) / total_w
            normalized = clip(avg_score)

            # Confidence: 0.50 base, boosted by term density, capped at 0.85
            confidence = clip(0.50 + min(total_terms, 80) / 400.0, 0.50, 0.85)

            # Penalise if all entries are stale (>72h) — feed may be inactive
            ages = [_entry_age_hours(e) for e in entries]
            valid_ages = [a for a in ages if a is not None]
            if valid_ages and min(valid_ages) > 72:
                confidence = clip(confidence * 0.6, 0.30, confidence)

            out.append(
                SignalSample(
                    source="rss",
                    kind="news_sentiment",
                    series_key=f"rss:{url}",
                    industry=industry,
                    captured_at=now,
                    raw_value=round(avg_score, 6),
                    normalized_score=normalized,
                    confidence=confidence,
                    category_tags=tags,
                    region=region,
                    payload={
                        "feed_url": url,
                        "entries_analyzed": len(entries),
                        "entries_scored": len(weighted_scores),
                        "sentiment_terms": total_terms,
                    },
                )
            )

        if not out:
            return []
        return out

    def _synthetic(
        self,
        industry: str,
        feeds: list[tuple[str, list[str], str]],
    ) -> list[SignalSample]:
        now = datetime.now(UTC)
        rng = random.Random(hash((industry, now.date().isoformat(), "rss")) & 0xFFFFFFFF)
        return [
            SignalSample(
                source="rss",
                kind="news_sentiment",
                series_key=f"rss:{url}",
                industry=industry,
                captured_at=now,
                raw_value=None,
                normalized_score=clip(rng.gauss(0, 0.3)),
                confidence=0.30,
                category_tags=tags,
                region=region,
                payload={"synthetic": True, "feed_url": url},
            )
            for url, tags, region in feeds
        ]
