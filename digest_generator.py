from datetime import datetime
from typing import Dict, Any, List

CATEGORY_TITLES = {
    "tech": "🤖 Tech & AI",
    "europe": "🇪🇺 Italy & Europe — Jobs & Startups",
    "turkey": "🇹🇷 Türkiye — News & Economy",
    "finance": "💰 Finance & Economy",
    "world": "🌍 World News",
}

def _format_item(it: Dict[str, Any]) -> List[str]:
    lines = []
    title = (it.get("title") or "").strip()
    tldr = (it.get("tldr") or "").strip()
    summary = (it.get("summary") or "").strip()
    why = (it.get("why_it_matters") or "").strip()
    turkey_comp = it.get("turkey_comparison")
    sources = it.get("items", [])

    source_parts = []
    for s in sources:
        s_name = s.get("source_name", "Source")
        s_type = s.get("source_type")
        s_link = s.get("link", "")
        label = f"{s_name} ({s_type})" if s_type else s_name
        source_parts.append(f"[{label}]({s_link})" if s_link else label)
    sources_str = " · ".join(source_parts) if source_parts else "Source link unavailable"

    lines.append(f"🔹 *{title}*")
    if tldr:
        lines.append(f"⚡ {tldr}")
    if summary:
        lines.append(f"📝 {summary}")
    if turkey_comp:
        lines.append(f"🗞️ How sources compare: {turkey_comp}")
    if why:
        lines.append(f"💡 Why it matters to you: {why}")
    lines.append(f"🔗 {sources_str}")
    lines.append("")
    return lines

def generate_digest_markdown(
    processed_data: Dict[str, Any],
    feed_problems: List[Dict[str, str]],
    date_str: str = None
) -> str:
    """Generate the emoji-rich, easy-to-read digest (Markdown, Telegram-compatible)."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    lines = []
    lines.append(f"📰 *Daily News Digest — {date_str}*")
    lines.append("☀️ Good morning! Here's what matters for you today:\n")

    items = processed_data.get("items", [])

    if not items:
        lines.append("😴 No stories passed today's filters — check the feed problems below.\n")
    else:
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            cat = it.get("category", "world")
            by_category.setdefault(cat, []).append(it)

        for cat_key, cat_heading in CATEGORY_TITLES.items():
            cat_items = by_category.get(cat_key, [])
            if not cat_items:
                continue
            cat_items.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            lines.append(f"—— {cat_heading} ——\n")
            for it in cat_items:
                lines.extend(_format_item(it))

    # Vocabulary section
    lines.append("📚 *Word of the Day — English (B2–C1)*")
    vocab_en = processed_data.get("vocabulary_english", [])
    if vocab_en:
        for v in vocab_en:
            word = v.get("word")
            level = v.get("level", "B2")
            tr = v.get("turkish_meaning")
            ex = v.get("example_usage")
            lines.append(f"• *{word}* ({level}): {tr}")
            if ex:
                lines.append(f"   ✏️ \"{ex}\"")
    else:
        lines.append("• No new vocabulary items extracted today.")
    lines.append("")

    lines.append("🇮🇹 *Italian Word of the Day (A1–A2) — with English translations*")
    vocab_it = processed_data.get("vocabulary_italian", [])
    if vocab_it:
        for v in vocab_it:
            art = (v.get("article") or "").strip()
            word = (v.get("word") or "").strip()
            en = v.get("english_meaning", "")
            lines.append(f"• *{art} {word}* — {en}")
    else:
        lines.append("• No Italian vocabulary items extracted today.")
    lines.append("")

    # Feed problems: keep Telegram message clean, details stay in the repo file
    if feed_problems:
        lines.append(f"⚠️ {len(feed_problems)} feed(s) unreachable today — skipped.")
        for prob in feed_problems:
            lines.append(f"   - {prob.get('name')}: {prob.get('reason')}")
        lines.append("")

    model = processed_data.get("model_used", "N/A")
    t_in = processed_data.get("tokens_prompt", 0)
    t_out = processed_data.get("tokens_completion", 0)
    cost = processed_data.get("estimated_cost_usd", 0.0)
    lines.append("—————————————")
    lines.append(f"🤖 Model: {model} | Tokens: {t_in} in / {t_out} out | Cost: ${cost:.6f}")
    lines.append("✅ Delivered via Telegram · Scheduled daily by GitHub Actions")

    return "\n".join(lines)
