"""RSS news feed collector."""

import hashlib
import logging
from datetime import datetime

import feedparser
import httpx

from collectors.base import BaseCollector
from config import NEWS_FEEDS, NEWS_POLL_INTERVAL, GEO_KEYWORDS, HTTP_TIMEOUT, HTTP_USER_AGENT
from ws_manager import manager

logger = logging.getLogger(__name__)

# In-memory store
seen_hashes: set[str] = set()
articles_cache: list[dict] = []
MAX_CACHE = 200


def geo_tag(text: str) -> tuple[str | None, float | None, float | None]:
    """Extract geo info from text using keyword matching."""
    text_lower = text.lower()
    for keyword, val in GEO_KEYWORDS.items():
        if val is None:
            continue
        if keyword.lower() in text_lower:
            return val[2], val[0], val[1]
    return None, None, None


class NewsCollector(BaseCollector):
    def __init__(self):
        super().__init__("news", NEWS_POLL_INTERVAL)
        self.db_session_factory = None

    def set_db(self, session_factory):
        self.db_session_factory = session_factory

    async def collect(self):
        new_articles = []
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True, headers={"User-Agent": HTTP_USER_AGENT}) as client:
            for source, url in NEWS_FEEDS.items():
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning(f"[news] {source} returned {resp.status_code}")
                        continue
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:20]:
                        url_hash = hashlib.sha256(entry.get("link", "").encode()).hexdigest()[:16]
                        if url_hash in seen_hashes:
                            continue
                        seen_hashes.add(url_hash)

                        title = entry.get("title", "")
                        summary = entry.get("summary", entry.get("description", ""))
                        # Strip HTML tags from summary
                        import re
                        summary = re.sub(r'<[^>]+>', '', summary)[:300]

                        published = entry.get("published", "")
                        link = entry.get("link", "")

                        region, lat, lon = geo_tag(title + " " + summary)

                        from scoring import score_text
                        threat_score = score_text(title + " " + summary)

                        article = {
                            "url_hash": url_hash,
                            "title": title,
                            "summary": summary,
                            "source": source,
                            "url": link,
                            "published": published,
                            "geo_region": region,
                            "geo_lat": lat,
                            "geo_lon": lon,
                            "threat_score": threat_score,
                            "collected_at": datetime.utcnow().isoformat(),
                        }
                        new_articles.append(article)

                except Exception as e:
                    logger.error(f"[news] Error fetching {source}: {e}")

        if new_articles:
            articles_cache.extend(new_articles)
            # Trim cache
            while len(articles_cache) > MAX_CACHE:
                articles_cache.pop(0)

            # Persist to DB if available
            if self.db_session_factory:
                try:
                    from database import Article
                    db = self.db_session_factory()
                    try:
                        for a in new_articles:
                            existing = db.query(Article).filter(Article.url_hash == a["url_hash"]).first()
                            if not existing:
                                db.add(Article(
                                    url_hash=a["url_hash"],
                                    title=a["title"],
                                    summary=a["summary"],
                                    source=a["source"],
                                    url=a["url"],
                                    published=a["published"],
                                    geo_region=a["geo_region"],
                                    geo_lat=a["geo_lat"],
                                    geo_lon=a["geo_lon"],
                                    threat_score=a["threat_score"],
                                ))
                        db.commit()
                    finally:
                        db.close()
                except Exception as e:
                    logger.error(f"[news] DB persist error: {e}")

            await manager.broadcast("news", new_articles)
            logger.info(f"[news] Broadcast {len(new_articles)} new articles")

            # Threat engine assessment
            import threat_engine
            for a in new_articles:
                try:
                    await threat_engine.assess("news", a["title"], a.get("summary", ""))
                except Exception as e:
                    logger.error(f"[news] Threat assess error: {e}")

        return new_articles
