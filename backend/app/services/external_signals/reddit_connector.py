"""Reddit social-sentiment connector.

Polls relevant subreddits' new posts and runs a lightweight lexicon
sentiment score per industry. Uses PRAW if `REDDIT_CLIENT_ID` and
`REDDIT_CLIENT_SECRET` are configured; otherwise emits synthetic samples.

This deliberately uses a dictionary-based scoring (not a heavy NLP model)
because we want every connector to run in <2s and stay free of GPU.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
from datetime import UTC, datetime

import structlog

from app.services.external_signals.base import (
    SignalConnector,
    SignalSample,
    clip,
)

log = structlog.get_logger(__name__)


# Industry → list of (subreddit, category_tags)
INDUSTRY_SUBREDDITS: dict[str, list[tuple[str, list[str]]]] = {
    "fashion": [
        ("malefashionadvice", ["mens", "general"]),
        ("femalefashionadvice", ["womens", "general"]),
        ("sneakers", ["footwear"]),
        ("streetwear", ["streetwear"]),
    ],
    "electronics": [
        ("gadgets", ["general"]),
        ("buildapc", ["computing"]),
        ("hometheater", ["av"]),
        ("headphones", ["audio"]),
    ],
    "pharma": [
        ("pharmacy", ["industry"]),
        ("medicine", ["clinical"]),
        ("supplements", ["otc"]),
    ],
    "agrocenter": [
        ("farming", ["general", "crop"]),
        ("agriculture", ["general", "trade"]),
        ("homesteading", ["smallholder"]),
        ("pesticides", ["pesticide", "input"]),
    ],
    "hardware": [
        ("Tools", ["power_tool", "general"]),
        ("HomeImprovement", ["diy", "demand"]),
        ("electricians", ["trade", "electrical"]),
        ("Construction", ["trade", "construction"]),
    ],
}


POSITIVE_LEXICON = {
    "love",
    "great",
    "amazing",
    "best",
    "perfect",
    "excellent",
    "good",
    "favorite",
    "recommend",
    "awesome",
    "fantastic",
    "happy",
    "worth",
    "fire",
    "clean",
    "fresh",
    "quality",
    "trending",
    "popular",
    "hyped",
    "drop",
}
NEGATIVE_LEXICON = {
    "hate",
    "terrible",
    "worst",
    "bad",
    "broken",
    "defective",
    "scam",
    "fake",
    "disappointed",
    "regret",
    "avoid",
    "trash",
    "garbage",
    "issue",
    "recall",
    "shortage",
    "delayed",
    "backorder",
    "expensive",
    "overpriced",
}

WORD_RE = re.compile(r"[A-Za-z]+")


def lexicon_sentiment(text: str) -> tuple[float, int]:
    """Return (score in [-1, +1], n_terms)."""
    if not text:
        return 0.0, 0
    words = [w.lower() for w in WORD_RE.findall(text)]
    if not words:
        return 0.0, 0
    pos = sum(1 for w in words if w in POSITIVE_LEXICON)
    neg = sum(1 for w in words if w in NEGATIVE_LEXICON)
    denom = pos + neg
    if denom == 0:
        return 0.0, 0
    return (pos - neg) / denom, denom


class RedditConnector(SignalConnector):
    name = "reddit"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str = "sanket-platform/1.0 by sanket-signals",
        timeout_s: float = 10.0,
        posts_per_sub: int = 50,
    ):
        self.client_id = client_id or os.environ.get("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("REDDIT_CLIENT_SECRET")
        self.user_agent = user_agent
        self.timeout_s = timeout_s
        self.posts_per_sub = posts_per_sub

    async def fetch(self, industry: str) -> list[SignalSample]:
        subs = INDUSTRY_SUBREDDITS.get(industry, [])
        if not subs:
            return []
        if not (self.client_id and self.client_secret):
            return []
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync, industry, subs),
                timeout=self.timeout_s,
            )
        except Exception as exc:
            log.warning("reddit.fetch.failed", industry=industry, error=str(exc))
            return []

    def _fetch_sync(
        self,
        industry: str,
        subs: list[tuple[str, list[str]]],
    ) -> list[SignalSample]:
        try:
            import praw  # type: ignore
        except ImportError:
            log.info("reddit.praw.missing — emitting synthetic")
            return []

        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
            check_for_async=False,
        )
        reddit.read_only = True
        out: list[SignalSample] = []
        now = datetime.now(UTC)

        for sub_name, tags in subs:
            try:
                subreddit = reddit.subreddit(sub_name)
                posts = list(subreddit.new(limit=self.posts_per_sub))
            except Exception as exc:
                log.warning("reddit.sub.failed", sub=sub_name, error=str(exc))
                continue

            if not posts:
                continue
            scores: list[float] = []
            total_terms = 0
            engagement_total = 0
            for post in posts:
                text = f"{post.title} {getattr(post, 'selftext', '')}"
                s, n = lexicon_sentiment(text)
                if n > 0:
                    scores.append(s)
                    total_terms += n
                engagement_total += int(getattr(post, "score", 0) or 0)

            if not scores:
                continue
            avg = sum(scores) / len(scores)
            engagement_factor = clip(engagement_total / max(self.posts_per_sub, 1) / 50, 0, 1)
            normalized = clip(avg * (0.6 + 0.4 * engagement_factor))

            out.append(
                SignalSample(
                    source="reddit",
                    kind="social_buzz",
                    series_key=f"reddit:r/{sub_name}",
                    industry=industry,
                    captured_at=now,
                    raw_value=avg,
                    normalized_score=normalized,
                    confidence=clip(0.4 + total_terms / 200, 0.4, 0.9),
                    category_tags=tags,
                    region="WW",
                    payload={
                        "subreddit": sub_name,
                        "posts_analyzed": len(posts),
                        "scored_posts": len(scores),
                        "sentiment_terms": total_terms,
                        "engagement_factor": round(engagement_factor, 4),
                    },
                )
            )
        if not out:
            return []
        return out

    def _synthetic(
        self,
        industry: str,
        subs: list[tuple[str, list[str]]],
    ) -> list[SignalSample]:
        now = datetime.now(UTC)
        rng = random.Random(hash((industry, now.date().isoformat(), "reddit")) & 0xFFFFFFFF)
        out: list[SignalSample] = []
        for sub_name, tags in subs:
            score = clip(rng.gauss(0, 0.4))
            out.append(
                SignalSample(
                    source="reddit",
                    kind="social_buzz",
                    series_key=f"reddit:r/{sub_name}",
                    industry=industry,
                    captured_at=now,
                    raw_value=None,
                    normalized_score=score,
                    confidence=0.35,
                    category_tags=tags,
                    region="WW",
                    payload={"synthetic": True, "subreddit": sub_name},
                )
            )
        return out
