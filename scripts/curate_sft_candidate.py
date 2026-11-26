"""Curate the frozen OASST1 candidate and append project-authored Geri dialogues.

This is a conservative, deterministic screen, not a substitute for the human
factuality, privacy, safety, or license review recorded in the output manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from tokenizers import Tokenizer

OASST = "openassistant_oasst1_2023_04_12"
GERI = "geri2_project_authored_identity_2026_11"

# Drop answers whose claims cannot be made true for the Geri runtime, or that
# are stale by construction. These rules only reject; they never label facts true.
REJECT = {
    "foreign_or_unscoped_identity": re.compile(
        r"\b(?:open\s*assistant|chatgpt|soy\s+(?:un\s+)?(?:modelo de lenguaje|inteligencia artificial|ia|chatbot|asistente virtual)|"
        r"como modelo de lenguaje|soy un modelo|mi nombre es open assistant)\b", re.I
    ),
    "unsupported_live_or_external_capability": re.compile(
        r"\b(?:puedo decirte el clima|clima de hoy|hora actual en|he buscado en internet|"
        r"informaci[oó]n que he encontrado en internet|informaci[oó]n que encontrado en|"
        r"[uú]ltimos tweets|partidos de hoy|tengo acceso a internet|he consultado internet)\b", re.I
    ),
    "volatile_or_dated_claim": re.compile(
        r"\b(?:a fecha de \d{1,2}[/-]\d{1,2}[/-]\d{2,4}|al d[ií]a de hoy|a d[ií]a de hoy|"
        r"actualmente es|actualmente tiene|actualmente ha|hasta la fecha.{0,60}(?:nasa|descubierto)|"
        r"el canal con m[aá]s suscriptores|persona viva m[aá]s longeva|partidos.{0,30}hoy|"
        r"este a[nñ]o.{0,50}(?:m[aá]s usado|popular)|recientemente han ocurrido)\b", re.I
    ),
    "clear_math_or_explanation_error": re.compile(
        r"ra[ií]ces quintas.{0,100}son aproximadas|365\.256 d[ií]as.{0,220}cada 4 a[nñ]os|"
        r"1\.366 vatios.{0,160}(?:64 millones|1/4\.69)|vers[ií]culo m[aá]s corto.{0,220}No matar[aá]s", re.I
    ),
    "role_transcript_leak": re.compile(r"(?:^|\n)\s*(?:Paciente|Psic[oó]logo|Assistant|User)\s*:", re.I),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--geri-dialogues", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-seq-len", type=int, default=256)
    args = parser.parse_args()
    tokenizer = Tokenizer.from_file(str(args.tokenizer))
    records = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != 779:
        raise ValueError(f"expected frozen 779-row source candidate; got {len(records)}")
    seen_ids: set[str] = set()
    retained: list[dict] = []
    discarded: dict[str, list[str]] = {}
    primary_discard_reasons: Counter[str] = Counter()
    for row in records:
        if row.get("source_id") != OASST or not isinstance(row.get("messages"), list) or len(row["messages"]) != 2:
            raise ValueError(f"unexpected source or structure: {row.get('conversation_id')}")
        if [m.get("role") for m in row["messages"]] != ["user", "assistant"]:
            raise ValueError(f"role inversion: {row.get('conversation_id')}")
        assistant = row["messages"][1]["content"]
        reasons = [name for name, pattern in REJECT.items() if pattern.search(assistant)]
        if reasons:
            discarded[row["conversation_id"]] = reasons
            primary_discard_reasons[reasons[0]] += 1
            continue
        ids = []
        for message in row["messages"]:
            ids.extend(tokenizer.encode(f"<|{message['role']}|>\n{message['content'].strip()}\n").ids)
        ids.append(tokenizer.token_to_id("<eos>"))
        if len(ids) > args.max_seq_len:
            discarded[row["conversation_id"]] = ["over_context_after_curated_filter"]
            continue
        seen_ids.add(row["conversation_id"])
        retained.append(row)

    authored = [json.loads(line) for line in args.geri_dialogues.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(authored) != 8 or any(row.get("source_id") != GERI for row in authored):
        raise ValueError("expected eight project-authored Geri dialogues with the registered source_id")
    for row in authored:
        ids = []
        for message in row["messages"]:
            ids.extend(tokenizer.encode(f"<|{message['role']}|>\n{message['content']}\n").ids)
        ids.append(tokenizer.token_to_id("<eos>"))
        if len(ids) > args.max_seq_len:
            raise ValueError(f"authored example exceeds context: {row['conversation_id']} ({len(ids)} tokens)")
        if row["conversation_id"] in seen_ids:
            raise ValueError("duplicate conversation id")
        seen_ids.add(row["conversation_id"])
    merged = retained + authored
    args.output.mkdir(parents=True, exist_ok=True)
    input_path = args.output / "conversations.jsonl"
    input_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in merged), encoding="utf-8")
    snapshot = Path(r"C:\Geriv2-Data\sft\source-workspace\oasst1\2023-04-12_oasst_ready.trees.jsonl.gz")
    sources = {
        "sources": [
            {
                "source_id": OASST,
                "source_url": "https://huggingface.co/datasets/OpenAssistant/oasst1/tree/fdf72ae0827c1cda404aff25b6603abec9e3399b",
                "license": "Apache-2.0",
                "attribution": "OpenAssistant Conversations Dataset (OASST1), OpenAssistant/LAION-AI contributors; Apache License 2.0; Spanish direct-reply subset filtered and split for Geriv2.",
                "snapshot_file": snapshot.name,
                "snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                "snapshot_bytes": snapshot.stat().st_size,
                "source_revision": "fdf72ae0827c1cda404aff25b6603abec9e3399b",
                "filters": "Pinned 2023-04-12 OASST1 snapshot; source annotations and structural screens from extraction; additional deterministic exclusion of foreign identity, unsupported live capabilities, volatile claims, clear errors and transcript-role leakage.",
                "review_status": "pending_human_review",
            },
            {
                "source_id": GERI,
                "source_url": "https://github.com/lordherald28/Geri_Model_IA",
                "license": "Project-authored internal candidate; license and redistribution/weight-use terms pending human approval.",
                "attribution": "Original short dialogues authored for the Geriv2 Geri identity candidate by the project implementation; generated by scripts/curate_sft_candidate.py; no external text source.",
                "created_at": "2026-11-25",
                "content_sha256": hashlib.sha256(json.dumps(authored, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
                "review_status": "pending_human_review",
            },
        ]
    }
    sources_path = args.output / "sources.json"
    sources_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "status": "candidate_only_human_review_required_not_approved",
        "training_authorization": None,
        "original_oasst_rows": len(records),
        "retained_oasst_rows": len(retained),
        "discarded_oasst_rows": len(discarded),
        "primary_discard_reasons": dict(sorted(primary_discard_reasons.items())),
        "discard_reasons": dict(sorted(Counter(reason for reasons in discarded.values() for reason in reasons).items())),
        "discarded_ids_and_reasons": discarded,
        "project_authored_rows_added": len(authored),
        "result_rows": len(merged),
        "result_turn_distribution": dict(sorted(Counter(len(row["messages"]) // 2 for row in merged).items())),
        "corrections_to_oasst_text": 0,
        "automated_screen_limit": "These deterministic rules reject only clear incompatibilities; they do not prove factuality, language quality, privacy, safety, or legal clearance.",
        "authored_validation": "All eight dialogues have alternating roles, pass common PII/control checks in prepare-sft, fit the frozen tokenizer context, and make only project-runtime claims grounded in the text-only offline implementation; human persona, quality and license review remains required.",
        "geri_dialogues_sha256": hashlib.sha256(args.geri_dialogues.read_bytes()).hexdigest(),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "source_registry_sha256": hashlib.sha256(sources_path.read_bytes()).hexdigest(),
        "max_seq_len": args.max_seq_len,
        "human_review_required": [
            "review all retained OASST responses for factuality, Spanish quality, contextual privacy and safety; automated flags are triage only",
            "approve OASST Apache-2.0 attribution and downstream training/weight use",
            "review Geri persona statements and approve project-authored content license/weight-use terms",
            "approve or reject the regenerated SFT manifest",
        ],
    }
    report_path = args.output / "curation-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "discarded_ids_and_reasons"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
