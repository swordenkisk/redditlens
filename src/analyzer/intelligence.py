"""
intelligence.py — RedditLens: Market Intelligence Engine
=========================================================
Extracts business opportunities, pain points, and buying signals
from Reddit posts WITHOUT needing an LLM (pure text analysis),
plus optional LLM-enhanced deep analysis.

Signal categories extracted:
  💔 Pain Points    — frustrations, problems, struggles
  💰 WTP Signals    — willingness to pay, "I'd pay for..."
  🔍 Gap Signals    — "wish there was", "why doesn't X exist"
  📣 Need Signals   — "need help with", "looking for"
  🏆 Competitor     — mentions of existing tools/competitors
  ⚡ Urgency        — time-sensitive needs
  🌍 Audience       — who is asking (demographics, context)
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import Counter

from ..reddit.fetcher import RedditPost, RedditComment


# ── Signal patterns ────────────────────────────────────────────

PAIN_PATTERNS = [
    r"i('m| am) (frustrated|struggling|stuck|annoyed|tired|sick of|fed up)",
    r"(hate|can't stand|despise|can't deal with|so annoying)",
    r"(problem|issue|bug|broken|doesn't work|fails|failing)",
    r"(wasted|losing|lost) (hours?|days?|money|time)",
    r"(drives? me crazy|nightmare|disaster|mess)",
    r"(why (is|does|can't|won't)|how come)",
    r"(nobody|nothing|no (one|app|tool|service)) (helps?|solves?|fixes?|addresses?)",
    r"still (no|not|can't|doesn't) \w+",
    r"(overwhelmed|exhausted|burned? out|drained)",
]

WTP_PATTERNS = [
    r"(i'?d?|would) (pay|spend|give) ([\$£€]?\d+|good money|anything|a lot)",
    r"worth [\$£€]?\d+",
    r"(shut up and take my money|take my money)",
    r"(affordable|cheap|free) (version|tier|plan|option)",
    r"(price|pricing|cost|fee|subscription|how much)",
    r"(budget|willing to pay|ready to pay)",
    r"[\$£€]\d+\s*(per|a|/)\s*(month|year|mo|yr)",
    r"(premium|pro|paid) (version|plan|feature|tier)",
]

GAP_PATTERNS = [
    r"(wish|hope|want) (there (was|were|is)|someone (would|could|will))",
    r"why (isn't|aren't|doesn't|don't|can't|won't) (there|someone|anyone)",
    r"(no (one|tool|app|service|platform|solution) (that|which|for))",
    r"(looking for|searching for|need) (a|an|some) \w+ (that|which|to)",
    r"(doesn't exist yet|should exist|needs to exist)",
    r"(gap in the market|market gap|opportunity here|niche)",
    r"(tried everything|nothing works|can't find anything)",
    r"(build|create|make|develop) (this|something like|a tool)",
]

NEED_PATTERNS = [
    r"(need|need to|desperately need|really need)",
    r"(help me|help with|help finding|help getting)",
    r"(looking for (a |an )?recommendation|recommend me|suggest)",
    r"(anyone know|does anyone|has anyone tried)",
    r"(best way to|easiest way to|how do i|how to)",
    r"(what (is|are) the best|what do you use for)",
    r"(advice|guidance|tips|suggestions?) (on|for|about)",
]

COMPETITOR_PATTERNS = [
    r"(using|use|tried|try|switched (from|to)|moved (from|to))",
    r"(compared to|vs\.?|versus|alternative to|instead of)",
    r"(better than|worse than|similar to|like \w+ but)",
    r"(tool|app|software|service|platform|solution) (called|named|like)",
]

URGENCY_PATTERNS = [
    r"(asap|urgent(ly)?|right now|immediately|quickly|today|tonight)",
    r"(deadline|due (date|soon|tomorrow)|running out of time)",
    r"(can't wait|need this (now|today|asap))",
    r"(ship(ping)?|launch(ing)?|release) (tomorrow|soon|next week)",
]

BUYING_INTENT_KEYWORDS = [
    "buy", "purchase", "subscribe", "sign up", "trial", "demo",
    "pricing", "cost", "how much", "license", "checkout", "order",
    "discount", "coupon", "deal", "offer",
]


# ── Signal dataclass ───────────────────────────────────────────

@dataclass
class Signal:
    category    : str        # pain | wtp | gap | need | competitor | urgency
    text        : str        # the matching text snippet
    context     : str        # surrounding sentence
    score       : int        # upvotes of containing comment/post
    source_type : str        # "post_title" | "post_body" | "comment"
    author      : str = ""
    emoji       : str = ""

    EMOJIS = {
        "pain"      : "💔",
        "wtp"       : "💰",
        "gap"       : "🔍",
        "need"      : "📣",
        "competitor": "🏆",
        "urgency"   : "⚡",
    }

    def __post_init__(self):
        self.emoji = self.EMOJIS.get(self.category, "🔧")


@dataclass
class OpportunityReport:
    post_id     : str
    post_title  : str
    subreddit   : str
    url         : str
    score       : int
    num_comments: int
    signals     : List[Signal] = field(default_factory=list)
    pain_points : List[str]    = field(default_factory=list)
    wtp_signals : List[str]    = field(default_factory=list)
    gaps        : List[str]    = field(default_factory=list)
    keywords    : List[Tuple[str,int]] = field(default_factory=list)  # (keyword, freq)
    opportunity_score: float   = 0.0
    audience_profile : str     = ""
    summary     : str          = ""

    @property
    def signal_count(self) -> int:
        return len(self.signals)

    @property
    def pain_density(self) -> float:
        return len([s for s in self.signals if s.category == "pain"])

    def to_dict(self) -> dict:
        return {
            "post_id"       : self.post_id,
            "post_title"    : self.post_title,
            "subreddit"     : self.subreddit,
            "url"           : self.url,
            "score"         : self.score,
            "num_comments"  : self.num_comments,
            "opportunity_score": round(self.opportunity_score, 2),
            "pain_points"   : self.pain_points[:5],
            "wtp_signals"   : self.wtp_signals[:3],
            "gaps"          : self.gaps[:3],
            "top_keywords"  : self.keywords[:10],
            "signal_count"  : self.signal_count,
            "summary"       : self.summary,
        }


# ── Text helpers ───────────────────────────────────────────────

def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"[.!?\n]+", text) if len(s.strip()) > 10]


def _extract_signals(text: str, source_type: str, score: int,
                     author: str = "") -> List[Signal]:
    signals = []
    text_l  = text.lower()
    sents   = _sentences(text)

    pattern_groups = [
        ("pain",       PAIN_PATTERNS),
        ("wtp",        WTP_PATTERNS),
        ("gap",        GAP_PATTERNS),
        ("need",       NEED_PATTERNS),
        ("competitor", COMPETITOR_PATTERNS),
        ("urgency",    URGENCY_PATTERNS),
    ]

    for sent in sents:
        sent_l = sent.lower()
        for cat, patterns in pattern_groups:
            for pat in patterns:
                m = re.search(pat, sent_l)
                if m:
                    signals.append(Signal(
                        category=cat,
                        text=m.group()[:100],
                        context=sent[:200],
                        score=score,
                        source_type=source_type,
                        author=author,
                    ))
                    break  # one signal per sentence per category
    return signals


def _extract_keywords(text: str, top_n: int = 20) -> List[Tuple[str, int]]:
    """Extract meaningful keywords (nouns/phrases) using simple frequency."""
    STOPWORDS = {
        "the","a","an","is","are","was","were","be","been","have","has","had",
        "do","does","did","will","would","could","should","may","might","shall",
        "i","you","he","she","we","they","it","this","that","these","those",
        "and","or","but","if","in","on","at","to","for","of","with","by","from",
        "up","out","about","into","through","during","before","after","above",
        "below","between","each","so","than","too","very","just","not","what",
        "which","who","how","when","where","why","all","any","both","such","no",
        "can","my","your","our","their","its","am","said","get","got","make",
        "made","go","going","going","also","more","other","like","than","then",
        "don't","doesn't","isn't","aren't","wasn't","weren't","won't","hasn't",
    }
    words = re.findall(r"\b[a-z][a-z']+\b", text.lower())
    filtered = [w for w in words if w not in STOPWORDS and len(w) >= 4]
    # 2-gram phrases
    pairs = [f"{filtered[i]} {filtered[i+1]}" for i in range(len(filtered)-1)]
    counter = Counter(filtered + pairs)
    return counter.most_common(top_n)


def _score_opportunity(signals: List[Signal], post: RedditPost) -> float:
    """
    Composite opportunity score (0-100).
    High score = strong pain + WTP signal + engagement + comments.
    """
    score = 0.0
    cat_weights = {"pain": 3, "wtp": 5, "gap": 4, "need": 2, "urgency": 3, "competitor": 1}

    for sig in signals:
        w = cat_weights.get(sig.category, 1)
        score += w * (1 + min(sig.score, 100) / 100)  # cap score boost

    # Engagement bonus
    score += min(post.score, 1000) / 100          # up to 10pts from votes
    score += min(post.num_comments, 200) / 20     # up to 10pts from comments
    score += post.upvote_ratio * 5                 # up to 5pts from ratio

    # Normalize to 0-100
    return min(score * 2, 100)


# ── Main analyzer ──────────────────────────────────────────────

class MarketIntelligence:
    """
    Analyzes Reddit posts for market opportunities without external APIs.
    Pass an optional LLM function for enhanced AI analysis.
    """

    def analyze_post(self, post: RedditPost,
                     llm_fn=None) -> OpportunityReport:
        """Full analysis of a single Reddit post + its comments."""
        all_signals: List[Signal] = []

        # Analyze title
        all_signals.extend(_extract_signals(
            post.title, "post_title", post.score, post.author
        ))
        # Analyze body
        if post.selftext:
            all_signals.extend(_extract_signals(
                post.selftext, "post_body", post.score, post.author
            ))
        # Analyze comments (weighted by comment score)
        def _recurse_comments(comments: List[RedditComment]):
            for c in comments:
                if c.is_substantial:
                    all_signals.extend(_extract_signals(
                        c.body, "comment", c.score, c.author
                    ))
                _recurse_comments(c.replies)
        _recurse_comments(post.comments)

        # Deduplicate by context
        seen_ctx = set()
        unique_signals = []
        for s in all_signals:
            key = s.context[:80].lower()
            if key not in seen_ctx:
                seen_ctx.add(key)
                unique_signals.append(s)

        # Extract keyword freq from full text
        full_text = post.all_text()
        keywords  = _extract_keywords(full_text)

        # Categorize
        pain_pts = [s.context for s in unique_signals if s.category == "pain"][:8]
        wtp_sigs = [s.context for s in unique_signals if s.category == "wtp"][:5]
        gaps     = [s.context for s in unique_signals if s.category == "gap"][:5]

        opp_score = _score_opportunity(unique_signals, post)

        # Quick audience profile
        profile = _infer_audience(full_text)

        # Auto-summary (no LLM needed)
        summary = _auto_summary(post, unique_signals, opp_score)

        # LLM enhancement if available
        if llm_fn and full_text:
            try:
                ai_summary = llm_fn(full_text, post.title, unique_signals)
                if ai_summary:
                    summary = ai_summary
            except Exception:
                pass  # fall back to auto-summary

        return OpportunityReport(
            post_id          = post.id,
            post_title       = post.title,
            subreddit        = post.subreddit,
            url              = post.full_url,
            score            = post.score,
            num_comments     = post.num_comments,
            signals          = unique_signals,
            pain_points      = pain_pts,
            wtp_signals      = wtp_sigs,
            gaps             = gaps,
            keywords         = keywords,
            opportunity_score= opp_score,
            audience_profile = profile,
            summary          = summary,
        )

    def batch_analyze(self, posts: List[RedditPost],
                      min_score: float = 10.0,
                      llm_fn=None) -> List[OpportunityReport]:
        """Analyze a list of posts and return sorted by opportunity score."""
        reports = []
        for post in posts:
            try:
                report = self.analyze_post(post, llm_fn)
                if report.opportunity_score >= min_score:
                    reports.append(report)
            except Exception:
                pass
        return sorted(reports, key=lambda r: r.opportunity_score, reverse=True)

    def scan_subreddit(self, fetcher, subreddit: str,
                       sort: str = "hot", limit: int = 25,
                       fetch_comments: bool = True,
                       llm_fn=None) -> List[OpportunityReport]:
        """
        Full pipeline: fetch → analyze → rank.
        Optionally fetches full comment trees for top posts.
        """
        posts = fetcher.fetch_subreddit_feed(subreddit, sort=sort, limit=limit)

        if fetch_comments:
            # Only fetch full comments for top N by engagement
            posts_sorted = sorted(posts, key=lambda p: p.engagement_score, reverse=True)
            enriched = []
            for i, post in enumerate(posts_sorted):
                if i < 5:  # fetch full comments for top 5
                    try:
                        full = fetcher.fetch_post(post.full_url)
                        enriched.append(full)
                    except Exception:
                        enriched.append(post)
                else:
                    enriched.append(post)
            posts = enriched

        return self.batch_analyze(posts, llm_fn=llm_fn)


def _infer_audience(text: str) -> str:
    text_l = text.lower()
    clues  = []
    role_map = {
        "entrepreneur|founder|startup|side project|indie": "Entrepreneurs/Founders",
        "developer|programmer|engineer|coding|software": "Developers",
        "freelancer|freelance|client|agency": "Freelancers",
        "student|college|university|academic|thesis": "Students",
        "creator|youtuber|streamer|content|podcast": "Content Creators",
        "marketer|marketing|seo|ads|campaign": "Marketers",
        "designer|ux|ui|figma|sketch": "Designers",
        "parent|mom|dad|kid|children|family": "Parents/Families",
        "health|doctor|patient|medical|therapy": "Healthcare",
    }
    for pattern, label in role_map.items():
        if re.search(pattern, text_l):
            clues.append(label)
    return " · ".join(clues[:3]) if clues else "General Community"


def _auto_summary(post: RedditPost, signals: List[Signal],
                   opp_score: float) -> str:
    pain_count = len([s for s in signals if s.category == "pain"])
    wtp_count  = len([s for s in signals if s.category == "wtp"])
    gap_count  = len([s for s in signals if s.category == "gap"])

    parts = []
    if opp_score >= 60:
        parts.append(f"🔥 HIGH-VALUE opportunity in r/{post.subreddit}.")
    elif opp_score >= 30:
        parts.append(f"💡 Moderate opportunity in r/{post.subreddit}.")
    else:
        parts.append(f"📊 Low signal in r/{post.subreddit}.")

    if pain_count > 0:
        parts.append(f"Detected {pain_count} pain signal{'s' if pain_count>1 else ''}.")
    if wtp_count > 0:
        parts.append(f"Found {wtp_count} willingness-to-pay indicator{'s' if wtp_count>1 else ''}.")
    if gap_count > 0:
        parts.append(f"Identified {gap_count} market gap signal{'s' if gap_count>1 else ''}.")

    return " ".join(parts)
