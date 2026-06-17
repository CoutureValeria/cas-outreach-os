"""
Indeed-Intel — Task-Based Job Posting Sourcing Pipeline

Fetches job postings from Platsbanken (Arbetsförmedlingen API) for Stockholm,
scores each by what fraction of listed tasks are automatable (booking/scheduling/
routing/admin), and pushes high-fit leads to the CAS email engine.

Scoring principle:
  automation_fit_score = (automatable_tasks / total_tasks) * 100
  >= 50 → SEND | < 50 → IGNORE

Run:
  python main.py                    # full pipeline, --no-push by default (safe)
  python main.py --push             # actually push SEND leads to email engine
  python main.py --max 10           # limit postings per query (default from settings)
  python main.py --no-push          # explicit dry run (default)

Output:
  data/results_TIMESTAMP.json       — full scored results
  data/send_leads_TIMESTAMP.json    — SEND bucket only
"""

import argparse
import json
import os
from datetime import datetime

from collectors.platsbanken import fetch_postings
from collectors.openclaw_client import get_page_text
from scoring.task_scorer    import score_all, generate_email
from exporters.webhook_client import send_all
from enrichment.pipeline import run_pipeline
from config.settings import DATA_DIR, SCORE_THRESHOLD, RESULTS_PER_QUERY


def _tier(score: int) -> str:
    if score >= 75:
        return "HIGH"
    if score >= SCORE_THRESHOLD:
        return "MODERATE"
    if score >= 25:
        return "LOW"
    return "NONE"


def _print_distribution(scored: list[dict]) -> dict:
    buckets = {"0-24": 0, "25-49": 0, "50-74": 0, "75-100": 0, "error": 0}
    for p in scored:
        if p.get("bucket") == "error":
            buckets["error"] += 1
            continue
        s = p.get("automation_fit_score", 0)
        if s >= 75:
            buckets["75-100"] += 1
        elif s >= 50:
            buckets["50-74"] += 1
        elif s >= 25:
            buckets["25-49"] += 1
        else:
            buckets["0-24"] += 1
    return buckets


def _pick_examples(scored: list[dict]) -> dict:
    """Pick one example from each score tier for the report."""
    examples = {}
    tiers = [("HIGH", 75, 100), ("MODERATE", 50, 74), ("LOW", 25, 49), ("NONE", 0, 24)]
    for label, lo, hi in tiers:
        candidates = [
            p for p in scored
            if lo <= p.get("automation_fit_score", 0) <= hi
            and p.get("bucket") != "error"
            and p.get("score_data")
        ]
        if candidates:
            # Pick highest score in tier
            examples[label] = max(candidates, key=lambda p: p.get("automation_fit_score", 0))
    return examples


def _print_example(label: str, posting: dict) -> None:
    score      = posting.get("automation_fit_score", 0)
    score_data = posting.get("score_data", {}) or {}
    auto_tasks = score_data.get("automatable_tasks", [])
    non_auto   = score_data.get("non_automatable_tasks", [])
    angle      = score_data.get("automation_angle", "")
    total      = score_data.get("total_tasks", 0)
    confidence = score_data.get("confidence", "?")

    print(f"\n{'-'*60}")
    print(f"  [{label}]  {posting.get('headline', '?')}")
    print(f"  Employer:  {posting.get('employer_name', '?')}")
    print(f"  Score:     {score}%  ({len(auto_tasks)}/{total} tasks automatable) [confidence: {confidence}]")
    print(f"  URL:       {posting.get('webpage_url', '?')}")
    if angle:
        print(f"  Angle:     {angle}")
    if auto_tasks:
        print("  AUTOMATABLE tasks:")
        for t in auto_tasks:
            print(f"    + {t['task']}")
    if non_auto:
        print("  NOT AUTOMATABLE tasks:")
        for t in non_auto:
            print(f"    - {t['task']}")

    if label in ("HIGH", "MODERATE"):
        print(f"\n  Generated email:")
        print(f"  {'-'*50}")
        email = generate_email(posting, score_data)
        for line in email.split("\n"):
            print(f"  {line}")
    print(f"{'-'*60}")


def run(max_per_query: int = RESULTS_PER_QUERY, push: bool = False) -> dict:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}")
    print(f"  INDEED-INTEL  --  Task-Based Job Posting Sourcing")
    print(f"  {ts}")
    print(f"{'='*60}\n")

    # Phase 1: Fetch
    print("--- Phase 1: Fetch from Platsbanken ---")
    postings = fetch_postings(max_per_query=max_per_query)
    if not postings:
        print("No postings fetched. Aborting.")
        return {}

    print(f"\n--- Phase 2: Score {len(postings)} postings with Claude ---")
    scored = score_all(postings)

    send_leads = [p for p in scored if p.get("bucket") == "SEND"]
    ignore_leads = [p for p in scored if p.get("bucket") == "IGNORE"]
    error_count  = sum(1 for p in scored if p.get("bucket") == "error")

    # Distribution
    dist = _print_distribution(scored)

    print(f"\n{'='*60}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  Total postings scored: {len(scored)}")
    print(f"  SEND (>= {SCORE_THRESHOLD}%):     {len(send_leads)}")
    print(f"  IGNORE (< {SCORE_THRESHOLD}%):    {len(ignore_leads)}")
    print(f"  Scoring errors:       {error_count}")
    print(f"\n  Score distribution:")
    print(f"    0-24%  (not automatable):  {dist['0-24']}")
    print(f"   25-49%  (low signal):        {dist['25-49']}")
    print(f"   50-74%  (MODERATE - SEND):   {dist['50-74']}")
    print(f"   75-100% (HIGH - SEND):       {dist['75-100']}")

    # Example postings at different tiers
    print(f"\n{'='*60}")
    print(f"  EXAMPLE POSTINGS BY TIER")
    print(f"{'='*60}")
    examples = _pick_examples(scored)
    for label in ["HIGH", "MODERATE", "LOW", "NONE"]:
        if label in examples:
            _print_example(label, examples[label])

    # Phase 2.5: Website enrichment for SEND leads
    print(f"\n--- Phase 2.5: Website enrichment for {len(send_leads)} SEND leads ---")
    enriched_count = 0
    for lead in send_leads:
        website = lead.get("employer_url")
        if not website:
            print(f"  SKIP (no website): {lead.get('employer_name', '?')}")
            continue

        raw_text = get_page_text(website)
        if not raw_text:
            print(f"  SKIP (fetch failed): {lead.get('employer_name', '?')}")
            lead["_enrichment"] = None
            continue

        enrich = run_pipeline(raw_text, str(website))
        lead["_enrichment"] = enrich

        dm_name = None
        if enrich.get("extraction_success"):
            dm = (enrich.get("data") or {}).get("decision_maker") or {}
            dm_name = dm.get("name")
            if dm_name and not lead.get("_contact_name"):
                lead["_contact_name"] = dm_name
            enriched_count += 1

        print(
            f"  {lead.get('employer_name', '?')[:40]}: "
            f"page={len(raw_text)} chars | "
            f"page_preview={repr(raw_text[:200])} | "
            f"score={enrich.get('automation_score', 0)} | "
            f"dm={dm_name or 'none'} | "
            f"success={enrich.get('extraction_success')}"
        )

    print(f"\n  Enrichment complete: {enriched_count}/{len(send_leads)} successful")

    # Save results
    os.makedirs(DATA_DIR, exist_ok=True)
    file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    results_file = os.path.join(DATA_DIR, f"results_{file_ts}.json")
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  Full results saved: {results_file}")

    send_file = os.path.join(DATA_DIR, f"send_leads_{file_ts}.json")
    with open(send_file, "w", encoding="utf-8") as f:
        json.dump(send_leads, f, ensure_ascii=False, indent=2, default=str)
    print(f"  SEND leads saved:   {send_file}")

    # Phase 3: Push (only if --push flag passed)
    push_result = {}
    if push:
        print(f"\n--- Phase 3: Push {len(send_leads)} SEND leads to email engine ---")
        push_result = send_all(send_leads)
        print(f"  Push result: {push_result}")
    else:
        print(f"\n--- Phase 3: SKIPPED (run with --push to send to email engine) ---")
        print(f"  {len(send_leads)} SEND leads ready to push when you give the go-ahead.")

    return {
        "total":    len(scored),
        "send":     len(send_leads),
        "ignore":   len(ignore_leads),
        "errors":   error_count,
        "dist":     dist,
        "push":     push_result,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Indeed-Intel job posting sourcing pipeline")
    parser.add_argument("--push",    action="store_true",  help="Push SEND leads to email engine")
    parser.add_argument("--no-push", action="store_true",  help="Skip push (default behavior)")
    parser.add_argument("--max",     type=int, default=RESULTS_PER_QUERY,
                        help=f"Max postings per search query (default: {RESULTS_PER_QUERY})")
    args = parser.parse_args()

    result = run(max_per_query=args.max, push=args.push)
