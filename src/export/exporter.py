"""
export/exporter.py — RedditLens: Report Exporter
=================================================
Export opportunity reports to multiple formats.
"""

import csv
import io
import json
import time
from typing import List

from ..analyzer.intelligence import OpportunityReport


class ReportExporter:

    def to_json(self, reports: List[OpportunityReport]) -> str:
        data = {
            "generated_at"   : time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_reports"  : len(reports),
            "reports"        : [r.to_dict() for r in reports],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def to_csv(self, reports: List[OpportunityReport]) -> str:
        buf = io.StringIO()
        fields = ["post_title", "subreddit", "url", "score", "num_comments",
                  "opportunity_score", "signal_count", "summary",
                  "top_keywords", "pain_points"]
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in reports:
            row = r.to_dict()
            row["top_keywords"] = " | ".join(f"{k}({v})" for k, v in row.get("top_keywords", [])[:5])
            row["pain_points"]  = " | ".join(row.get("pain_points", [])[:3])
            w.writerow({f: row.get(f, "") for f in fields})
        return buf.getvalue()

    def to_markdown(self, reports: List[OpportunityReport],
                    title: str = "Market Intelligence Report") -> str:
        lines = [
            f"# 🔍 {title}",
            f"*Generated: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}*",
            f"*{len(reports)} opportunities found*",
            "",
        ]
        for i, r in enumerate(reports, 1):
            stars = "🔥" if r.opportunity_score >= 60 else ("💡" if r.opportunity_score >= 30 else "📊")
            lines += [
                f"## {i}. {stars} {r.post_title[:80]}",
                f"**r/{r.subreddit}** · Score: **{r.opportunity_score:.1f}/100** "
                f"· 👍 {r.score} · 💬 {r.num_comments}",
                f"🔗 {r.url}",
                "",
                r.summary,
                "",
            ]
            if r.pain_points:
                lines.append("**Pain Points:**")
                for pp in r.pain_points[:3]:
                    lines.append(f"- {pp[:120]}")
                lines.append("")
            if r.wtp_signals:
                lines.append("**WTP Signals:**")
                for wtp in r.wtp_signals[:2]:
                    lines.append(f"- 💰 {wtp[:120]}")
                lines.append("")
            if r.keywords:
                kw_str = ", ".join(f"`{k}`" for k, _ in r.keywords[:8])
                lines.append(f"**Keywords:** {kw_str}")
                lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)
