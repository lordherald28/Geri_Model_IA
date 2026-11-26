"""Small, auditable, deterministic Spanish text corpus pipeline."""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

URL_RE = re.compile(r"https?://|www\.", re.I)
SPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÜÑ¿¡])")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(text: str) -> str:
    text = html.unescape(text).replace("\ufeff", "").replace("\u00ad", "")
    text = unicodedata.normalize("NFC", text)
    return SPACE_RE.sub(" ", text).strip()


def quality_reasons(text: str, minimum: int, maximum: int) -> list[str]:
    reasons = []
    if len(text) < minimum:
        reasons.append("too_short")
    if len(text) > maximum:
        reasons.append("too_long")
    if URL_RE.search(text):
        reasons.append("url_or_boilerplate")
    if "\ufffd" in text or any(unicodedata.category(c) == "Cc" and c not in "\t\n\r" for c in text):
        reasons.append("control_or_replacement_character")
    letters = sum(c.isalpha() for c in text)
    if not text or letters / max(1, len(text)) < 0.35:
        reasons.append("low_letter_ratio")
    return reasons


def _tei_text(path: Path) -> str:
    root = ET.parse(path).getroot()
    chunks = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] in {"p", "head", "l"}:
            value = normalize(" ".join(element.itertext()))
            if value:
                chunks.append(value)
    return "\n".join(chunks)


def _sentences(text: str) -> list[str]:
    paragraphs = [normalize(p) for p in text.splitlines() if normalize(p)]
    return [normalize(s) for p in paragraphs for s in SENTENCE_SPLIT.split(p) if normalize(s)]


def _split(document: str, seed: int, ratios: tuple[float, float, float]) -> str:
    value = int(hashlib.sha256(f"{seed}:{document}".encode()).hexdigest()[:16], 16) / 16**16
    if value < ratios[0]:
        return "train"
    if value < ratios[0] + ratios[1]:
        return "validation"
    return "test"


def _download(url: str, target: Path, max_bytes: int, timeout: int = 60) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Geri2DataPipeline/0.1 (reproducible corpus preparation)"})
    total = 0
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, temporary.open("wb") as output:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > max_bytes:
                raise ValueError(f"download exceeds configured limit ({declared} > {max_bytes})")
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > max_bytes:
                    raise ValueError(f"download exceeds configured limit ({total} > {max_bytes})")
                output.write(block)
        temporary.replace(target)
        return total
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _load_source_records(source: dict, raw_dir: Path, max_download: int, remaining_budget: int) -> tuple[list[dict], dict]:
    archive = raw_dir / source["filename"]
    downloaded = 0
    if not archive.exists() and source["type"] != "eltec_files":
        if source.get("url") is None and source.get("type") != "eltec_files":
            raise FileNotFoundError(f"local source missing: {archive}")
        cap = min(max_download, remaining_budget)
        if cap <= 0:
            raise ValueError("total download budget exhausted")
        downloaded = _download(source["url"], archive, cap)
    digest = sha256(archive) if archive.exists() else None
    rows: list[dict] = []
    if source["type"] == "eltec_files":
        from urllib.parse import quote
        files = []
        total_downloaded = downloaded
        for relative in source["documents"]:
            document_path = Path(relative)
            if document_path.is_absolute() or ".." in document_path.parts:
                raise ValueError(f"unsafe source document path: {relative}")
            target = raw_dir / source["id"] / document_path
            if not target.exists():
                per_file_budget = min(max_download, remaining_budget - total_downloaded)
                if per_file_budget <= 0:
                    raise ValueError("total download budget exhausted")
                url = source["url_template"].format(path=quote(relative, safe="/"))
                total_downloaded += _download(url, target, per_file_budget)
            files.append((relative, target))
        for relative, path in files:
            rows.extend(_records_for_document(_tei_text(path), relative, source))
        snapshot = {"snapshot_sha256": hashlib.sha256("\n".join(f"{name}:{sha256(path)}" for name, path in files).encode()).hexdigest(), "snapshot_bytes": sum(path.stat().st_size for _, path in files), "downloaded_bytes": total_downloaded, "snapshot": source["filename"], "document_hashes": {name: sha256(path) for name, path in files}}
        return rows, snapshot
    elif source["type"] == "eltec_zip":
        import zipfile
        with zipfile.ZipFile(archive) as bundle:
            xml_files = sorted(n for n in bundle.namelist() if re.fullmatch(r"level1/SPA\d+_[^/]+\.xml", n))
            if not xml_files:
                raise ValueError("pinned ELTeC release contains no level1 Spanish novels")
            for name in xml_files:
                raw = bundle.read(name)
                text = _tei_text_from_bytes(raw)
                rows.extend(_records_for_document(text, name, source))
    elif source["type"] == "tatoeba_cc0_tsv":
        import csv
        with archive.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.reader(stream, delimiter="\t"):
                if len(row) < 3 or row[1] != "spa":
                    continue
                text = normalize(row[2])
                if text:
                    rows.append({"text": text, "document_id": f"tatoeba:{row[0]}", "source_id": row[0], "source": source["id"], "url": source["url"], "license": "CC0-1.0", "attribution": row[0]})
    else:
        raise ValueError(f"unsupported source type: {source['type']}")
    return rows, {"snapshot_sha256": digest, "snapshot_bytes": archive.stat().st_size, "downloaded_bytes": downloaded, "snapshot": source["filename"]}


def _tei_text_from_bytes(raw: bytes) -> str:
    root = ET.fromstring(raw)
    chunks = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] in {"p", "head", "l"}:
            value = normalize(" ".join(element.itertext()))
            if value:
                chunks.append(value)
    return "\n".join(chunks)


def _records_for_document(text: str, document: str, source: dict) -> list[dict]:
    return [{"text": sentence, "document_id": f"{source['id']}:{document}", "source_id": document, "source": source["id"], "url": source.get("source_page") or source.get("url_template", source.get("url", "")), "license": source["license"], "attribution": source["attribution"]} for sentence in _sentences(text)]


def prepare(config_path: Path, output_dir: Path, source_ids: set[str] | None = None, offline: bool = False) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    registry_path = config_path.with_name("sources.json")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    selected = [s for s in registry["sources"] if source_ids is None or s["id"] in source_ids]
    if not selected:
        raise ValueError("no sources selected")
    raw_dir = output_dir / "raw"
    processed_dir = output_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    budget = int(config["max_total_download_bytes"])
    snapshots, all_rows = {}, []
    for source in selected:
        if offline:
            if source["type"] == "eltec_files":
                missing = [name for name in source["documents"] if not (raw_dir / source["id"] / name).exists()]
                if missing:
                    raise FileNotFoundError(f"offline mode: missing {len(missing)} pinned source files; first: {missing[0]}")
            elif not (raw_dir / source["filename"]).exists():
                raise FileNotFoundError(f"offline mode: missing snapshot {source['filename']}")
        records, snapshot = _load_source_records(source, raw_dir, int(config["max_download_bytes"]), budget)
        budget -= snapshot["downloaded_bytes"]
        snapshots[source["id"]] = snapshot
        all_rows.extend(records)

    minimum, maximum = int(config["min_characters"]), int(config["max_characters"])
    seen, accepted, rejected, duplicates = set(), [], Counter(), 0
    ratios = (float(config["train_ratio"]), float(config["validation_ratio"]), float(config["test_ratio"]))
    if abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError("split ratios must sum to 1")
    for row in all_rows:
        text = normalize(row["text"])
        reasons = quality_reasons(text, minimum, maximum)
        if reasons:
            rejected.update(reasons)
            continue
        fingerprint = hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()
        if fingerprint in seen:
            duplicates += 1
            continue
        seen.add(fingerprint)
        row["text"] = text
        row["document_hash"] = hashlib.sha256(row["document_id"].encode()).hexdigest()
        row["split"] = _split(row["document_id"], int(config["seed"]), ratios)
        row["text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        accepted.append(row)

    # Stratify at document granularity and guarantee all partitions when >=3 documents exist.
    documents = sorted({r["document_id"] for r in accepted}, key=lambda d: hashlib.sha256(f"{config['seed']}:{d}".encode()).hexdigest())
    if len(documents) < 3:
        raise ValueError("at least three eligible source documents are required for train/validation/test")
    train_end = max(1, int(len(documents) * ratios[0]))
    validation_count = max(1, int(len(documents) * ratios[1]))
    if train_end + validation_count >= len(documents):
        train_end = len(documents) - 2
        validation_count = 1
    split_by_document = {doc: "train" if index < train_end else "validation" if index < train_end + validation_count else "test" for index, doc in enumerate(documents)}
    for row in accepted:
        row["split"] = split_by_document[row["document_id"]]
    split_counts = Counter(r["split"] for r in accepted)
    if any(split_counts.get(name, 0) == 0 for name in ("train", "validation", "test")):
        raise ValueError(f"document split left an empty partition: {dict(split_counts)}; add documents or adjust ratios")
    for split in ("train", "validation", "test"):
        path = processed_dir / f"{split}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for row in accepted:
                if row["split"] == split:
                    stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    docs_by_split = {name: sorted({r["document_hash"] for r in accepted if r["split"] == name}) for name in ("train", "validation", "test")}
    manifest = {
        "schema_version": 1, "pipeline_version": "0.1.0", "seed": int(config["seed"]),
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "normalization": "HTML entity decode, remove BOM/soft hyphen, Unicode NFC, collapse whitespace",
        "split_unit": "source document (Tatoeba sentence is its own document)",
        "split_ratios": {"train": ratios[0], "validation": ratios[1], "test": ratios[2]},
        "sources": [{**s, **snapshots[s["id"]]} for s in selected],
        "counts": {"input": len(all_rows), "accepted": len(accepted), "duplicates": duplicates, "rejected_by_reason": dict(rejected), "splits": dict(split_counts)},
        "documents_by_split_sha256": {name: hashlib.sha256("\n".join(ids).encode()).hexdigest() for name, ids in docs_by_split.items()},
        "quality_checks": {"min_characters": minimum, "max_characters": maximum, "url_filter": True, "unicode_controls": True, "letter_ratio_minimum": 0.35, "pii": "not automatically screened; human review required", "factuality": "not assessed"},
        "artifacts": {},
    }
    for split in ("train", "validation", "test"):
        path = processed_dir / f"{split}.jsonl"
        manifest["artifacts"][path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    (processed_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def validate(output_dir: Path) -> dict:
    processed = output_dir / "processed"
    manifest = json.loads((processed / "manifest.json").read_text(encoding="utf-8"))
    docs, texts, counts = {}, {}, Counter()
    for split in ("train", "validation", "test"):
        path = processed / f"{split}.jsonl"
        if sha256(path) != manifest["artifacts"][path.name]["sha256"]:
            raise ValueError(f"hash mismatch: {path.name}")
        with path.open(encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                row = json.loads(line)
                if row["split"] != split or not row.get("text") or not row.get("license") or not row.get("url"):
                    raise ValueError(f"invalid row {path.name}:{line_no}")
                if row["document_hash"] in docs and docs[row["document_hash"]] != split:
                    raise ValueError("document leakage across splits")
                docs[row["document_hash"]] = split
                fingerprint = hashlib.sha256(row["text"].casefold().encode()).hexdigest()
                if fingerprint in texts:
                    raise ValueError(f"duplicate text across splits: {texts[fingerprint]} and {split}")
                texts[fingerprint] = split
                counts[split] += 1
    if set(counts) != {"train", "validation", "test"}:
        raise ValueError("one or more splits are empty")
    return {"valid": True, "rows": dict(counts), "documents": len(docs), "unique_texts": len(texts), "files_verified": 3}


def dimension_tokenizer(output_dir: Path, vocab_candidates: Iterable[int] | None = None) -> dict:
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers, decoders, normalizers

    processed = output_dir / "processed"
    records = [json.loads(line) for line in (processed / "train.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if not records:
        raise ValueError("train split is empty")
    docs: dict[str, list[str]] = {}
    for row in records:
        docs.setdefault(row["document_hash"], []).append(row["text"])
    train_texts = ["\n".join(texts) for texts in docs.values()]
    config_path = Path(__file__).resolve().parents[3] / "configs" / "data-pipeline.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    limit = int(config["max_tokenizer_train_documents"])
    if len(train_texts) > limit:
        train_texts = train_texts[:limit]
    candidates = list(vocab_candidates or config["vocab_candidates"])
    validation_records = [json.loads(line) for line in (processed / "validation.jsonl").read_text(encoding="utf-8").splitlines() if line]
    validation = [r["text"] for r in validation_records]
    validation_documents = len({r["document_hash"] for r in validation_records})
    reports = []
    artifacts = output_dir / "tokenizer"
    artifacts.mkdir(parents=True, exist_ok=True)
    for vocab in candidates:
        tokenizer = Tokenizer(models.BPE(unk_token="<unk>"))
        tokenizer.normalizer = normalizers.NFC()
        tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
        tokenizer.decoder = decoders.ByteLevel()
        trainer = trainers.BpeTrainer(vocab_size=int(vocab), min_frequency=2, special_tokens=["<unk>", "<pad>", "<bos>", "<eos>"], show_progress=False)
        tokenizer.train_from_iterator(train_texts, trainer=trainer)
        train_chars = sum(map(len, train_texts))
        val_chars = sum(map(len, validation))
        train_tokens = sum(len(tokenizer.encode(t).ids) for t in train_texts)
        val_tokens = sum(len(tokenizer.encode(t).ids) for t in validation)
        model_path = artifacts / f"bpe-vocab-{vocab}.json"
        tokenizer.save(str(model_path))
        reports.append({"requested_vocab": vocab, "actual_vocab": tokenizer.get_vocab_size(), "train_documents": len(train_texts), "train_characters": train_chars, "train_tokens": train_tokens, "train_tokens_per_character": train_tokens / max(1, train_chars), "validation_documents": validation_documents, "validation_records": len(validation), "validation_characters": val_chars, "validation_tokens": val_tokens, "validation_tokens_per_character": val_tokens / max(1, val_chars), "compression_ratio_characters_per_token_train": train_chars / max(1, train_tokens), "model_file": model_path.name, "model_sha256": sha256(model_path)})
    selected = min(reports, key=lambda x: x["validation_tokens_per_character"])
    final_path = artifacts / "tokenizer.json"
    (artifacts / selected["model_file"]).replace(final_path)
    report = {"algorithm": "byte-level BPE", "library": "tokenizers", "normalization": "NFC", "training_data": "train documents only", "selection_metric": "lowest validation tokens per character", "candidate_measurements": reports, "selected_vocab": selected["requested_vocab"], "selected_actual_vocab": selected["actual_vocab"], "tokenizer_file": final_path.name, "tokenizer_sha256": sha256(final_path), "test_split_used_for_selection": False}
    (artifacts / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def verify_offline(output_dir: Path) -> dict:
    """Verify frozen files with networking APIs blocked; requires no network."""
    from unittest.mock import patch
    def blocked(*_args, **_kwargs):
        raise AssertionError("network access attempted in offline verification")
    with patch("urllib.request.urlopen", blocked), patch("socket.create_connection", blocked):
        report = validate(output_dir)
        tokenizer_path = output_dir / "tokenizer" / "tokenizer.json"
        metrics_path = output_dir / "tokenizer" / "metrics.json"
        if not tokenizer_path.exists() or not metrics_path.exists():
            raise FileNotFoundError("frozen tokenizer artifacts missing")
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        sample = json.loads((output_dir / "processed" / "test.jsonl").read_text(encoding="utf-8").splitlines()[0])["text"]
        ids = tokenizer.encode(sample).ids
        decoded = tokenizer.decode(ids)
        if not decoded:
            raise ValueError("offline tokenizer produced empty decoding")
        return {**report, "offline_network_blocked": True, "test_sample_tokens": len(ids), "test_sample_roundtrip_nonempty": True, "tokenizer_sha256": sha256(tokenizer_path)}
