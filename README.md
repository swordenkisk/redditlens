# 🔍 RedditLens — Market Intelligence Platform

**Find million-dollar opportunities hidden in Reddit communities.**

> Inspired by the insight: *Any Reddit URL + `.json` = full conversation data. Feed it through an LLM to detect real pain points, buying signals, and market gaps.*

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)]()
[![Flask](https://img.shields.io/badge/Flask-2.x-green)]()
[![Tests](https://img.shields.io/badge/tests-22%2F22%20passing-brightgreen)]()
[![No API Key](https://img.shields.io/badge/Reddit%20API-not%20required-gold)]()
[![License](https://img.shields.io/badge/license-MIT-brightgreen)]()

**`github.com/swordenkisk/redditlens` | swordenkisk 🇩🇿 | 2026**

---

## Quick Start

```bash
git clone https://github.com/swordenkisk/redditlens
cd redditlens
pip install flask
python app.py   # → http://127.0.0.1:5060
```

No API keys required. Uses Reddit's free public JSON API.

---

## The Core Insight

```
Any Reddit URL
   ↓ + /.json
Full thread data: all comments, upvotes, metadata
   ↓ signal detection
Pain points · WTP signals · Market gaps · Urgency
   ↓ scoring
Ranked opportunities 0–100
   ↓ (optional LLM)
Product ideas · Customer personas · Monetization
```

---

## Features

| Feature | Description |
|---------|-------------|
| 🔍 Post Analyzer | Deep analysis of any Reddit post + all comments |
| ⚡ Subreddit Scanner | Scan hot/top/new feed, rank by opportunity score |
| 🎯 Batch Mode | Scan up to 10 subreddits simultaneously |
| 💔 Pain Detection | 20 signal patterns across 6 categories |
| 💰 WTP Signals | Willingness-to-pay keyword extraction |
| 🔍 Gap Detection | "Wish there was" / "why doesn't" patterns |
| 📊 Opportunity Score | 0-100 composite score (pain × engagement × WTP) |
| 🤖 AI Enhancement | Optional LLM for product ideas & personas |
| 📤 Export | JSON / CSV / Markdown report export |
| 🔖 Bookmarks | Save and manage reports |

---

## 6 Signal Categories

- **💔 Pain** — frustrations, struggles, "hate", "nightmare"
- **💰 WTP** — "I'd pay $X", pricing mentions, "worth it"
- **🔍 Gap** — "wish there was", "why doesn't X exist"
- **📣 Need** — "looking for", "recommend me", "need help"
- **⚡ Urgency** — ASAP, deadline, "need this now"
- **🏆 Competitor** — "using X but", "alternative to", "switched"

---

## API

```bash
POST /api/analyze/post      {"url": "https://reddit.com/r/.../"}
POST /api/analyze/subreddit {"subreddit": "SaaS", "sort": "hot", "limit": 25}
POST /api/batch             {"subreddits": ["SaaS","startups"], "posts_per_sub": 10}
GET  /api/reports           # all saved reports
GET  /api/export/<id>/json  # export one report
GET  /api/export/<id>/md    # markdown export
POST /api/configure/llm     {"api_key": "sk-...", "model": "gpt-4o-mini"}
```

---

## Optional LLM

Works with any OpenAI-compatible API:
- OpenAI (gpt-4o-mini, gpt-4o)
- Anthropic (claude-sonnet-4-6)
- DeepSeek (deepseek-chat)
- Awrass proxy (`http://localhost:7777/v1`)
- Any local Ollama endpoint

Configure in the UI or via `POST /api/configure/llm`.

---

## New Modules (v2.1)

| Module | Description |
|--------|-------------|
| 🔍 Subreddit Discovery | Find hidden gems by keyword or niche — ranked by activity ratio |
| 📊 Trend Analyzer | Keyword frequency, competitor mentions, signal breakdown across subreddits |
| 👤 Persona Builder | Extract customer personas (roles, budget, frustrations, goals) from communities |
| 🎯 Keyword Ranker | Find which posts best match your target keywords |

## Architecture

```
src/
├── reddit/
│   ├── fetcher.py              ← URL normalize + JSON harvest + rate limiting
│   └── subreddit_discovery.py  ← Keyword search + niche maps + gem scoring
├── analyzer/
│   ├── intelligence.py         ← 20 signal patterns + BM25 search + opportunity score
│   ├── trends.py               ← Cross-subreddit trend + competitor mention tracking
│   └── persona_builder.py      ← Customer persona extraction (roles/budget/goals)
├── llm/
│   └── enhancer.py             ← Optional OpenAI-compatible LLM for AI summaries
└── export/
    └── exporter.py             ← JSON / CSV / Markdown export
```

## Tests: 32/32 ✅

```bash
python tests/test_redditlens.py
``````bash
python tests/test_redditlens.py
```

---

## License

MIT — © 2026 swordenkisk 🇩🇿 — Tlemcen, Algeria

*"الاستماع الذكي = فهم أعمق = منتجات تحقق مبيعات حقيقية"*
*Smart listening = deeper understanding = products with real sales*
