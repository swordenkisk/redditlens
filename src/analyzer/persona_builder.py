"""
persona_builder.py — RedditLens: Customer Persona Builder
==========================================================
Extracts customer personas from Reddit posts — who is suffering,
what they do, what they want to pay, what tools they use.
Works 100% offline via pattern matching + heuristics.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..reddit.fetcher import RedditPost


# ── Role & context detectors ──────────────────────────────────

ROLE_PATTERNS = {
    "Founder / CEO"          : [r"\bfounder\b", r"\bco.founder\b", r"\bceo\b", r"\bbuilding\s+\w+\b"],
    "Developer"              : [r"\bdeveloper\b", r"\bprogrammer\b", r"\bengineer\b", r"\bcoding\b", r"\bcode\b"],
    "Freelancer"             : [r"\bfreelance\b", r"\bfreelancer\b", r"\bclient\b", r"\bproject\s+based\b"],
    "Designer"               : [r"\bdesigner\b", r"\bux\b", r"\bui\b", r"\bfigma\b", r"\bsketch\b"],
    "Marketer"               : [r"\bmarketer\b", r"\bmarketing\b", r"\bseo\b", r"\bcampaign\b", r"\bleads\b"],
    "Student"                : [r"\bstudent\b", r"\buniversity\b", r"\bcollege\b", r"\bthesis\b", r"\bclass\b"],
    "Content Creator"        : [r"\byoutuber\b", r"\bcreator\b", r"\bstreamer\b", r"\bcontent\b", r"\bpodcast\b"],
    "Small Business Owner"   : [r"\bsmall\s+business\b", r"\bmy\s+business\b", r"\bstore\b", r"\bshop\b"],
    "Enterprise Employee"    : [r"\bcorporate\b", r"\benterprise\b", r"\bteam\b", r"\borganization\b"],
    "Parent"                 : [r"\bparent\b", r"\bmom\b", r"\bdad\b", r"\bkids?\b", r"\bchildren\b"],
    "Healthcare Professional": [r"\bdoctor\b", r"\bnurse\b", r"\bpatient\b", r"\bclinic\b", r"\bmedical\b"],
}

EXPERIENCE_PATTERNS = {
    "Beginner"    : [r"\bnew to\b", r"\bjust started\b", r"\blearning\b", r"\bbeginner\b", r"\bnoob\b"],
    "Intermediate": [r"\b\d+\s+years?\s+(of\s+)?experience\b", r"\bsome experience\b"],
    "Expert"      : [r"\bsenior\b", r"\bexpert\b", r"\b10\+\s+years\b", r"\bveteran\b", r"\bprofessional\b"],
}

BUDGET_PATTERNS = {
    "Budget (<$20/mo)"    : [r"\$\s*\d{1,2}(?:/mo|/month|per month)?\b", r"\bfree\b.*\bplan\b", r"\bcheap\b", r"\baffordable\b"],
    "Mid ($20-100/mo)"    : [r"\$[2-9]\d(?:/mo|per month)?\b", r"\$100\b"],
    "Premium ($100+/mo)"  : [r"\$[1-9]\d{2,}(?:/mo|per month)?\b", r"\bpremium\b", r"\benterprise\b.*\bpricing\b"],
    "One-time Purchase"   : [r"\bone.time\b", r"\blifetime\b", r"\bperpetual\b", r"\blicense\b"],
}

TOOL_CATEGORIES = {
    "Project Management" : [r"\bjira\b", r"\btrello\b", r"\basana\b", r"\bnotion\b", r"\bmonday\b"],
    "Communication"      : [r"\bslack\b", r"\bdiscord\b", r"\bteams\b", r"\bzoom\b"],
    "Development"        : [r"\bgithub\b", r"\bgitlab\b", r"\bvscode\b", r"\bjupyter\b"],
    "Analytics"          : [r"\bgoogle analytics\b", r"\bmixpanel\b", r"\bamplitude\b", r"\bsegment\b"],
    "Marketing"          : [r"\bmailchimp\b", r"\bhubspot\b", r"\bsalesforce\b", r"\bmarketo\b"],
    "Design"             : [r"\bfigma\b", r"\bcanva\b", r"\bsketch\b", r"\badobe\b"],
    "AI Tools"           : [r"\bchatgpt\b", r"\bclaude\b", r"\bmidjourney\b", r"\bgpt\b"],
    "E-commerce"         : [r"\bshopify\b", r"\bwoocommerce\b", r"\betsy\b", r"\bamazon\b"],
}

FRUSTRATION_TRIGGERS = [
    (r"too\s+(?:expensive|costly|pricey)", "Pricing"),
    (r"(?:hard|difficult|complex|complicated)\s+to\s+(?:use|learn|setup|configure)", "UX/Complexity"),
    (r"(?:slow|performance|lag|takes forever)", "Performance"),
    (r"(?:no|missing|lack of|doesn't have)\s+\w+\s+(?:feature|support|integration)", "Missing Features"),
    (r"(?:bad|poor|terrible)\s+(?:support|documentation|help)", "Support"),
    (r"(?:privacy|security|data)\s+(?:concern|issue|problem|risk)", "Privacy/Security"),
    (r"(?:doesn't work|broken|bug|crash)", "Reliability"),
    (r"(?:no|doesn't have)\s+(?:api|integration|webhook)", "Integration"),
]


@dataclass
class CustomerPersona:
    """Extracted customer persona from Reddit posts."""
    roles            : List[str]
    experience_level : str
    budget_range     : str
    tools_used       : List[str]
    frustrations     : List[str]
    goals            : List[str]
    keywords         : List[str]
    sample_quotes    : List[str]
    post_count       : int = 0

    def to_dict(self) -> dict:
        return {
            "roles"          : self.roles,
            "experience_level": self.experience_level,
            "budget_range"   : self.budget_range,
            "tools_used"     : self.tools_used,
            "frustrations"   : self.frustrations[:6],
            "goals"          : self.goals[:5],
            "keywords"       : self.keywords[:12],
            "sample_quotes"  : self.sample_quotes[:4],
            "post_count"     : self.post_count,
        }

    def summary(self) -> str:
        role_str  = " / ".join(self.roles[:2]) if self.roles else "Professional"
        exp_str   = self.experience_level or "Unknown experience"
        budget_str= self.budget_range or "Unknown budget"
        frus_str  = ", ".join(self.frustrations[:2]) if self.frustrations else "various issues"
        return (f"{exp_str} {role_str} with {budget_str} budget. "
                f"Main frustrations: {frus_str}.")


class PersonaBuilder:
    """Builds customer personas from collections of Reddit posts."""

    def build(self, posts: List[RedditPost]) -> CustomerPersona:
        """Extract composite persona from a list of posts."""
        all_text = "\n".join(p.all_text() for p in posts)
        text_l   = all_text.lower()

        # Roles
        roles = []
        for role, patterns in ROLE_PATTERNS.items():
            count = sum(len(re.findall(p, text_l)) for p in patterns)
            if count >= 2:
                roles.append((count, role))
        roles = [r for _, r in sorted(roles, reverse=True)[:3]]

        # Experience
        exp_level = "Unknown"
        for level, patterns in EXPERIENCE_PATTERNS.items():
            if any(re.search(p, text_l) for p in patterns):
                exp_level = level
                break

        # Budget
        budget = "Unknown"
        for brange, patterns in BUDGET_PATTERNS.items():
            count = sum(len(re.findall(p, text_l)) for p in patterns)
            if count >= 1:
                budget = brange
                break

        # Tools used
        tools = []
        for category, patterns in TOOL_CATEGORIES.items():
            if any(re.search(p, text_l) for p in patterns):
                tools.append(category)

        # Frustrations
        frustrations = []
        for pat, label in FRUSTRATION_TRIGGERS:
            if re.search(pat, text_l) and label not in frustrations:
                frustrations.append(label)

        # Goals (simple heuristic)
        goal_patterns = [
            (r"want(?:s)? to (.{10,60}?)(?:\.|,|\n)", "wants"),
            (r"trying to (.{10,60}?)(?:\.|,|\n)", "trying"),
            (r"need(?:s)? (?:a way )?to (.{10,60}?)(?:\.|,|\n)", "needs"),
        ]
        goals = []
        for pat, _ in goal_patterns:
            for m in re.finditer(pat, text_l):
                g = m.group(1).strip()[:80]
                if len(g) > 10 and g not in goals:
                    goals.append(g)
            if len(goals) >= 5:
                break

        # Keywords
        from ..analyzer.intelligence import _extract_keywords
        kw_pairs = _extract_keywords(all_text, top_n=15)
        keywords = [k for k, _ in kw_pairs]

        # Sample quotes (high-score comments)
        quotes = []
        for post in posts:
            if post.selftext and len(post.selftext) > 30:
                quotes.append(post.selftext[:180].strip())
            for c in post.comments[:3]:
                if c.is_substantial and c.score >= 5:
                    quotes.append(c.body[:180].strip())
            if len(quotes) >= 6:
                break

        return CustomerPersona(
            roles            = roles or ["Professional"],
            experience_level = exp_level,
            budget_range     = budget,
            tools_used       = tools,
            frustrations     = frustrations,
            goals            = goals[:5],
            keywords         = keywords,
            sample_quotes    = quotes[:4],
            post_count       = len(posts),
        )
