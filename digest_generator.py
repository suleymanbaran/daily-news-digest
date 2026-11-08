from datetime import datetime
from typing import Dict, Any, List

CATEGORY_TITLES = {
    "tech": "Tech & AI Engineering",
    "europe": "Italy & Europe (Jobs & Startups)",
    "turkey": "Turkey (News & Economy)",
    "finance": "Finance & Macroeconomics",
    "world": "World News",
}

def generate_digest_markdown(
    processed_data: Dict[str, Any],
    feed_problems: List[Dict[str, str]],
    date_str: str = None
) -> str:
    """Generate clean, structured Markdown digest according to exact user specifications."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    lines = []
    lines.append(f"# Daily News Digest — {date_str}\n")

    items = processed_data.get("items", [])

    # Group items by category
    by_category = {}
    for it in items:
        cat = it.get("category", "tech")
        by_category.setdefault(cat, []).append(it)

    for cat_key, cat_heading in CATEGORY_TITLES.items():
        cat_items = by_category.get(cat_key, [])
        if not cat_items:
            continue

        lines.append(f"## {cat_heading}\n")
        for it in cat_items:
            title = it.get("title", "").strip()
            summary = it.get("summary", "").strip()
            why = it.get("why_it_matters", "").strip()
            turkey_comp = it.get("turkey_comparison")
            sources = it.get("items", [])

            # Source attribution and links
            source_parts = []
            primary_link = "#"
            for s in sources:
                s_name = s.get("source_name", "Source")
                s_type = s.get("source_type")
                s_link = s.get("link", "")
                if s_link and primary_link == "#":
                    primary_link = s_link
                if s_type:
                    source_parts.append(f"[{s_name} ({s_type})]({s_link})")
                else:
                    source_parts.append(f"[{s_name}]({s_link})")

            sources_str = ", ".join(source_parts) if source_parts else f"[Source]({primary_link})"

            # Format per prompt:
            # - Title (source name, source_type if Turkey) - link
            # - 1-2 sentence summary
            # - "Why it matters to me:" one short sentence
            lines.append(f"- **{title}** ({sources_str})")
            lines.append(f"  - {summary}")
            if turkey_comp:
                lines.append(f"  - *Coverage comparison:* {turkey_comp}")
            lines.append(f"  - **Why it matters to me:** {why}\n")

    # Vocabulary section
    lines.append("## Vocabulary\n")
    
    # English Vocabulary
    lines.append("### English (B2–C1 Level)")
    vocab_en = processed_data.get("vocabulary_english", [])
    if vocab_en:
        for v in vocab_en:
            word = v.get("word")
            level = v.get("level", "B2")
            tr = v.get("turkish_meaning")
            ex = v.get("example_usage")
            lines.append(f"- **{word}** ({level}): {tr} — *\"{ex}\"*")
    else:
        lines.append("- No new vocabulary items extracted today.")
    lines.append("")

    # Italian Vocabulary
    lines.append("### Italian (A1–A2 Level)")
    vocab_it = processed_data.get("vocabulary_italian", [])
    if vocab_it:
        for v in vocab_it:
            art = v.get("article", "").strip()
            word = v.get("word", "").strip()
            gender = v.get("gender", "")
            en = v.get("english_meaning", "")
            lines.append(f"- **{art} {word}** ({gender}): {en}")
    else:
        lines.append("- No Italian vocabulary items extracted today.")
    lines.append("")

    # Delivery Channel
    lines.append("## Delivery Channel")
    lines.append("Telegram Bot (Scheduled via GitHub Actions)\n")

    # Feed Problems Section
    if feed_problems:
        lines.append("## Feed Problems")
        lines.append("The following feeds were unreachable or returned 0 entries and were skipped:\n")
        for prob in feed_problems:
            lines.append(f"- **{prob.get('name')}** (`{prob.get('feed_url')}`): {prob.get('reason')}")
        lines.append("")

    # Run metadata footer
    model = processed_data.get("model_used", "N/A")
    t_in = processed_data.get("tokens_prompt", 0)
    t_out = processed_data.get("tokens_completion", 0)
    cost = processed_data.get("estimated_cost_usd", 0.0)
    lines.append("---")
    lines.append(f"*Run Summary: Model: `{model}` | Tokens: prompt={t_in}, completion={t_out} | Est. Cost: ${cost:.6f}*")

    return "\n".join(lines)
