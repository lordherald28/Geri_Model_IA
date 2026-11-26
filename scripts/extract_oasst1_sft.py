"""Extract a conservative, Spanish-only OASST1 candidate for the local SFT gate.

This is preparation only. The output manifest is deliberately unapproved and
must pass human source/content review before the training loader will accept it.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from geri.data.pipeline import pii_findings, quality_reasons
from tokenizers import Tokenizer


SOURCE_ID = "openassistant_oasst1_2023_04_12"
SOURCE_URL = "https://huggingface.co/datasets/OpenAssistant/oasst1"
SOURCE_REVISION = "fdf72ae0827c1cda404aff25b6603abec9e3399b"
SNAPSHOT_URL = f"https://huggingface.co/datasets/OpenAssistant/oasst1/resolve/{SOURCE_REVISION}/2023-04-12_oasst_ready.trees.jsonl.gz"
LICENSE = "Apache-2.0"
ATTRIBUTION = "OpenAssistant Conversations Dataset (OASST1), OpenAssistant/LAION-AI contributors, Apache License 2.0; adapted to Spanish one-turn pairs, filtered and split for Geriv2."
SAFETY_LABELS = ("spam", "lang_mismatch", "pii", "not_appropriate", "hate_speech", "sexual_content")
DETOXIFY_LABELS = ("toxicity", "severe_toxicity", "obscene", "identity_attack", "insult", "threat", "sexual_explicit")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_node(message: dict, assistant: bool) -> str | None:
    if message.get("role") != ("assistant" if assistant else "prompter"):
        return "role"
    if message.get("lang") != "es":
        return "language"
    if message.get("review_result") is not True or message.get("deleted") is not False:
        return "moderation_review"
    if message.get("synthetic") is not False:
        return "synthetic_or_unknown"
    if int(message.get("review_count", 0)) < 3:
        return "insufficient_review_count"
    labels = message.get("labels") or {}
    for label in SAFETY_LABELS:
        record = labels.get(label, {})
        if int(record.get("count", 0)) < 3 or float(record.get("value", 1)) != 0:
            return f"label_{label}"
    if assistant:
        failed = labels.get("fails_task", {})
        helpful = labels.get("helpfulness", {})
        quality = labels.get("quality", {})
        if int(failed.get("count", 0)) < 3 or float(failed.get("value", 1)) != 0:
            return "label_fails_task"
        if int(helpful.get("count", 0)) < 3 or float(helpful.get("value", 0)) < 0.5:
            return "label_helpfulness"
        if int(quality.get("count", 0)) < 3 or float(quality.get("value", 0)) < 0.5:
            return "label_quality"
    for label in DETOXIFY_LABELS:
        value = (message.get("detoxify") or {}).get(label)
        if value is not None and float(value) >= 0.5:
            return f"detoxify_{label}"
    text = message.get("text")
    if not isinstance(text, str) or len(text.strip()) < (20 if assistant else 8):
        return "empty_or_short"
    text = text.strip()
    if "\ufffd" in text:
        return "replacement_character"
    reasons = quality_reasons(text, 1, 8000)
    if reasons:
        return "text_quality_" + "+".join(sorted(reasons))
    if pii_findings(text):
        return "pattern_pii"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--tokenizer", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="directory for conversations.jsonl and extraction report")
    parser.add_argument("--max-seq-len", default=256, type=int)
    args = parser.parse_args()
    if not args.snapshot.is_file() or not args.tokenizer.is_file():
        raise SystemExit("snapshot and frozen tokenizer must exist locally")
    tokenizer = Tokenizer.from_file(str(args.tokenizer))
    eos = tokenizer.token_to_id("<eos>")
    if eos is None:
        raise SystemExit("tokenizer has no <eos> token")
    source_hash = sha256_file(args.snapshot)
    counts: Counter[str] = Counter()
    candidates: list[dict] = []
    seen_content: set[str] = set()
    tree_count = 0
    with gzip.open(args.snapshot, "rt", encoding="utf-8", errors="strict") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            tree_count += 1
            tree = json.loads(line)
            root = tree.get("prompt") or {}
            reason = check_node(root, assistant=False)
            if reason:
                counts["prompt:" + reason] += 1
                continue
            replies = root.get("replies") or []
            valid_replies = []
            for reply in replies:
                why = check_node(reply, assistant=True)
                if why:
                    counts["reply:" + why] += 1
                    continue
                valid_replies.append(reply)
            if not valid_replies:
                counts["tree:no_eligible_reply"] += 1
                continue
            # OASST rank 0 is the top-ranked branch. Stable message_id tie-break.
            reply = min(valid_replies, key=lambda item: (int(item.get("rank", 10**9)), item.get("message_id", "")))
            messages = [
                {"role": "user", "content": root["text"].strip()},
                {"role": "assistant", "content": reply["text"].strip()},
            ]
            token_count = sum(len(tokenizer.encode(f"<|{item['role']}|>\n{item['content']}\n").ids) for item in messages) + 1
            if token_count > args.max_seq_len:
                counts["tree:over_context"] += 1
                continue
            content_key = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            if content_key in seen_content:
                counts["tree:duplicate_content"] += 1
                continue
            seen_content.add(content_key)
            candidates.append({"conversation_id": "oasst1-" + tree["message_tree_id"], "source_id": SOURCE_ID, "messages": messages})
            counts["accepted"] += 1
    if len(candidates) < 3:
        raise SystemExit(f"only {len(candidates)} eligible examples; cannot create train/validation/test")
    args.output.mkdir(parents=True, exist_ok=True)
    conversations = args.output / "conversations.jsonl"
    conversations.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in candidates), encoding="utf-8")
    registry = args.output / "sources.json"
    registry.write_text(json.dumps({"sources": [{
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "license": LICENSE,
        "attribution": ATTRIBUTION,
        "snapshot_file": args.snapshot.name,
        "snapshot_sha256": source_hash,
        "snapshot_bytes": args.snapshot.stat().st_size,
        "snapshot_release_date": "2023-04-12",
        "source_revision": SOURCE_REVISION,
        "snapshot_url": SNAPSHOT_URL,
        "filters": "Spanish only; non-synthetic; positive source review; >=3 reviews; zero annotated safety/PII flags; assistant quality/helpfulness >=0.5; pattern PII and structural screen; top-ranked direct reply; max context length",
        "review_status": "pending_human_review"
    }]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "dataset_status": "candidate_only_human_review_required_not_approved",
        "training_authorization": None,
        "source_id": SOURCE_ID,
        "source_revision": SOURCE_REVISION,
        "snapshot_url": SNAPSHOT_URL,
        "snapshot_sha256": source_hash,
        "snapshot_bytes": args.snapshot.stat().st_size,
        "snapshot_trees": tree_count,
        "accepted_conversations": len(candidates),
        "tokenizer_sha256": sha256_file(args.tokenizer),
        "max_seq_len": args.max_seq_len,
        "selection": "one direct top-ranked assistant reply per tree; no author/user IDs retained; no continuation branches",
        "factuality": "not machine-verifiable; human review required",
        "privacy": "source PII annotations plus common-pattern scan passed on retained messages; names/contextual PII require human review",
        "exclusions": dict(sorted(counts.items())),
        "human_review_required": ["license/attribution and downstream model-weight use", "Spanish quality and factuality sample", "contextual/name/rare-identifier privacy sample", "safety and representativeness review", "approve or reject corpus manifest"]
    }
    (args.output / "extraction-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
