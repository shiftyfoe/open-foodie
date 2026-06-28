#!/usr/bin/env python3
"""Evaluate heuristic classifier quality via a stratified human-annotated sample.

Usage:
  # Step 1 – generate sample (run once, commit the output)
  python3 eval_classify.py sample [--size N]

  # Step 2 – open eval/sample.json and fill in "correct_tags" for each post
  #          Use [] for "no tags", or the list of tags that truly apply.

  # Step 3 – compute metrics
  python3 eval_classify.py score
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

DATA_FILE = Path("data/posts.json")
EVAL_DIR = Path("eval")
SAMPLE_FILE = EVAL_DIR / "sample.json"

ALL_TAGS = [
    "cafe", "hawker", "restaurant", "bakery", "dessert", "drinks",
    "chinese", "japanese", "korean", "thai", "western", "indian",
    "malay", "vietnamese",
]

SEED = 42


# ---------------------------------------------------------------------------
# Sample generation
# ---------------------------------------------------------------------------

def build_sample(posts: list[dict], target_per_tag: int = 8, untagged_target: int = 25) -> list[dict]:
    """Stratified sample: posts per-tag bucket + untagged bucket.

    Strategy:
    - For each tag, draw up to `target_per_tag` posts that carry that tag.
    - Separately draw `untagged_target` posts that have no tags at all.
    - Deduplicate by id so multi-tag posts count once.
    - Shuffle deterministically.
    """
    rng = random.Random(SEED)

    selected_ids: set[str] = set()
    selected: list[dict] = []

    # Per-tag stratum
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for p in posts:
        for tag in p.get("tags", []):
            by_tag[tag].append(p)

    for tag in ALL_TAGS:
        bucket = by_tag.get(tag, [])
        picks = rng.sample(bucket, min(target_per_tag, len(bucket)))
        for p in picks:
            if p["id"] not in selected_ids:
                selected_ids.add(p["id"])
                selected.append(p)

    # Untagged stratum
    untagged = [p for p in posts if not p.get("tags")]
    picks = rng.sample(untagged, min(untagged_target, len(untagged)))
    for p in picks:
        if p["id"] not in selected_ids:
            selected_ids.add(p["id"])
            selected.append(p)

    rng.shuffle(selected)
    return selected


def sample_command(args: argparse.Namespace) -> None:
    db = json.loads(DATA_FILE.read_text())
    posts = db.get("posts", [])

    target_per_tag = args.size
    untagged_target = max(20, args.size * 2)
    sample = build_sample(posts, target_per_tag=target_per_tag, untagged_target=untagged_target)

    EVAL_DIR.mkdir(exist_ok=True)

    # Preserve any existing annotations when regenerating
    existing: dict[str, list[str] | None] = {}
    if SAMPLE_FILE.exists():
        old = json.loads(SAMPLE_FILE.read_text())
        for entry in old:
            if entry.get("correct_tags") is not None:
                existing[entry["id"]] = entry["correct_tags"]

    output = []
    for p in sample:
        combined = " ".join(filter(None, [
            p.get("restaurant_name", ""),
            p.get("source_title", ""),
            p.get("text", ""),
        ]))
        entry = {
            "id": p["id"],
            "source": p.get("source", ""),
            "text": combined[:600],  # truncate for readability
            "predicted_tags": p.get("tags", []),
            # Annotator fills this in; null = not yet labeled
            "correct_tags": existing.get(p["id"], None),
        }
        output.append(entry)

    SAMPLE_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    tagged_count = sum(1 for e in output if e["correct_tags"] is not None)
    print(f"Wrote {len(output)} posts to {SAMPLE_FILE}")
    print(f"  {tagged_count} already annotated, {len(output) - tagged_count} need labels")
    print()
    print('Open eval/sample.json and fill "correct_tags" for each entry.')
    print('  []           → post has no relevant food tags')
    print('  ["cafe"]     → only "cafe" applies')
    print('  ["hawker","chinese"] → both apply')
    print(f'\nAvailable tags: {", ".join(ALL_TAGS)}')


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_command(_args: argparse.Namespace) -> None:
    del _args
    if not SAMPLE_FILE.exists():
        sys.exit(f"Sample file not found: {SAMPLE_FILE}\nRun: python3 eval_classify.py sample")

    entries = json.loads(SAMPLE_FILE.read_text())
    labeled = [e for e in entries if e.get("correct_tags") is not None]

    if not labeled:
        sys.exit("No labeled entries found. Fill in 'correct_tags' in eval/sample.json first.")

    unlabeled = len(entries) - len(labeled)
    if unlabeled:
        print(f"Warning: {unlabeled}/{len(entries)} entries still unlabeled (excluded from metrics)\n")

    # Per-tag counts
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)

    # Post-level exact match
    exact_match = 0

    for entry in labeled:
        predicted = set(entry["predicted_tags"])
        correct = set(entry["correct_tags"])

        if predicted == correct:
            exact_match += 1

        for tag in ALL_TAGS:
            p_has = tag in predicted
            c_has = tag in correct
            if p_has and c_has:
                tp[tag] += 1
            elif p_has and not c_has:
                fp[tag] += 1
            elif not p_has and c_has:
                fn[tag] += 1

    def prf(tag: str) -> tuple[float, float, float]:
        t, f_p, f_n = tp[tag], fp[tag], fn[tag]
        precision = t / (t + f_p) if (t + f_p) else math.nan
        recall = t / (t + f_n) if (t + f_n) else math.nan
        if math.isnan(precision) or math.isnan(recall) or (precision + recall) == 0:
            f1 = math.nan
        else:
            f1 = 2 * precision * recall / (precision + recall)
        return precision, recall, f1

    print(f"=== Classifier Evaluation ({len(labeled)} labeled posts) ===\n")
    print(f"{'Tag':<12} {'Prec':>6} {'Rec':>6} {'F1':>6}  {'TP':>4} {'FP':>4} {'FN':>4}")
    print("-" * 52)

    macro_p, macro_r, macro_f1 = [], [], []
    support_tags = []

    for tag in ALL_TAGS:
        if tp[tag] + fp[tag] + fn[tag] == 0:
            continue  # tag not in sample at all
        p, r, f1 = prf(tag)
        support_tags.append(tag)
        fmt_p = f"{p:.1%}" if not math.isnan(p) else "  N/A"
        fmt_r = f"{r:.1%}" if not math.isnan(r) else "  N/A"
        fmt_f1 = f"{f1:.1%}" if not math.isnan(f1) else "  N/A"
        print(f"{tag:<12} {fmt_p:>6} {fmt_r:>6} {fmt_f1:>6}  {tp[tag]:>4} {fp[tag]:>4} {fn[tag]:>4}")
        if not math.isnan(f1):
            macro_p.append(p)
            macro_r.append(r)
            macro_f1.append(f1)

    print("-" * 52)
    if macro_f1:
        mp = sum(macro_p) / len(macro_p)
        mr = sum(macro_r) / len(macro_r)
        mf = sum(macro_f1) / len(macro_f1)
        print(f"{'macro avg':<12} {mp:.1%} {mr:.1%} {mf:.1%}")

    em_pct = exact_match / len(labeled)
    print(f"\nExact-match accuracy (all tags correct): {exact_match}/{len(labeled)} = {em_pct:.1%}")

    # Untagged precision: posts with no correct tags that classifier also left untagged
    true_neg = sum(
        1 for e in labeled
        if not e["correct_tags"] and not e["predicted_tags"]
    )
    false_pos_any = sum(
        1 for e in labeled
        if not e["correct_tags"] and e["predicted_tags"]
    )
    false_neg_any = sum(
        1 for e in labeled
        if e["correct_tags"] and not e["predicted_tags"]
    )
    print(f"\nUntagged posts (correct_tags=[]):")
    print(f"  Correctly left untagged: {true_neg}")
    print(f"  Incorrectly tagged:      {false_pos_any}")
    print(f"  Tagged posts missed entirely (predicted nothing): {false_neg_any}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sample = sub.add_parser("sample", help="Generate stratified eval sample")
    p_sample.add_argument(
        "--size", type=int, default=8,
        help="Posts to draw per-tag stratum (default: 8)",
    )

    sub.add_parser("score", help="Compute metrics from annotated sample")

    args = parser.parse_args()
    if args.command == "sample":
        sample_command(args)
    else:
        score_command(args)


if __name__ == "__main__":
    main()
