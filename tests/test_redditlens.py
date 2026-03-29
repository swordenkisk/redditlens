"""
test_redditlens.py — RedditLens Test Suite (22 tests)
Run: python tests/test_redditlens.py
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.reddit.fetcher import normalize_url, RedditPost, RedditComment
from src.analyzer.intelligence import (
    _extract_signals, _score_opportunity,
    _extract_keywords, MarketIntelligence, OpportunityReport,
    PAIN_PATTERNS, WTP_PATTERNS, GAP_PATTERNS, NEED_PATTERNS
)
from src.export.exporter import ReportExporter

W = 64
passed = failed = 0
results = []

def check(name, cond, detail=""):
    global passed, failed
    s = f"  [{'PASS' if cond else 'FAIL'}] {name}"
    if detail: s += f"  --  {detail}"
    print(s)
    results.append((name, cond))
    if cond: passed += 1
    else:    failed += 1

# Fix missing import
import re
def _detect_patterns_for(text):
    from src.analyzer.intelligence import PAIN_PATTERNS, WTP_PATTERNS, GAP_PATTERNS, NEED_PATTERNS
    text_l = text.lower()
    found = []
    for cat, pats in [("pain",PAIN_PATTERNS),("wtp",WTP_PATTERNS),
                       ("gap",GAP_PATTERNS),("need",NEED_PATTERNS)]:
        for p in pats:
            if re.search(p, text_l):
                found.append(cat); break
    return found

print("="*W)
print("  RedditLens — Test Suite (22 tests)")
print("="*W)

# ── Block A: URL Normalizer ───────────────────────────────
print("\n[ Block A: URL Normalizer (4 tests) ]\n")

check("A1: basic URL normalized",
      normalize_url("https://reddit.com/r/test/comments/abc123/title") \
      .endswith(".json"))
check("A2: trailing slash handled",
      normalize_url("https://reddit.com/r/test/comments/abc123/title/") \
      .endswith(".json"))
check("A3: redd.it shortlink expanded",
      "comments/abc" in normalize_url("https://redd.it/abc123"))
check("A4: already has .json — no double",
      normalize_url("https://reddit.com/r/x/.json").count(".json") == 1)

# ── Block B: Signal Detection ─────────────────────────────
print("\n[ Block B: Signal Detection (6 tests) ]\n")

pain_text = "I'm so frustrated and struggling with this tool, it's a nightmare"
sigs = _extract_signals(pain_text, "post_body", 100)
check("B1: pain signal detected in frustration text",
      any(s.category == "pain" for s in sigs), f"signals={[s.category for s in sigs]}")

wtp_text = "I would pay $50/month for something like this"
sigs2 = _extract_signals(wtp_text, "comment", 50)
check("B2: WTP signal detected in price mention",
      any(s.category == "wtp" for s in sigs2), f"signals={[s.category for s in sigs2]}")

gap_text = "Wish there was a tool that could do this automatically"
sigs3 = _extract_signals(gap_text, "comment", 20)
check("B3: gap signal detected in wish statement",
      any(s.category == "gap" for s in sigs3))

need_text = "Looking for recommendations on how to solve this problem"
sigs4 = _extract_signals(need_text, "post_title", 75)
check("B4: need signal detected in lookup request",
      any(s.category == "need" for s in sigs4))

urgency_text = "I need this ASAP, deadline is tomorrow"
sigs5 = _extract_signals(urgency_text, "comment", 10)
check("B5: urgency signal detected",
      any(s.category == "urgency" for s in sigs5))

multi_text = "I hate this tool, I'd pay $100 for something better. Why doesn't anyone build this?"
sigs6 = _extract_signals(multi_text, "post_body", 200)
cats  = {s.category for s in sigs6}
check("B6: multiple signal types in one text",
      len(cats) >= 2, f"categories={cats}")

# ── Block C: Keyword Extraction ────────────────────────────
print("\n[ Block C: Keyword Extraction (3 tests) ]\n")

kw_text = "automation tool helps developers build software faster with automation"
keywords = _extract_keywords(kw_text, top_n=10)
check("C1: keywords extracted as list of tuples",
      isinstance(keywords, list) and all(isinstance(k,tuple) for k in keywords))
check("C2: 'automation' appears as top keyword",
      any(k == "automation" for k,_ in keywords), f"top3={keywords[:3]}")
check("C3: stopwords filtered",
      not any(k in {"the","and","with","this"} for k,_ in keywords))

# ── Block D: Opportunity Scoring ───────────────────────────
print("\n[ Block D: Opportunity Scoring (3 tests) ]\n")

def make_post(**kw):
    return RedditPost(id="x",title="test",selftext="",author="u",
                      subreddit="test",url="",score=kw.get("score",10),
                      upvote_ratio=kw.get("ratio",0.8),
                      num_comments=kw.get("comments",5),created_utc=0)

low_signals  = []
high_signals = _extract_signals(
    "I hate this, I'd pay $100. Why isn't there a solution?", "post_body", 500)

high_score = _score_opportunity(high_signals, make_post(score=500,comments=80))
low_score  = _score_opportunity(low_signals,  make_post(score=5,comments=2))
check("D1: high-signal post scores higher than zero",  high_score > 0)
check("D2: low-signal post has lower score",           high_score > low_score,
      f"high={high_score:.1f} low={low_score:.1f}")
check("D3: score is bounded 0-100",                    0 <= high_score <= 100)

# ── Block E: Full Analysis Pipeline ───────────────────────
print("\n[ Block E: Full Analysis Pipeline (3 tests) ]\n")

post = RedditPost(
    id="test1", title="Why is there no good tool for automating X?",
    selftext="I've tried everything. I'd pay $50/month for a solution.",
    author="user1", subreddit="startups", url="https://reddit.com/r/startups/1",
    score=250, upvote_ratio=0.92, num_comments=45, created_utc=0,
    comments=[
        RedditComment(id="c1", author="u2",
                      body="Same here! I'm frustrated and looking for recommendations.",
                      score=80, depth=0),
        RedditComment(id="c2", author="u3",
                      body="I would pay good money for this. The existing tools are terrible.",
                      score=60, depth=0),
    ]
)
mi     = MarketIntelligence()
report = mi.analyze_post(post)
check("E1: report generated with opportunity score",
      report.opportunity_score > 0, f"score={report.opportunity_score:.1f}")
check("E2: pain points extracted",
      len(report.pain_points) >= 1 or len(report.signals) >= 1,
      f"pain_pts={len(report.pain_points)} signals={len(report.signals)}")
check("E3: to_dict works",
      "opportunity_score" in report.to_dict())

# ── Block F: Export ────────────────────────────────────────
print("\n[ Block F: Export (3 tests) ]\n")

exp   = ReportExporter()
j_out = exp.to_json([report])
check("F1: JSON export valid",
      json.loads(j_out).get("total_reports") == 1)
csv_out = exp.to_csv([report])
check("F2: CSV export has header + data row",
      "post_title" in csv_out and csv_out.count("\n") >= 2)
md_out = exp.to_markdown([report])
check("F3: Markdown export has heading",
      "# 🔍" in md_out)

# ── Block G: Subreddit Discovery ──────────────────────────
print("\n[ Block G: Subreddit Discovery (4 tests) ]\n")

from src.reddit.subreddit_discovery import SubredditDiscovery, SubredditCandidate, NICHE_MAPS

disc = SubredditDiscovery()

check("G1: NICHE_MAPS has 10 niches",     len(NICHE_MAPS) >= 10, f"count={len(NICHE_MAPS)}")
check("G2: saas niche has subreddits",    len(NICHE_MAPS.get("saas", [])) >= 5)
check("G3: pain-rich list has 10+ subs",  len(disc.get_pain_rich_subs()) >= 10)

# Test gem scoring
c1 = SubredditCandidate("test","Test","Title","Desc",5000,50,"",False)
c2 = SubredditCandidate("test","Test","Title","Desc",500000,100,"",False)
c1.gem_score = disc._score_gem(c1)
c2.gem_score = disc._score_gem(c2)
check("G4: small active sub scores higher than huge inactive sub",
      c1.gem_score > c2.gem_score,
      f"small={c1.gem_score:.1f} huge={c2.gem_score:.1f}")

# ── Block H: Trend Analyzer ────────────────────────────────
print("\n[ Block H: Trend Analyzer (3 tests) ]\n")

from src.analyzer.trends import TrendAnalyzer, _extract_competitors

ta = TrendAnalyzer()

comp_text = "I switched from Notion to Obsidian. Also tried Roam Research."
comps = _extract_competitors(comp_text)
check("H1: competitor names extracted",
      len(comps) >= 1, f"found={comps}")

# Build mock posts for corpus analysis
post_list = [
    RedditPost(id=f"p{i}", title=f"Struggling with automation tool {i}",
               selftext=f"I would pay $50/month for this. Tried Zapier but it's too expensive.",
               author="u", subreddit="SaaS", url="", score=100+i*10,
               upvote_ratio=0.9, num_comments=20, created_utc=0,
               comments=[]) for i in range(5)
]
trend_report = ta.analyze_corpus(post_list, query="automation")
check("H2: trend report has keywords",
      len(trend_report.top_keywords) >= 1, f"kw_count={len(trend_report.top_keywords)}")
check("H3: signal breakdown populated",
      len(trend_report.signal_breakdown) >= 1, f"breakdown={trend_report.signal_breakdown}")

# ── Block I: Persona Builder ────────────────────────────────
print("\n[ Block I: Persona Builder (3 tests) ]\n")

from src.analyzer.persona_builder import PersonaBuilder

pb      = PersonaBuilder()
persona = pb.build(post_list)
check("I1: persona has roles",          isinstance(persona.roles, list))
check("I2: persona has budget_range",   len(persona.budget_range) > 0, f"budget={persona.budget_range}")
check("I3: persona summary is string",  isinstance(persona.summary(), str) and len(persona.summary()) > 20)

# ── Summary ───────────────────────────────────────────────
total = passed + failed
print()
print("="*W)
status = "ALL PASS ✅" if failed == 0 else f"{failed} FAILED ❌"
print(f"  Results  :  {passed}/{total} passed  ({status})")
if failed:
    print("  Failures :  " + ", ".join(n for n,ok in results if not ok))
print("="*W)

import sys as _s; _s.exit(0 if failed == 0 else 1)
