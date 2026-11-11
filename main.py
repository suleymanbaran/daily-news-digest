import argparse
import json
import os
import sys
import time
from datetime import datetime

from fetcher import fetch_all_sources
from dedup_filter import (
    load_state,
    save_state,
    pre_filter_items,
    cluster_items,
    normalize_title
)
from llm_scorer import process_clusters
from digest_generator import generate_digest_markdown

def main():
    parser = argparse.ArgumentParser(description="Personal Daily News Digest Agent")
    parser.add_argument("--config", default="sources.json", help="Path to sources.json")
    parser.add_argument("--state", default="state.json", help="Path to state.json")
    parser.add_argument("--log", default="run-log.json", help="Path to run-log.json")
    parser.add_argument("--output-dir", default=".", help="Directory to save digest markdown")
    parser.add_argument("--max-age-hours", type=int, default=48, help="Max item age in hours")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode (no LLM calls, no delivery, no state changes)")
    args = parser.parse_args()

    start_time = time.time()
    today_str = datetime.now().strftime("%Y-%m-%d")
    output_filename = os.path.join(args.output_dir, f"digest-{today_str}.md")

    print(f"=== Personal Daily News Digest ({today_str}) ===")
    has_llm_key = bool(
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    )
    if args.dry_run:
        print("[MODE] Running in DRY-RUN mode (LLM calls disabled, heuristics enabled).")
    elif not has_llm_key:
        print("[NOTICE] No OPENAI_API_KEY / GROQ_API_KEY / GEMINI_API_KEY found. Defaulting to heuristic mode.", file=sys.stderr)

    # 1. Load Sources
    if not os.path.exists(args.config):
        print(f"[ERROR] Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    with open(args.config, "r", encoding="utf-8") as f:
        sources = json.load(f)
    print(f"Loaded {len(sources)} sources from {args.config}.")

    # 2. Fetch Feeds
    print("Fetching feeds (read-only RSS/Atom, no full-page scraping)...")
    raw_items, feed_problems = fetch_all_sources(sources)
    print(f"Fetched {len(raw_items)} total items across all feeds.")
    if feed_problems:
        print(f"Encountered {len(feed_problems)} feed issues (will be logged).")

    # 3. Deduplicate and Pre-filter
    state = load_state(args.state)
    seen_urls = state.get("seen_urls", {})
    seen_titles = state.setdefault("seen_titles", {})
    filtered_items = pre_filter_items(raw_items, seen_urls, max_age_hours=args.max_age_hours, seen_titles=seen_titles)
    print(f"Items remaining after deduplication and rule-based pre-filtering: {len(filtered_items)}.")

    # 4. Cluster similar stories
    clusters = cluster_items(filtered_items)
    print(f"Grouped into {len(clusters)} distinct story clusters.")

    # 5. Score & Summarize
    print("Scoring relevance and preparing summaries...")
    processed_data = process_clusters(clusters, dry_run=args.dry_run)
    items_in_digest = len(processed_data.get("items", []))
    print(f"Selected {items_in_digest} top stories for today's digest.")

    # 6. Generate Digest Markdown
    digest_md = generate_digest_markdown(processed_data, feed_problems, date_str=today_str)
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(digest_md)
    print(f"Saved digest to {output_filename}.")

    # 7. Delivery via Telegram (if tokens configured)
    telegram_configured = bool(os.environ.get("TELEGRAM_BOT_TOKEN")) and bool(os.environ.get("TELEGRAM_CHAT_ID"))
    telegram_delivered = None
    if args.dry_run:
        print("[INFO] Dry-run: skipping Telegram delivery.")
    elif not telegram_configured:
        print("[WARN] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set; digest saved to file only.", file=sys.stderr)
    else:
        from delivery import send_telegram_digest
        print("Sending digest to Telegram...")
        telegram_delivered = send_telegram_digest(digest_md)
        if telegram_delivered:
            print("Successfully delivered digest to Telegram.")
        else:
            print("[ERROR] Telegram delivery failed.", file=sys.stderr)

    # 8. Decide run success. A run is successful only if it produced a digest AND
    #    (delivery wasn't required or it actually arrived). On failure, state is NOT
    #    updated, so the next run retries the same articles, and the process exits
    #    non-zero so GitHub Actions shows the failure.
    delivery_ok = args.dry_run or not telegram_configured or bool(telegram_delivered)
    success = items_in_digest > 0 and delivery_ok

    # 9. Update State (only on real, delivered runs — never in dry-run)
    if success and not args.dry_run:
        for it in filtered_items:
            url = it.get("link") or it.get("id")
            if url:
                seen_urls[url] = time.time()
            norm_title = normalize_title(it.get("title", ""))
            if norm_title:
                seen_titles[norm_title] = time.time()
        save_state(args.state, state)
        print(f"Updated state file {args.state} with {len(seen_urls)} tracked URLs and {len(seen_titles)} tracked titles.")
    else:
        print("[INFO] State not updated (dry-run or unsuccessful run); articles will be retried next run.")

    # 10. Log Run
    duration = round(time.time() - start_time, 2)
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "date": today_str,
        "dry_run": args.dry_run,
        "success": success,
        "sources_configured": len(sources),
        "items_fetched": len(raw_items),
        "items_kept_after_prefilter": len(filtered_items),
        "clusters_formed": len(clusters),
        "items_in_digest": items_in_digest,
        "feed_problems_count": len(feed_problems),
        "telegram_configured": telegram_configured,
        "telegram_delivered": telegram_delivered,
        "model_used": processed_data.get("model_used"),
        "tokens_prompt": processed_data.get("tokens_prompt", 0),
        "tokens_completion": processed_data.get("tokens_completion", 0),
        "estimated_cost_usd": processed_data.get("estimated_cost_usd", 0.0),
        "duration_seconds": duration,
        "output_file": output_filename
    }

    run_logs = []
    if os.path.exists(args.log):
        try:
            with open(args.log, "r", encoding="utf-8") as f:
                run_logs = json.load(f)
                if not isinstance(run_logs, list):
                    run_logs = [run_logs]
        except Exception:
            run_logs = []

    run_logs.append(log_entry)
    with open(args.log, "w", encoding="utf-8") as f:
        json.dump(run_logs, f, indent=2)
    print(f"Logged run summary to {args.log} (Duration: {duration}s, Cost: ${log_entry['estimated_cost_usd']:.6f}).")

    if not success:
        reason = []
        if items_in_digest == 0:
            reason.append("digest is empty (no items passed filtering or all feeds failed)")
        if telegram_delivered is False:
            reason.append("Telegram delivery failed")
        print(f"[ERROR] Run unsuccessful: {'; '.join(reason)}. Exiting with code 1.", file=sys.stderr)
        sys.exit(1)

    print("Digest generation complete. Exiting cleanly.")
    sys.exit(0)

if __name__ == "__main__":
    main()
