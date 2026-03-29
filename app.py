"""
app.py — RedditLens: Market Intelligence Platform
==================================================
The full web application.

Routes:
  GET  /                      → Dashboard
  GET  /scan                  → Subreddit scanner
  GET  /post                  → Single post analyzer
  GET  /batch                 → Batch multi-subreddit scan
  GET  /reports               → Saved reports list
  POST /api/analyze/post      → Analyze a single Reddit post URL
  POST /api/analyze/subreddit → Scan a subreddit
  POST /api/batch             → Batch scan multiple subreddits
  GET  /api/reports           → List saved reports
  GET  /api/report/<id>       → Get one report
  DELETE /api/report/<id>     → Delete a report
  GET  /api/export/<id>/<fmt> → Export report (json|csv|md)
  POST /api/configure/llm     → Set LLM API key
  GET  /health                → Health check

Author: github.com/swordenkisk/redditlens
"""

import json
import os
import time
import uuid
from pathlib import Path

from flask import (Flask, Response, abort, jsonify,
                   render_template, request)

from src.reddit.fetcher           import RedditFetcher, normalize_url
from src.reddit.subreddit_discovery import SubredditDiscovery, NICHE_MAPS
from src.analyzer.intelligence    import MarketIntelligence
from src.analyzer.trends          import TrendAnalyzer
from src.analyzer.persona_builder import PersonaBuilder
from src.llm.enhancer             import create_enhancer
from src.export.exporter          import ReportExporter

app       = Flask(__name__)
fetcher   = RedditFetcher()
analyzer  = MarketIntelligence()
discovery = SubredditDiscovery()
trends    = TrendAnalyzer()
personas  = PersonaBuilder()
exporter  = ReportExporter()

DATA_DIR  = Path("data")
DATA_DIR.mkdir(exist_ok=True)

_llm_cfg  : dict = {}          # persists LLM config for session
_reports  : dict = {}          # in-memory report store (id → dict)


def _get_llm_fn():
    if not _llm_cfg.get("api_key"):
        return None
    enh = create_enhancer(
        api_key  = _llm_cfg["api_key"],
        base_url = _llm_cfg.get("base_url", ""),
        model    = _llm_cfg.get("model", "gpt-4o-mini"),
    )
    return enh.make_llm_fn()


def _save_report(report_dict: dict) -> str:
    rid = str(uuid.uuid4())[:8]
    report_dict["id"]         = rid
    report_dict["saved_at"]   = time.time()
    _reports[rid] = report_dict
    return rid


# ── Pages ──────────────────────────────────────────────────────

@app.route("/")
def index():
    total     = len(_reports)
    top_opps  = sorted(_reports.values(),
                       key=lambda r: r.get("opportunity_score", 0), reverse=True)[:5]
    llm_ready = bool(_llm_cfg.get("api_key"))
    return render_template("index.html", total=total,
                           top_opps=top_opps, llm_ready=llm_ready)


@app.route("/scan")
def scan_page():
    return render_template("scan.html", llm_ready=bool(_llm_cfg.get("api_key")))


@app.route("/post")
def post_page():
    return render_template("post.html", llm_ready=bool(_llm_cfg.get("api_key")))


@app.route("/batch")
def batch_page():
    return render_template("batch.html", llm_ready=bool(_llm_cfg.get("api_key")))


@app.route("/discover")
def discover_page():
    niches = list(NICHE_MAPS.keys())
    return render_template("discover.html",
                           niches=niches,
                           llm_ready=bool(_llm_cfg.get("api_key")))


@app.route("/trends")
def trends_page():
    return render_template("trends.html",
                           llm_ready=bool(_llm_cfg.get("api_key")))


@app.route("/persona")
def persona_page():
    return render_template("persona.html",
                           llm_ready=bool(_llm_cfg.get("api_key")))


@app.route("/reports")
def reports_page():
    reps = sorted(_reports.values(),
                  key=lambda r: r.get("saved_at", 0), reverse=True)
    return render_template("reports.html", reports=reps)


@app.route("/report/<rid>")
def report_detail(rid: str):
    report = _reports.get(rid)
    if not report:
        abort(404)
    return render_template("report_detail.html", report=report)


# ── API ────────────────────────────────────────────────────────

@app.route("/api/analyze/post", methods=["POST"])
def api_analyze_post():
    data = request.get_json(silent=True) or {}
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    try:
        post   = fetcher.fetch_post(url, comment_limit=data.get("comment_limit", 100))
        report = analyzer.analyze_post(post, llm_fn=_get_llm_fn())
        d      = report.to_dict()

        # Enrich with signals
        d["signals"] = [
            {"category": s.category, "context": s.context[:200],
             "source": s.source_type, "score": s.score, "emoji": s.emoji}
            for s in report.signals[:30]
        ]
        d["audience_profile"] = report.audience_profile

        rid = _save_report(d)
        d["id"] = rid
        return jsonify(d)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze/subreddit", methods=["POST"])
def api_analyze_subreddit():
    data       = request.get_json(silent=True) or {}
    subreddit  = data.get("subreddit", "").strip().lstrip("r/")
    sort       = data.get("sort", "hot")
    limit      = min(int(data.get("limit", 25)), 50)
    fetch_cmts = data.get("fetch_comments", True)

    if not subreddit:
        return jsonify({"error": "subreddit is required"}), 400

    try:
        reports = analyzer.scan_subreddit(
            fetcher, subreddit,
            sort=sort, limit=limit,
            fetch_comments=fetch_cmts,
            llm_fn=_get_llm_fn(),
        )
        results = []
        for r in reports[:20]:
            d   = r.to_dict()
            rid = _save_report(d)
            d["id"] = rid
            results.append(d)

        return jsonify({
            "subreddit"  : subreddit,
            "total_found": len(results),
            "reports"    : results,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/batch", methods=["POST"])
def api_batch():
    data      = request.get_json(silent=True) or {}
    subs      = [s.strip().lstrip("r/") for s in data.get("subreddits", []) if s.strip()]
    sort      = data.get("sort", "hot")
    limit     = min(int(data.get("posts_per_sub", 10)), 25)
    threshold = float(data.get("min_score", 15))

    if not subs:
        return jsonify({"error": "subreddits list is required"}), 400
    if len(subs) > 10:
        return jsonify({"error": "max 10 subreddits per batch"}), 400

    try:
        all_posts_by_sub = fetcher.batch_scan(subs, sort=sort, posts_per_sub=limit)
        all_reports = []
        for sub, posts in all_posts_by_sub.items():
            sub_reports = analyzer.batch_analyze(posts, min_score=threshold,
                                                  llm_fn=_get_llm_fn())
            for r in sub_reports[:5]:
                d   = r.to_dict()
                rid = _save_report(d)
                d["id"] = rid
                all_reports.append(d)

        all_reports.sort(key=lambda x: x["opportunity_score"], reverse=True)
        return jsonify({
            "scanned_subs": len(subs),
            "total_found" : len(all_reports),
            "reports"     : all_reports[:30],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reports")
def api_reports():
    reps = sorted(_reports.values(),
                  key=lambda r: r.get("saved_at", 0), reverse=True)
    return jsonify(reps)


@app.route("/api/report/<rid>")
def api_report(rid: str):
    r = _reports.get(rid)
    if not r: return jsonify({"error": "not found"}), 404
    return jsonify(r)


@app.route("/api/report/<rid>", methods=["DELETE"])
def api_delete_report(rid: str):
    if rid not in _reports:
        return jsonify({"error": "not found"}), 404
    del _reports[rid]
    return jsonify({"status": "deleted"})


@app.route("/api/export/<rid>/<fmt>")
def api_export(rid: str, fmt: str):
    r = _reports.get(rid)
    if not r: return jsonify({"error": "not found"}), 404

    # Reconstruct minimal report for export
    from src.analyzer.intelligence import OpportunityReport
    report = OpportunityReport(
        post_id=r.get("post_id",""),
        post_title=r.get("post_title",""),
        subreddit=r.get("subreddit",""),
        url=r.get("url",""),
        score=r.get("score",0),
        num_comments=r.get("num_comments",0),
        opportunity_score=r.get("opportunity_score",0),
        pain_points=r.get("pain_points",[]),
        wtp_signals=r.get("wtp_signals",[]),
        gaps=r.get("gaps",[]),
        keywords=r.get("top_keywords",[]),
        summary=r.get("summary",""),
    )

    if fmt == "json":
        content  = exporter.to_json([report])
        mimetype = "application/json"
        fname    = f"redditlens_{rid}.json"
    elif fmt == "csv":
        content  = exporter.to_csv([report])
        mimetype = "text/csv"
        fname    = f"redditlens_{rid}.csv"
    elif fmt in ("md", "markdown"):
        content  = exporter.to_markdown([report])
        mimetype = "text/markdown"
        fname    = f"redditlens_{rid}.md"
    else:
        return jsonify({"error": "fmt must be json|csv|md"}), 400

    return Response(
        content, mimetype=mimetype,
        headers={"Content-Disposition": f"attachment;filename={fname}"}
    )


@app.route("/api/configure/llm", methods=["POST"])
def api_configure_llm():
    global _llm_cfg
    data = request.get_json(silent=True) or {}
    _llm_cfg = {
        "api_key" : data.get("api_key", ""),
        "base_url": data.get("base_url", ""),
        "model"   : data.get("model", "gpt-4o-mini"),
    }
    enabled = bool(_llm_cfg["api_key"])
    return jsonify({"status": "ok", "llm_enabled": enabled})


@app.route("/api/url/normalize", methods=["POST"])
def api_normalize_url():
    data = request.get_json(silent=True) or {}
    url  = data.get("url", "")
    return jsonify({"normalized": normalize_url(url)})


@app.route("/api/discover/search", methods=["POST"])
def api_discover_search():
    data  = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    limit = min(int(data.get("limit", 20)), 30)
    if not query:
        return jsonify({"error": "query required"}), 400
    try:
        candidates = discovery.search(query, limit=limit)
        return jsonify([c.to_dict() for c in candidates])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/discover/niche/<niche>")
def api_discover_niche(niche: str):
    subs = discovery.get_niche_list(niche)
    if not subs:
        return jsonify({"error": f"Unknown niche: {niche}. Try: {list(NICHE_MAPS.keys())}"}), 404
    return jsonify({"niche": niche, "subreddits": subs})


@app.route("/api/discover/pain-rich")
def api_discover_pain_rich():
    return jsonify({"subreddits": discovery.get_pain_rich_subs()})


@app.route("/api/trends", methods=["POST"])
def api_trends():
    data      = request.get_json(silent=True) or {}
    subs_raw  = data.get("subreddits", [])
    query     = data.get("query", "")
    limit     = min(int(data.get("limit", 15)), 30)
    sort      = data.get("sort", "hot")

    subs = [s.strip().lstrip("r/") for s in subs_raw if s.strip()]
    if not subs:
        return jsonify({"error": "subreddits list required"}), 400

    try:
        all_posts = []
        for sub in subs[:5]:
            posts = fetcher.fetch_subreddit_feed(sub, sort=sort, limit=limit)
            all_posts.extend(posts)

        report = trends.analyze_corpus(all_posts, query=query)
        return jsonify(report.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/persona", methods=["POST"])
def api_persona():
    data      = request.get_json(silent=True) or {}
    subs_raw  = data.get("subreddits", [])
    limit     = min(int(data.get("limit", 20)), 30)
    sort      = data.get("sort", "hot")

    subs = [s.strip().lstrip("r/") for s in subs_raw if s.strip()]
    if not subs:
        return jsonify({"error": "subreddits list required"}), 400

    try:
        all_posts = []
        for sub in subs[:3]:
            posts = fetcher.fetch_subreddit_feed(sub, sort=sort, limit=limit)
            all_posts.extend(posts)

        persona = personas.build(all_posts)
        result  = persona.to_dict()
        result["summary"] = persona.summary()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/keyword-rank", methods=["POST"])
def api_keyword_rank():
    data     = request.get_json(silent=True) or {}
    sub      = data.get("subreddit", "").strip().lstrip("r/")
    keywords = data.get("keywords", [])
    limit    = min(int(data.get("limit", 25)), 50)

    if not sub or not keywords:
        return jsonify({"error": "subreddit and keywords required"}), 400

    try:
        posts   = fetcher.fetch_subreddit_feed(sub, sort="hot", limit=limit)
        ranked  = trends.keyword_search_rank(posts, keywords)
        return jsonify({"subreddit": sub, "keywords": keywords, "results": ranked})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    return jsonify({
        "status"     : "ok",
        "app"        : "RedditLens",
        "version"    : "2.0.0",
        "reports"    : len(_reports),
        "llm_enabled": bool(_llm_cfg.get("api_key")),
    })


if __name__ == "__main__":
    host  = os.environ.get("HOST", "127.0.0.1")
    port  = int(os.environ.get("PORT", 5060))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    print(f"\n{'='*52}")
    print("  RedditLens — Market Intelligence Platform")
    print(f"  http://{host}:{port}")
    print("  No API key required — uses Reddit's public JSON API")
    print(f"{'='*52}\n")
    app.run(host=host, port=port, debug=debug)
