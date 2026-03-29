"""
subreddit_discovery.py — RedditLens: Smart Subreddit Discovery
===============================================================
Discovers hidden gem subreddits based on:
  - Keyword search across Reddit
  - Related subreddit suggestions
  - Curated niche category maps
  - Subscriber-to-activity ratio scoring (small but active = gold)

The insight: small communities (1k-50k members) are treasure troves.
People explain their exact needs without filters or social pressure.
"""

import re
import ssl
import json
import urllib.parse
import urllib.request
import time
from dataclasses import dataclass, field
from typing import List, Optional

_LAST_REQUEST = 0.0
_MIN_INTERVAL = 1.1


def _fetch(url: str, timeout: int = 12) -> dict:
    global _LAST_REQUEST
    elapsed = time.time() - _LAST_REQUEST
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    headers = {"User-Agent": "RedditLens/2.0 SubredditDiscovery"}
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        _LAST_REQUEST = time.time()
        return json.loads(r.read().decode("utf-8"))


@dataclass
class SubredditCandidate:
    name         : str
    display_name : str
    title        : str
    description  : str
    subscribers  : int
    active_users : int
    url          : str
    over18       : bool = False
    gem_score    : float = 0.0   # 0-100: how "hidden gem" it is

    @property
    def activity_ratio(self) -> float:
        """Active users per 1000 subscribers — higher = more engaged."""
        if self.subscribers == 0:
            return 0.0
        return (self.active_users / self.subscribers) * 1000

    @property
    def is_niche(self) -> bool:
        return 500 <= self.subscribers <= 100_000

    def to_dict(self) -> dict:
        return {
            "name"          : self.name,
            "display_name"  : self.display_name,
            "title"         : self.title,
            "description"   : self.description[:200],
            "subscribers"   : self.subscribers,
            "active_users"  : self.active_users,
            "url"           : self.url,
            "gem_score"     : round(self.gem_score, 1),
            "activity_ratio": round(self.activity_ratio, 2),
            "is_niche"      : self.is_niche,
        }


# ── Curated niche maps ────────────────────────────────────────

NICHE_MAPS = {
    "saas": [
        "SaaS", "microsaas", "indiehackers", "SideProject", "startups",
        "EntrepreneurRideAlong", "IMadeThis", "alphaandbetausers",
        "SaaSmarketing", "b2bmarketing",
    ],
    "freelance": [
        "freelance", "freelanceWriters", "Upwork", "forhire",
        "slavelabour", "HireADeveloper", "copywriting",
        "freelanceprogramming",
    ],
    "ecommerce": [
        "ecommerce", "shopify", "Etsy", "dropship", "AmazonSeller",
        "FulfillmentByAmazon", "WooCommerce", "printfulpod",
    ],
    "creators": [
        "NewTubers", "PartneredYoutube", "podcasting",
        "newsletter", "SubstackWriters", "blogging",
        "InstagramMarketing", "TikTokCreators",
    ],
    "productivity": [
        "productivity", "nosurf", "getdisciplined", "ADHD",
        "Notion", "Obsidian", "LifeImprovement", "selfimprovement",
    ],
    "dev_tools": [
        "webdev", "devops", "learnprogramming", "cscareerquestions",
        "ExperiencedDevs", "node", "Python", "rust",
    ],
    "finance": [
        "personalfinance", "financialindependence", "fatFIRE",
        "leanfire", "Accounting", "smallbusiness", "tax",
    ],
    "health": [
        "HealthIT", "mentalhealth", "Anxiety", "therapy",
        "nutrition", "loseit", "fitness", "bodyweightfitness",
    ],
    "ai_ml": [
        "MachineLearning", "artificial", "LanguageModelPrompts",
        "AIAssistants", "ChatGPT", "ClaudeAI", "LocalLLaMA",
        "StableDiffusion",
    ],
    "remote_work": [
        "digitalnomad", "RemoteWork", "WorkOnline",
        "beermoney", "povertyfinance", "WorkFromHome",
    ],
}

PAIN_RICH_SUBS = [
    # High-signal communities where people openly share problems
    "Entrepreneur", "smallbusiness", "startups", "SaaS",
    "freelance", "cscareerquestions", "personalfinance",
    "productivity", "ADHD", "Anxiety", "webdev",
    "learnprogramming", "digitalnomad", "ecommerce",
    "shopify", "marketing", "copywriting", "content_marketing",
    "socialmedia", "seo", "PPC", "analytics",
]


class SubredditDiscovery:
    """Finds and scores subreddits for market intelligence scanning."""

    BASE = "https://www.reddit.com"

    def search(self, query: str, limit: int = 20) -> List[SubredditCandidate]:
        """Search for subreddits matching a keyword."""
        q   = urllib.parse.quote_plus(query)
        url = f"{self.BASE}/subreddits/search.json?q={q}&limit={limit}&include_over_18=false"
        try:
            data = _fetch(url)
        except Exception:
            return []

        candidates = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            if child.get("kind") != "t5":
                continue
            c = SubredditCandidate(
                name        = d.get("display_name", ""),
                display_name= d.get("display_name", ""),
                title       = d.get("title", ""),
                description = d.get("public_description", ""),
                subscribers = d.get("subscribers", 0),
                active_users= d.get("active_user_count", 0),
                url         = d.get("url", ""),
                over18      = d.get("over18", False),
            )
            c.gem_score = self._score_gem(c)
            candidates.append(c)

        return sorted(candidates, key=lambda x: x.gem_score, reverse=True)

    def get_related(self, subreddit: str) -> List[str]:
        """
        Get related subreddits from sidebar wiki links.
        Uses subreddit wiki/sidebar parsing (no auth needed).
        """
        url = f"{self.BASE}/r/{subreddit}/about.json"
        try:
            data = _fetch(url)
            desc = data.get("data", {}).get("description", "") or ""
            # Extract r/subreddit mentions
            mentions = re.findall(r"/r/([A-Za-z0-9_]+)", desc)
            return list(dict.fromkeys(m for m in mentions
                                       if m.lower() != subreddit.lower()))[:15]
        except Exception:
            return []

    def get_niche_list(self, niche: str) -> List[str]:
        """Get curated subreddit list for a niche."""
        return NICHE_MAPS.get(niche.lower(), [])

    def get_pain_rich_subs(self) -> List[str]:
        """Return curated list of high-signal subreddits."""
        return PAIN_RICH_SUBS.copy()

    def _score_gem(self, c: SubredditCandidate) -> float:
        """
        Score how 'hidden gem' a subreddit is.
        Ideal: 1k-50k subscribers, high activity ratio, descriptive title.
        """
        score = 0.0

        # Sweet spot: not too big, not too small
        subs = c.subscribers
        if 1_000 <= subs <= 10_000:
            score += 40
        elif 10_000 < subs <= 50_000:
            score += 30
        elif 50_000 < subs <= 200_000:
            score += 15
        elif subs < 1_000:
            score += 10

        # Activity ratio bonus
        ratio = c.activity_ratio
        if ratio >= 5:
            score += 30
        elif ratio >= 2:
            score += 20
        elif ratio >= 1:
            score += 10

        # Description quality
        if len(c.description) > 50:
            score += 10

        # No NSFW penalty
        if c.over18:
            score -= 20

        return max(0.0, min(100.0, score))

    def rank_for_research(self, subreddits: List[str]) -> List[dict]:
        """
        Fetch info for a list of subreddits and rank by gem score.
        Returns sorted list of dicts.
        """
        results = []
        for sub in subreddits:
            try:
                url  = f"{self.BASE}/r/{sub}/about.json"
                data = _fetch(url)
                d    = data.get("data", {})
                c    = SubredditCandidate(
                    name        = d.get("display_name", sub),
                    display_name= d.get("display_name", sub),
                    title       = d.get("title", ""),
                    description = d.get("public_description", ""),
                    subscribers = d.get("subscribers", 0),
                    active_users= d.get("active_user_count", 0),
                    url         = d.get("url", f"/r/{sub}/"),
                    over18      = d.get("over18", False),
                )
                c.gem_score = self._score_gem(c)
                results.append(c.to_dict())
            except Exception:
                results.append({"name": sub, "gem_score": 0, "error": True})

        return sorted(results, key=lambda x: x.get("gem_score", 0), reverse=True)
