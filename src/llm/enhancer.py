"""
llm/enhancer.py — RedditLens: LLM Enhancement Layer
=====================================================
Connects to any OpenAI-compatible API for deep AI analysis.
Works with: OpenAI, Anthropic, DeepSeek, Qwen, Ollama, or
any OpenAI-compatible endpoint (including Awrass proxy).

When no LLM is configured, the tool works 100% locally
using the pure text analysis engine.
"""

import json
import os
import re
import ssl
import urllib.request
from typing import List, Optional

from ..analyzer.intelligence import Signal


class LLMEnhancer:
    """
    Optional AI enhancement for deeper market intelligence.
    Sends compressed post data to LLM and parses structured insights.
    """

    ANALYSIS_PROMPT = """You are a market research analyst specializing in identifying business opportunities from online communities.

Analyze this Reddit post and its comments to extract actionable market insights.

POST TITLE: {title}

CONTENT (compressed):
{content}

DETECTED SIGNALS: {signals}

Return a JSON object with EXACTLY these keys (no other text):
{{
  "opportunity_summary": "2-3 sentence business opportunity summary",
  "target_customer": "specific customer persona description",
  "core_pain": "the single most important pain point in one sentence",
  "product_idea": "one concrete product/service idea that solves this",
  "monetization": "suggested pricing/monetization model",
  "competition_gap": "what existing solutions miss",
  "urgency_level": "low|medium|high",
  "market_size_hint": "small niche|growing niche|large market",
  "key_quotes": ["most revealing quote 1", "most revealing quote 2"]
}}"""

    def __init__(self, api_key: str = "", base_url: str = "",
                 model: str = "gpt-4o-mini"):
        self.api_key  = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com")).rstrip("/")
        self.model    = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.enabled  = bool(self.api_key)

    def analyze(self, content: str, title: str,
                signals: List[Signal]) -> Optional[str]:
        """
        Sends post content to LLM and returns enhanced analysis string.
        Returns None if LLM not configured or call fails.
        """
        if not self.enabled:
            return None

        # Compress content to fit context window
        compressed = content[:4000]
        sig_summary = ", ".join(f"{s.category}:{s.text[:40]}" for s in signals[:8])

        prompt = self.ANALYSIS_PROMPT.format(
            title=title[:200],
            content=compressed,
            signals=sig_summary or "none detected",
        )

        try:
            result = self._call_api(prompt)
            parsed = self._parse_response(result)
            return parsed
        except Exception:
            return None

    def _call_api(self, prompt: str) -> str:
        url     = f"{self.base_url}/v1/chat/completions"
        payload = json.dumps({
            "model"     : self.model,
            "messages"  : [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens" : 600,
        }).encode()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type" : "application/json",
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            data = json.loads(r.read().decode())
            return data["choices"][0]["message"]["content"]

    def _parse_response(self, raw: str) -> str:
        """Parse LLM JSON response into a formatted insight string."""
        raw = re.sub(r"```json\s*|```", "", raw).strip()
        try:
            d = json.loads(raw)
        except Exception:
            m = re.search(r"\{[\s\S]+\}", raw)
            if m:
                try:
                    d = json.loads(m.group())
                except Exception:
                    return raw[:500]
            else:
                return raw[:500]

        parts = []
        if d.get("opportunity_summary"):
            parts.append(f"🎯 **Opportunity:** {d['opportunity_summary']}")
        if d.get("core_pain"):
            parts.append(f"💔 **Core Pain:** {d['core_pain']}")
        if d.get("product_idea"):
            parts.append(f"💡 **Product Idea:** {d['product_idea']}")
        if d.get("monetization"):
            parts.append(f"💰 **Monetization:** {d['monetization']}")
        if d.get("target_customer"):
            parts.append(f"👤 **Customer:** {d['target_customer']}")
        if d.get("competition_gap"):
            parts.append(f"🔍 **Gap:** {d['competition_gap']}")
        if d.get("urgency_level"):
            urgency_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(d["urgency_level"], "⚪")
            parts.append(f"{urgency_emoji} **Urgency:** {d['urgency_level'].upper()}")
        if d.get("key_quotes"):
            for q in d["key_quotes"][:2]:
                parts.append(f"💬 *\"{q[:120]}\"*")

        return "\n".join(parts) if parts else raw[:500]

    def make_llm_fn(self):
        """Return a callable for use in MarketIntelligence.analyze_post()."""
        if not self.enabled:
            return None
        def fn(content, title, signals):
            return self.analyze(content, title, signals)
        return fn


def create_enhancer(api_key="", base_url="", model="") -> LLMEnhancer:
    return LLMEnhancer(api_key=api_key, base_url=base_url, model=model)
