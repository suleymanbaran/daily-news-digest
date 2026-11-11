import os
import json
import time
import re
from typing import List, Dict, Any, Tuple

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll",
    "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself",
    "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not",
    "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll",
    "she's", "should", "shouldn't", "so", "some", "such", "than", "that", "that's",
    "the", "their", "theirs", "them", "themselves", "then", "there", "there's",
    "these", "they", "they'd", "they'll", "they're", "they've", "this", "those",
    "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we",
    "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when",
    "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why",
    "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll",
    "you're", "you've", "your", "yours", "yourself", "yourselves",
    # Turkish common stop words
    "ve", "ile", "bir", "bu", "da", "de", "icin", "için", "ne", "gibi", "kadar",
    "sonra", "en", "daha", "cok", "çok", "her", "ama", "fakat", "ya", "ise", "olan"
}

# Simple domain relevance keywords for pre-filtering
TECH_KEYWORDS = {
    "ai", "llm", "model", "agent", "software", "engineer", "engineering", "code",
    "coding", "developer", "python", "system", "architecture", "benchmark", "gpu",
    "cloud", "inference", "eval", "algorithm", "database", "api", "framework",
    "open-source", "weights", "data", "deepmind", "openai", "anthropic", "meta",
    "google", "huggingface", "robotics", "release", "paper", "research", "interview",
    "career", "startup", "scale", "performance", "compiler", "chip"
}

EUROPE_KEYWORDS = {
    "italy", "italia", "milan", "rome", "turin", "europe", "european", "startup",
    "startups", "tech", "job", "jobs", "hiring", "talent", "engineer", "founder",
    "funding", "vc", "venture", "investment", "hub", "ai", "visa", "university",
    "degree", "innovation", "economy", "growth", "ansa"
}

TURKEY_KEYWORDS = {
    "turkey", "türkiye", "turk", "türk", "ankara", "istanbul", "erdogan", "erdoğan",
    "tcmb", "merkez bankası", "lira", "tl", "try", "enflasyon", "inflation", "faiz",
    "ekonomi", "economy", "bakan", "meclis", "seçim", "hükümet", "dolar", "euro",
    "yargı", "chp", "akp", "dışişleri", "siyaset", "politika", "büyüme", "ihracat"
}

FINANCE_KEYWORDS = {
    "fed", "federal reserve", "ecb", "rates", "interest rate", "inflation", "cpi",
    "gdp", "yield", "bonds", "treasury", "central bank", "powell", "lagarde",
    "dollar", "euro", "lira", "try", "eur", "usd", "market", "stocks", "wall street",
    "economy", "recession", "cuts", "hike", "monetary", "banking", "debt"
}

def load_state(state_path: str) -> Dict[str, Any]:
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
                state.setdefault("seen_urls", {})
                state.setdefault("seen_titles", {})
                return state
        except Exception:
            return {"seen_urls": {}, "seen_titles": {}}
    return {"seen_urls": {}, "seen_titles": {}}

def save_state(state_path: str, state: Dict[str, Any], max_age_days: int = 14) -> None:
    now = time.time()
    cutoff = now - (max_age_days * 86400)
    for key in ("seen_urls", "seen_titles"):
        state[key] = {k: ts for k, ts in state.get(key, {}).items() if ts >= cutoff}
    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def normalize_title(title: str) -> str:
    """Canonical form for title-based dedup (Google News proxy URLs rotate per fetch)."""
    return re.sub(r"[^a-z0-9çğıöşü ]+", "", (title or "").lower()).strip()[:100]

def tokenize(text: str) -> set:
    words = re.findall(r"[a-zA-Z0-9çğıöşüÇĞİÖŞÜ]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}

def matches_keywords(title: str, snippet: str, keyword_set: set) -> bool:
    tokens = tokenize(title + " " + snippet)
    return bool(tokens & keyword_set)

def pre_filter_items(items: List[Dict[str, Any]], seen_urls: Dict[str, float], max_age_hours: int = 48, seen_titles: Dict[str, float] = None) -> List[Dict[str, Any]]:
    """
    1. Filter already seen items (by URL and by normalized title).
    2. Filter items older than max_age_hours (if timestamp available).
    3. Filter out items that do not match general interest heuristics.
    """
    now = time.time()
    age_limit_seconds = max_age_hours * 3600
    seen_titles = seen_titles if seen_titles is not None else {}
    kept = []

    for item in items:
        url = item.get("link") or item.get("id")
        if not url or url in seen_urls:
            continue
        norm_title = normalize_title(item.get("title", ""))
        if norm_title and norm_title in seen_titles:
            continue

        # Age check
        ts = item.get("timestamp")
        if ts and (now - ts > age_limit_seconds):
            continue

        cat = item.get("category", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        # High-signal feeds don't need aggressive keyword dropping
        src = item.get("source_name", "").lower()
        if any(h in src for h in ["openai", "google ai", "anthropic", "latent space", "simon willison", "hugging face"]):
            kept.append(item)
            continue

        # Primary central bank & statistics feeds are high signal
        if any(h in src for h in ["federal reserve", "ecb", "eurostat", "istat", "tcmb"]):
            kept.append(item)
            continue

        # Category keyword check
        passed = False
        if cat == "tech" and matches_keywords(title, snippet, TECH_KEYWORDS):
            passed = True
        elif cat == "europe" and (matches_keywords(title, snippet, EUROPE_KEYWORDS) or matches_keywords(title, snippet, TECH_KEYWORDS)):
            passed = True
        elif cat == "turkey" and matches_keywords(title, snippet, TURKEY_KEYWORDS):
            passed = True
        elif cat == "finance" and matches_keywords(title, snippet, FINANCE_KEYWORDS):
            passed = True
        elif cat == "world":
            # For world news, keep items that intersect with geopolitics, tech, or macro economy
            if matches_keywords(title, snippet, TECH_KEYWORDS | FINANCE_KEYWORDS | {"war", "peace", "election", "president", "summit", "trade", "climate", "ai"}):
                passed = True
        elif cat == "sport":
            # Hand-picked sport feeds (F1, football, Süper Lig) are always relevant
            passed = True

        # If it passed or has strong title content, keep
        if passed:
            kept.append(item)

    # Fallback/supplement: if kept has fewer than 8 items (e.g. manual re-runs on same day),
    # backfill with recent items so the digest is always balanced across Tech, Europe, Turkey, Finance.
    if len(kept) < 8:
        already_kept_urls = {it.get("link") or it.get("id") for it in kept}
        for item in items:
            url = item.get("link") or item.get("id")
            if url in already_kept_urls or url in seen_urls:
                continue
            norm_title = normalize_title(item.get("title", ""))
            if norm_title and norm_title in seen_titles:
                continue
            ts = item.get("timestamp")
            if ts and (now - ts > age_limit_seconds):
                continue
            cat = item.get("category", "")
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            passed = False
            if cat == "tech" and matches_keywords(title, snippet, TECH_KEYWORDS):
                passed = True
            elif cat == "europe" and (matches_keywords(title, snippet, EUROPE_KEYWORDS) or matches_keywords(title, snippet, TECH_KEYWORDS)):
                passed = True
            elif cat == "turkey" and matches_keywords(title, snippet, TURKEY_KEYWORDS):
                passed = True
            elif cat == "finance" and matches_keywords(title, snippet, FINANCE_KEYWORDS):
                passed = True
            elif cat == "world" and matches_keywords(title, snippet, TECH_KEYWORDS | FINANCE_KEYWORDS | {"war", "peace", "election", "president", "summit", "trade", "climate", "ai"}):
                passed = True
            elif cat == "sport":
                passed = True
            if passed:
                kept.append(item)
                already_kept_urls.add(url)

    return kept

def cluster_items(items: List[Dict[str, Any]], threshold: float = 0.35) -> List[Dict[str, Any]]:
    """
    Cluster items that cover the same story.
    Returns a list of cluster dicts:
    {
      "cluster_id": int,
      "category": str,
      "primary_title": str,
      "items": List[Dict[str, Any]]
    }
    """
    clusters = []
    
    # Process within categories
    by_category = {}
    for item in items:
        by_category.setdefault(item.get("category", "other"), []).append(item)

    cluster_counter = 1
    for cat, cat_items in by_category.items():
        cat_clusters = []
        for item in cat_items:
            item_tokens = tokenize(item["title"])
            best_cluster = None
            best_score = 0.0

            for c in cat_clusters:
                c_tokens = c["tokens"]
                if not item_tokens or not c_tokens:
                    continue
                intersection = item_tokens & c_tokens
                union = item_tokens | c_tokens
                jaccard = len(intersection) / len(union) if union else 0.0
                if jaccard > best_score:
                    best_score = jaccard
                    best_cluster = c

            if best_cluster and best_score >= threshold:
                best_cluster["items"].append(item)
                best_cluster["tokens"].update(item_tokens)
            else:
                cat_clusters.append({
                    "cluster_id": cluster_counter,
                    "category": cat,
                    "primary_title": item["title"],
                    "tokens": item_tokens,
                    "items": [item]
                })
                cluster_counter += 1

        clusters.extend(cat_clusters)

    return clusters
