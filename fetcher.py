import re
import html
import calendar
from typing import List, Dict, Any, Tuple
import requests
import feedparser

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

def clean_html(raw_html: str) -> str:
    """Strip HTML tags and unescape entities to return clean plain text."""
    if not raw_html:
        return ""
    # Remove script and style elements
    clean = re.sub(r"<(script|style).*?>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    clean = re.sub(r"<[^<]+?>", " ", clean)
    # Decode HTML entities
    clean = html.unescape(clean)
    # Collapse consecutive whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean

def fetch_feed(source: Dict[str, Any], timeout: int = 10) -> Tuple[List[Dict[str, Any]], str]:
    """
    Fetch and parse a single RSS/Atom feed.
    Returns (items, error_reason). error_reason is empty string if successful.
    """
    url = source.get("feed_url")
    name = source.get("name", "Unknown Source")
    category = source.get("category", "general")
    source_type = source.get("source_type")

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        if resp.status_code != 200:
            return [], f"HTTP {resp.status_code}"

        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            return [], f"Feed parse error: {parsed.bozo_exception}"

        if not parsed.entries:
            return [], "Feed returned 0 items (empty or deprecated)"

        items = []
        for entry in parsed.entries:
            title = clean_html(entry.get("title", ""))
            link = entry.get("link", "").strip()
            
            # Extract summary or snippet
            raw_summary = (
                entry.get("summary")
                or entry.get("description")
                or (entry.get("content", [{}])[0].get("value") if entry.get("content") else "")
                or ""
            )
            snippet = clean_html(raw_summary)

            # Published timestamp (feedparser returns UTC struct_time)
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            timestamp = calendar.timegm(published_parsed) if published_parsed else None

            if not title or not link:
                continue

            items.append({
                "id": link or entry.get("id"),
                "title": title,
                "snippet": snippet[:1000],  # keep snippet compact to prevent excessive token usage
                "link": link,
                "timestamp": timestamp,
                "source_name": name,
                "category": category,
                "source_type": source_type,
            })

        return items, ""

    except requests.exceptions.Timeout:
        return [], "Request timed out"
    except requests.exceptions.RequestException as e:
        return [], f"Network error: {str(e)}"
    except Exception as e:
        return [], f"Unexpected error: {str(e)}"

def fetch_all_sources(sources: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    Fetch all sources sequentially or in batch.
    Returns (all_items, feed_problems).
    """
    all_items = []
    feed_problems = []

    for src in sources:
        items, err = fetch_feed(src)
        if err:
            feed_problems.append({
                "name": src.get("name", "Unknown"),
                "feed_url": src.get("feed_url", ""),
                "reason": err,
            })
        else:
            all_items.extend(items)

    return all_items, feed_problems
