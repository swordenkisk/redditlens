"""
trends.py — RedditLens: Trend Analysis Engine
=============================================
Tracks keyword and pain-point frequency across subreddits over time.
Detects rising signals before they go mainstream.

Features:
  - Keyword frequency across multiple posts/subreddits
  - Signal category breakdown per subreddit
  - Rising vs declining topic detection
  - Competitor mention frequency
  - Audience segment cross-analysis
"""

import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..reddit.fetcher import RedditPost
from ..analyzer.intelligence import (
    _extract_signals, _extract_keywords, Signal
)


@dataclass
class TrendReport:
    query          : str
    subreddits     : List[str]
    posts_analyzed : int
    total_signals  : int
    top_keywords   : List[Tuple[str, int]]
    signal_breakdown: Dict[str, int]   # category → count
    top_pain_phrases: List[str]
    top_wtp_phrases : List[str]
    competitor_mentions: List[Tuple[str, int]]  # (name, count)
    audience_segments  : List[str]
    generated_at   : float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "query"             : self.query,
            "subreddits"        : self.subreddits,
            "posts_analyzed"    : self.posts_analyzed,
            "total_signals"     : self.total_signals,
            "top_keywords"      : self.top_keywords[:20],
            "signal_breakdown"  : self.signal_breakdown,
            "top_pain_phrases"  : self.top_pain_phrases[:8],
            "top_wtp_phrases"   : self.top_wtp_phrases[:5],
            "competitor_mentions": self.competitor_mentions[:10],
            "audience_segments" : self.audience_segments[:5],
            "generated_at"      : self.generated_at,
        }


COMPETITOR_STOP = {
    "the", "this", "that", "they", "their", "them",
    "have", "been", "with", "from", "will", "what",
    "which", "when", "where", "there", "here",
}


def _extract_competitors(text: str) -> List[str]:
    """Extract tool/product/company names likely mentioned as competitors."""
    text_l = text.lower()
    # Patterns: "using X", "tried X", "switched to X", "X is better"
    patterns = [
        r"(?:using|tried|use|switched to|moved to|replaced by)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)?)",
        r"([A-Z][a-zA-Z0-9]+(?:\.(?:com|io|ai|app|dev)))",
        r"(?:tool|app|software|platform|service)\s+(?:called|named)\s+([A-Z][a-zA-Z0-9]+)",
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            name = m.group(1).strip()
            if name.lower() not in COMPETITOR_STOP and len(name) >= 3:
                found.append(name)
    return found


class TrendAnalyzer:
    """Aggregate signal analysis across multiple posts."""

    def analyze_corpus(self, posts: List[RedditPost],
                       query: str = "") -> TrendReport:
        """
        Analyze a collection of posts as a corpus.
        Returns aggregated trend report.
        """
        all_keywords   : List[str] = []
        all_bigrams    : List[str] = []
        signal_cats    : Counter   = Counter()
        pain_phrases   : List[str] = []
        wtp_phrases    : List[str] = []
        competitors    : List[str] = []
        audience_segs  : Counter   = Counter()
        total_signals  : int       = 0

        for post in posts:
            full_text = post.all_text()
            if not full_text.strip():
                continue

            # Keywords
            kw_pairs = _extract_keywords(full_text, top_n=30)
            for kw, _ in kw_pairs:
                if " " in kw:
                    all_bigrams.append(kw)
                else:
                    all_keywords.append(kw)

            # Signals
            sigs = _extract_signals(full_text, "corpus", post.score)
            for s in sigs:
                signal_cats[s.category] += 1
                total_signals += 1
                if s.category == "pain" and s.context:
                    pain_phrases.append(s.context[:150])
                elif s.category == "wtp" and s.context:
                    wtp_phrases.append(s.context[:150])

            # Competitors
            competitors.extend(_extract_competitors(full_text))

            # Audience
            from ..analyzer.intelligence import _infer_audience
            seg = _infer_audience(full_text)
            if seg and seg != "General Community":
                for s in seg.split(" · "):
                    audience_segs[s.strip()] += 1

        # Aggregate keywords
        kw_counter    = Counter(all_keywords)
        bigram_counter = Counter(all_bigrams)
        combined      = kw_counter + bigram_counter
        top_kw        = combined.most_common(25)

        # Deduplicate phrases
        def dedup(phrases, max_n=8):
            seen = set()
            result = []
            for p in phrases:
                key = p.lower()[:60]
                if key not in seen:
                    seen.add(key)
                    result.append(p)
                if len(result) >= max_n:
                    break
            return result

        # Competitor frequency
        comp_counter = Counter(competitors)
        top_comps    = [(n, c) for n, c in comp_counter.most_common(15)
                        if n.lower() not in COMPETITOR_STOP]

        return TrendReport(
            query            = query,
            subreddits       = list({p.subreddit for p in posts}),
            posts_analyzed   = len(posts),
            total_signals    = total_signals,
            top_keywords     = top_kw,
            signal_breakdown = dict(signal_cats),
            top_pain_phrases = dedup(pain_phrases),
            top_wtp_phrases  = dedup(wtp_phrases),
            competitor_mentions = top_comps[:10],
            audience_segments   = [s for s, _ in audience_segs.most_common(5)],
        )

    def keyword_search_rank(self, posts: List[RedditPost],
                             keywords: List[str]) -> List[dict]:
        """
        Rank posts by how many target keywords they contain.
        Useful for finding the most relevant posts for a keyword set.
        """
        kw_set = {k.lower() for k in keywords}
        results = []
        for post in posts:
            text   = post.all_text().lower()
            hits   = {k for k in kw_set if k in text}
            density = sum(text.count(k) for k in hits)
            if hits:
                results.append({
                    "post_id"    : post.id,
                    "title"      : post.title,
                    "subreddit"  : post.subreddit,
                    "url"        : post.full_url,
                    "score"      : post.score,
                    "kw_hits"    : list(hits),
                    "kw_density" : density,
                    "num_comments": post.num_comments,
                })
        return sorted(results, key=lambda x: (len(x["kw_hits"]), x["kw_density"]),
                      reverse=True)
