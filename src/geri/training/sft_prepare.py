"""Prepare a sourced conversation JSONL into deterministic, unapproved SFT splits."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from geri.data.pipeline import pii_findings, quality_reasons


def prepare_sft(input_path: Path, sources_path: Path, output: Path, tokenizer_path: Path,
                seed: int = 20261125, train_ratio: float = 0.9, validation_ratio: float = 0.05) -> dict:
    if train_ratio <= 0 or validation_ratio <= 0 or train_ratio + validation_ratio >= 1:
        raise ValueError("train and validation ratios must be positive and leave a nonempty test split")
    source_file_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    sources_config = json.loads(sources_path.read_text(encoding="utf-8"))
    sources = sources_config.get("sources", [])
    source_map = {source.get("source_id"): source for source in sources}
    if not source_map or None in source_map or len(source_map) != len(sources):
        raise ValueError("source registry requires unique source_id values")
    records = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise ValueError("conversation input is empty")
    seen_ids, seen_contents = set(), set()
    quality_counts = {"conversations": 0, "messages": 0, "pii_rejected": 0, "control_or_replacement": 0, "overlong_messages": 0, "urls_present": 0}
    eligible = []
    for index, row in enumerate(records, 1):
        conversation_id = row.get("conversation_id")
        messages = row.get("messages")
        if not isinstance(conversation_id, str) or not conversation_id.strip() or conversation_id in seen_ids:
            raise ValueError(f"missing or duplicate conversation_id at row {index}")
        if not isinstance(messages, list) or len(messages) < 2 or len(messages) % 2:
            raise ValueError(f"invalid message count at row {index}")
        if [m.get("role") for m in messages] != [role for _ in range(len(messages)//2) for role in ("user", "assistant")]:
            raise ValueError(f"messages must alternate user/assistant at row {index}")
        if any(not isinstance(m.get("content"), str) or not m["content"].strip() for m in messages):
            raise ValueError(f"empty message at row {index}")
        for message in messages:
            content = message["content"].strip()
            findings = pii_findings(content)
            if findings:
                quality_counts["pii_rejected"] += len(findings)
                raise ValueError(f"pattern-detected PII {findings} at row {index}; redact and review the source before preparation")
            reasons = quality_reasons(content, 1, 8000)
            if "control_or_replacement_character" in reasons:
                quality_counts["control_or_replacement"] += 1
                raise ValueError(f"control/replacement character at row {index}")
            if "too_long" in reasons:
                quality_counts["overlong_messages"] += 1
                raise ValueError(f"message exceeds 8,000 characters at row {index}")
            if "url_or_boilerplate" in reasons:
                quality_counts["urls_present"] += 1
            quality_counts["messages"] += 1
        quality_counts["conversations"] += 1
        source_id = row.get("source_id")
        source = source_map.get(source_id)
        if not source or any(not isinstance(source.get(field), str) or not source[field].strip()
                             for field in ("source_url", "license", "attribution")):
            raise ValueError(f"unregistered or incomplete source at row {index}")
        digest = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if digest in seen_contents:
            raise ValueError(f"duplicate conversation content at row {index}")
        seen_ids.add(conversation_id)
        seen_contents.add(digest)
        eligible.append({"conversation_id": conversation_id, "source_id": source_id,
                         "source_url": source["source_url"], "license": source["license"],
                         "attribution": source["attribution"], "messages": messages})
    if len(eligible) < 3:
        raise ValueError("at least three unique conversations are required for train/validation/test")
    ordered = sorted(eligible, key=lambda row: hashlib.sha256(f"{seed}:{row['conversation_id']}".encode()).hexdigest())
    train_end = max(1, int(len(ordered) * train_ratio))
    validation_count = max(1, int(len(ordered) * validation_ratio))
    if train_end + validation_count >= len(ordered):
        train_end, validation_count = len(ordered) - 2, 1
    split_rows = {"train": ordered[:train_end], "validation": ordered[train_end:train_end + validation_count], "test": ordered[train_end + validation_count:]}
    processed = output / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    split_ids = {}
    for split, rows in split_rows.items():
        for row in rows:
            row["split"] = split
        path = processed / f"{split}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        artifacts[path.name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": len(rows)}
        split_ids[split] = sorted(row["conversation_id"] for row in rows)
    tokenizer_hash = hashlib.sha256(tokenizer_path.read_bytes()).hexdigest()
    manifest_sources = []
    for source_id, source in sorted(source_map.items()):
        manifest_sources.append({**source, "source_id": source_id, "review_status": "pending_human_review"})
    manifest = {"schema_version": 1, "dataset_status": "prepared_candidate; human source review pending; not approved for training",
        "training_authorization": None, "human_review": {"decision": "pending", "reviewer": None, "approved_at_utc": None},
        "prepared_from_sha256": source_file_hash, "source_registry_sha256": hashlib.sha256(sources_path.read_bytes()).hexdigest(), "tokenizer_sha256": tokenizer_hash,
        "seed": seed, "split_unit": "conversation_id", "split_ratios": {"train": train_ratio, "validation": validation_ratio, "test": 1 - train_ratio - validation_ratio},
        "split_conversation_ids": split_ids, "sources": manifest_sources, "artifacts": artifacts,
        "quality_screen": {**quality_counts, "pii_policy": "pattern matches rejected; screen does not detect names/contextual PII", "factuality": "not automated; human review required"},
        "quality_review_required": ["language and factuality sampling", "safety and PII review", "source rights and license compatibility", "human response-quality review"]}
    (processed / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
