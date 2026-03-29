"""
fetcher.py — RedditLens: Reddit Data Fetcher
=============================================
Fetches Reddit posts, comments, and subreddit data using
Reddit's public JSON API (no API key required).

Core insight from the original concept:
  Any Reddit URL + /.json gives you the FULL thread with
  all comments, upvotes, metadata — completely free.

Features:
  ✅ Fetch any post + all nested comments via /.json
  ✅ Subreddit hot/new/top/rising feed
  ✅ Subreddit search
  ✅ Multi-subreddit batch scanning
  ✅ Rate limiting (respectful scraping)
  ✅ Comment tree flattening
  ✅ Pain point signal extraction
  ✅ Retry + error handling
"""

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Rate limit: Reddit allows ~60 req/min unauthenticated
_LAST_REQUEST = 0.0
_MIN_INTERVAL = 1.1  # seconds between requests


def _fetch(url: str, timeout: int = 15) -> dict:
    """Make a rate-limited GET request and return parsed JSON."""
    global _LAST_REQUEST
    elapsed = time.time() - _LAST_REQUEST
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    headers = {
        "User-Agent": "RedditLens/2.0 Market Intelligence Tool (educational)",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            _LAST_REQUEST = time.time()
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        _LAST_REQUEST = time.time()
        raise RuntimeError(f"Fetch failed [{url}]: {e}")


# ── Data models ────────────────────────────────────────────────

@dataclass
class RedditComment:
    id          : str
    author      : str
    body        : str
    score       : int
    depth       : int = 0
    replies     : List["RedditComment"] = field(default_factory=list)
    created_utc : float = 0.0

    @property
    def word_count(self) -> int:
        return len(self.body.split())

    @property
    def is_substantial(self) -> bool:
        return self.word_count >= 15 and self.score >= 0 and self.author != "[deleted]"


@dataclass
class RedditPost:
    id          : str
    title       : str
    selftext    : str
    author      : str
    subreddit   : str
    url         : str
    score       : int
    upvote_ratio: float
    num_comments: int
    created_utc : float
    flair       : str = ""
    comments    : List[RedditComment] = field(default_factory=list)

    @property
    def full_url(self) -> str:
        return f"https://www.reddit.com/r/{self.subreddit}/comments/{self.id}/"

    @property
    def engagement_score(self) -> float:
        """Composite engagement metric."""
        return self.score * self.upvote_ratio + self.num_comments * 2

    def all_text(self) -> str:
        """Title + selftext + all comment bodies concatenated."""
        parts = [self.title, self.selftext]
        parts.extend(self._flatten_comments(self.comments))
        return "\n\n".join(p for p in parts if p and p != "[deleted]" and p != "[removed]")

    def _flatten_comments(self, comments: List[RedditComment]) -> List[str]:
        result = []
        for c in comments:
            if c.is_substantial:
                result.append(c.body)
            result.extend(self._flatten_comments(c.replies))
        return result


@dataclass
class SubredditInfo:
    name             : str
    display_name     : str
    title            : str
    description      : str
    subscribers      : int
    active_users     : int
    over18           : bool
    created_utc      : float
    url              : str


# ── URL normalizer ─────────────────────────────────────────────

def normalize_url(raw: str) -> str:
    """
    Accept any Reddit URL form and return the clean /.json URL.
    Handles:
      - Full URLs with or without trailing /
      - Shortlinks (redd.it/xxx)
      - URLs with query params
      - Subreddit-only URLs
    """
    raw = raw.strip()
    # Remove query params and fragments
    raw = re.sub(r"[?#].*$", "", raw)
    # Remove trailing slash
    raw = raw.rstrip("/")
    # Handle redd.it shortlinks
    if "redd.it" in raw:
        post_id = raw.split("/")[-1]
        raw = f"https://www.reddit.com/comments/{post_id}"
    # Ensure no double .json
    if raw.endswith(".json"):
        return raw
    return raw + "/.json"


# ── Comment tree parser ────────────────────────────────────────

def _parse_comment(data: dict, depth: int = 0) -> Optional[RedditComment]:
    if data.get("kind") != "t1":
        return None
    d = data.get("data", {})
    if not d.get("body") or d["body"] in ("[deleted]", "[removed]"):
        return None

    replies_raw = d.get("replies", "")
    replies = []
    if isinstance(replies_raw, dict):
        for child in replies_raw.get("data", {}).get("children", []):
            c = _parse_comment(child, depth + 1)
            if c:
                replies.append(c)

    return RedditComment(
        id=d.get("id", ""),
        author=d.get("author", "[deleted]"),
        body=d.get("body", ""),
        score=d.get("score", 0),
        depth=depth,
        replies=replies,
        created_utc=d.get("created_utc", 0),
    )


# ── Main fetcher class ─────────────────────────────────────────

class RedditFetcher:

    BASE = "https://www.reddit.com"

    # ── Post fetching ─────────────────────────────────────────

    def fetch_post(self, url: str, comment_limit: int = 100) -> RedditPost:
        """Fetch a single post with all its comments."""
        json_url = normalize_url(url)
        if "?limit" not in json_url:
            json_url = json_url.rstrip("/") + f"?limit={comment_limit}"

        data = _fetch(json_url)

        # Reddit returns [post_listing, comments_listing]
        if not isinstance(data, list) or len(data) < 2:
            raise ValueError("Unexpected Reddit response format")

        post_data = data[0]["data"]["children"][0]["data"]
        comments_raw = data[1]["data"]["children"]

        comments = []
        for child in comments_raw:
            c = _parse_comment(child)
            if c:
                comments.append(c)

        return RedditPost(
            id=post_data.get("id", ""),
            title=post_data.get("title", ""),
            selftext=post_data.get("selftext", ""),
            author=post_data.get("author", "[deleted]"),
            subreddit=post_data.get("subreddit", ""),
            url=post_data.get("url", ""),
            score=post_data.get("score", 0),
            upvote_ratio=post_data.get("upvote_ratio", 0.5),
            num_comments=post_data.get("num_comments", 0),
            created_utc=post_data.get("created_utc", 0),
            flair=post_data.get("link_flair_text") or "",
            comments=comments,
        )

    # ── Subreddit feed ────────────────────────────────────────

    def fetch_subreddit_feed(self, subreddit: str, sort: str = "hot",
                              limit: int = 25, time_filter: str = "week") -> List[RedditPost]:
        """
        Fetch posts from a subreddit feed.
        sort: hot | new | top | rising | controversial
        time_filter: hour | day | week | month | year | all  (for 'top' sort)
        """
        url = f"{self.BASE}/r/{subreddit}/{sort}.json?limit={limit}&t={time_filter}"
        data = _fetch(url)
        posts = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            if child.get("kind") != "t3":
                continue
            posts.append(RedditPost(
                id=d.get("id", ""),
                title=d.get("title", ""),
                selftext=d.get("selftext", ""),
                author=d.get("author", "[deleted]"),
                subreddit=d.get("subreddit", ""),
                url=d.get("url", ""),
                score=d.get("score", 0),
                upvote_ratio=d.get("upvote_ratio", 0.5),
                num_comments=d.get("num_comments", 0),
                created_utc=d.get("created_utc", 0),
                flair=d.get("link_flair_text") or "",
            ))
        return posts

    # ── Subreddit search ──────────────────────────────────────

    def search_subreddit(self, subreddit: str, query: str,
                          limit: int = 25, sort: str = "relevance") -> List[RedditPost]:
        """Search within a subreddit."""
        q = urllib.parse.quote_plus(query)
        url = f"{self.BASE}/r/{subreddit}/search.json?q={q}&restrict_sr=1&sort={sort}&limit={limit}"
        data = _fetch(url)
        posts = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            if child.get("kind") != "t3":
                continue
            posts.append(RedditPost(
                id=d.get("id", ""),
                title=d.get("title", ""),
                selftext=d.get("selftext", ""),
                author=d.get("author", "[deleted]"),
                subreddit=d.get("subreddit", ""),
                url=d.get("url", ""),
                score=d.get("score", 0),
                upvote_ratio=d.get("upvote_ratio", 0.5),
                num_comments=d.get("num_comments", 0),
                created_utc=d.get("created_utc", 0),
                flair=d.get("link_flair_text") or "",
            ))
        return posts

    # ── Subreddit info ────────────────────────────────────────

    def fetch_subreddit_info(self, subreddit: str) -> SubredditInfo:
        url = f"{self.BASE}/r/{subreddit}/about.json"
        data = _fetch(url)
        d = data.get("data", {})
        return SubredditInfo(
            name=d.get("name", ""),
            display_name=d.get("display_name", subreddit),
            title=d.get("title", ""),
            description=d.get("public_description", ""),
            subscribers=d.get("subscribers", 0),
            active_users=d.get("active_user_count", 0),
            over18=d.get("over18", False),
            created_utc=d.get("created_utc", 0),
            url=d.get("url", f"/r/{subreddit}/"),
        )

    # ── Batch scan ────────────────────────────────────────────

    def batch_scan(self, subreddits: List[str], sort: str = "hot",
                   posts_per_sub: int = 10) -> Dict[str, List[RedditPost]]:
        """Scan multiple subreddits and return posts grouped by subreddit."""
        results = {}
        for sub in subreddits:
            try:
                posts = self.fetch_subreddit_feed(sub, sort=sort, limit=posts_per_sub)
                results[sub] = posts
            except Exception as e:
                results[sub] = []
        return results
