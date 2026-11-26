"""Small, auditable, deterministic Spanish text corpus pipeline."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

URL_RE = re.compile(r"https?://|www\.", re.I)
SPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÜÑ¿¡])")
PII_PATTERNS = {
    "email": re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    "dni_nie": re.compile(r"\b(?:\d{8}[A-Z]|[XYZ]\d{7}[A-Z])\b", re.I),
    "phone": re.compile(r"(?<!\w)(?:\+34\s?)?[6789]\d{2}(?:[ .-]?\d{3}){2}(?!\w)"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_capacity(output_dir: Path, config: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(output_dir)
    required = int(config["min_free_disk_bytes"]) + int(config["max_pipeline_storage_bytes"])
    if usage.free < required:
        raise OSError(
            f"insufficient free space on {output_dir.drive or output_dir.anchor}: "
            f"{usage.free} bytes available; need at least {required} "
            "(configured data cap plus reserved free-space margin). "
            "Choose an output path on a drive with more free space."
        )
    minimum_memory = int(config.get("min_available_memory_bytes", 0))
    if minimum_memory:
        available = _available_memory_bytes()
        if available is not None and available < minimum_memory:
            raise OSError(f"insufficient available RAM: {available} bytes; need at least {minimum_memory}")


def _available_memory_bytes() -> int | None:
    if os.name == "nt":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
        return None
    try:
        return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        return None


def _check_output_size(output_dir: Path, config: dict) -> int:
    total = sum(path.stat().st_size for path in output_dir.rglob("*") if path.is_file())
    limit = int(config["max_pipeline_storage_bytes"])
    if total > limit:
        raise OSError(f"pipeline output is {total} bytes; configured cap is {limit}")
    return total


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


def pii_findings(text: str) -> list[str]:
    return [name for name, pattern in PII_PATTERNS.items() if pattern.search(text)]


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


def _download(url: str, target: Path, max_bytes: int, timeout: int = 60, accept: str | None = None) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Geri2DataPipeline/0.1 (reproducible corpus preparation)"}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
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
    document_source = source["type"] in {"eltec_files", "boe_xml_documents", "cordis_html_documents"}
    if not archive.exists() and not document_source:
        if source.get("url") is None:
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
            url = source["url_template"].format(path=quote(relative, safe="/"))
            if not target.exists():
                per_file_budget = min(max_download, remaining_budget - total_downloaded)
                if per_file_budget <= 0:
                    raise ValueError("total download budget exhausted")
                total_downloaded += _download(url, target, per_file_budget)
            files.append((relative, target, url))
        for relative, path, url in files:
            document_source = {**source, "document_metadata": {relative: {"url": url}}}
            rows.extend(_records_for_document(_tei_text(path), relative, document_source))
        snapshot = {"snapshot_sha256": hashlib.sha256("\n".join(f"{name}:{sha256(path)}" for name, path, _ in files).encode()).hexdigest(), "snapshot_bytes": sum(path.stat().st_size for _, path, _ in files), "downloaded_bytes": total_downloaded, "snapshot": source["filename"], "document_hashes": {name: sha256(path) for name, path, _ in files}}
        return rows, snapshot
    elif source["type"] in {"boe_xml_documents", "cordis_html_documents"}:
        entries = []
        total_downloaded = downloaded
        extension = ".xml" if source["type"] == "boe_xml_documents" else ".html"
        for item in source["documents"]:
            doc_id, url = item["id"], item["url"]
            expected_host = "www.boe.es/" if source["type"] == "boe_xml_documents" else "cordis.europa.eu/"
            if not url.startswith("https://" + expected_host):
                raise ValueError(f"unexpected source URL for {source['id']}: {url}")
            target = raw_dir / source["id"] / f"{doc_id}{extension}"
            if not target.exists():
                per_file_budget = min(max_download, remaining_budget - total_downloaded)
                if per_file_budget <= 0:
                    raise ValueError("total download budget exhausted")
                accept = "application/xml" if source["type"] == "boe_xml_documents" else "text/html,application/xhtml+xml"
                total_downloaded += _download(url, target, per_file_budget, accept=accept)
            entries.append((item, target))
        for item, path in entries:
            text = _boe_latest_text(path) if source["type"] == "boe_xml_documents" else _cordis_text(path)
            if not text:
                raise ValueError(f"no editorial text extracted from {path.name}")
            rows.extend(_records_for_document(text, item["id"], {**source, "document_metadata": {item["id"]: item}}))
        hashes = {item["id"]: sha256(path) for item, path in entries}
        snapshot = {"snapshot_sha256": hashlib.sha256("\n".join(f"{name}:{digest}" for name, digest in hashes.items()).encode()).hexdigest(), "snapshot_bytes": sum(path.stat().st_size for _, path in entries), "downloaded_bytes": total_downloaded, "snapshot": source["filename"], "document_hashes": hashes}
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


def _boe_latest_text(path: Path) -> str:
    """Extract only the newest version of each block from BOE consolidated XML."""
    root = ET.parse(path).getroot()
    chunks: list[str] = []
    for block in root.iter("bloque"):
        versions = block.findall("version")
        if not versions:
            continue
        latest = max(versions, key=lambda item: item.get("fecha_publicacion", ""))
        for element in latest.iter():
            if element.tag.rsplit("}", 1)[-1] in {"p", "head", "l"}:
                value = normalize(" ".join(element.itertext()))
                if value:
                    chunks.append(value)
    return "\n".join(chunks)


class _CordisArticleParser(HTMLParser):
    """Keep editorial title, teaser and article paragraphs, excluding page chrome."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_main = False
        self.capture_tag: str | None = None
        self.current: list[str] = []
        self.chunks: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "main" and values.get("id") == "c-main":
            self.in_main = True
        if not self.in_main:
            return
        if tag in {"script", "style", "nav", "footer", "aside"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        selected = (tag in {"h1", "h2", "h3"}) or bool(classes & {"c-teaser", "c-article__text"})
        if selected and self.capture_tag is None:
            self.current = []
            self.capture_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            if tag in {"script", "style", "nav", "footer", "aside"}:
                self.skip_depth -= 1
            return
        if tag == self.capture_tag:
            value = normalize("".join(self.current))
            if value:
                self.chunks.append(value)
            self.capture_tag = None
        if tag == "main" and self.in_main:
            self.in_main = False

    def handle_data(self, data: str) -> None:
        if self.in_main and self.capture_tag and not self.skip_depth:
            self.current.append(data)


def _cordis_text(path: Path) -> str:
    parser = _CordisArticleParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parser.chunks)


def _records_for_document(text: str, document: str, source: dict) -> list[dict]:
    metadata = source.get("document_metadata", {}).get(document, {})
    url = metadata.get("url") or source.get("source_page") or source.get("url_template", source.get("url", ""))
    return [{"text": sentence, "document_id": f"{source['id']}:{document}", "source_id": document, "source": source["id"], "domain": source["domain"], "url": url, "license": source["license"], "license_url": source.get("license_url", ""), "attribution": source["attribution"], "source_metadata": metadata} for sentence in _sentences(text)]


def prepare(config_path: Path, output_dir: Path, source_ids: set[str] | None = None, offline: bool = False) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    _check_capacity(output_dir, config)
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
            elif source["type"] in {"boe_xml_documents", "cordis_html_documents"}:
                extension = ".xml" if source["type"] == "boe_xml_documents" else ".html"
                missing = [item["id"] for item in source["documents"] if not (raw_dir / source["id"] / f"{item['id']}{extension}").exists()]
                if missing:
                    raise FileNotFoundError(f"offline mode: missing {len(missing)} pinned source files; first: {missing[0]}")
            elif not (raw_dir / source["filename"]).exists():
                raise FileNotFoundError(f"offline mode: missing snapshot {source['filename']}")
        records, snapshot = _load_source_records(source, raw_dir, int(config["max_download_bytes"]), budget)
        budget -= snapshot["downloaded_bytes"]
        snapshots[source["id"]] = snapshot
        all_rows.extend(records)

    minimum, maximum = int(config["min_characters"]), int(config["max_characters"])
    seen, accepted, rejected, duplicates = {}, [], Counter(), 0
    ratios = (float(config["train_ratio"]), float(config["validation_ratio"]), float(config["test_ratio"]))
    if abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError("split ratios must sum to 1")
    for row in all_rows:
        row.setdefault("domain", row["source"])
        row.setdefault("source_metadata", {})
        text = normalize(row["text"])
        reasons = quality_reasons(text, minimum, maximum)
        if reasons:
            rejected.update(reasons)
            continue
        fingerprint = hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()
        if fingerprint in seen:
            duplicates += 1
            provenance = row.get("provenance", [{key: row.get(key) for key in ("source", "source_id", "domain", "url", "license", "license_url", "attribution", "source_metadata")}])
            existing = seen[fingerprint].setdefault("provenance", [{key: seen[fingerprint].get(key) for key in ("source", "source_id", "domain", "url", "license", "license_url", "attribution", "source_metadata")}])
            for item in provenance:
                if item not in existing:
                    existing.append(item)
            continue
        row["provenance"] = row.get("provenance", [{key: row.get(key) for key in ("source", "source_id", "domain", "url", "license", "license_url", "attribution", "source_metadata")}])
        seen[fingerprint] = row
        row["text"] = text
        row["document_hash"] = hashlib.sha256(row["document_id"].encode()).hexdigest()
        row["split"] = _split(row["document_id"], int(config["seed"]), ratios)
        row["text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        accepted.append(row)

    # Stratify at document granularity and guarantee all partitions when >=3 documents exist.
    docs_by_source: dict[str, list[str]] = {}
    for row in accepted:
        docs_by_source.setdefault(row["source"], []).append(row["document_id"])
    split_by_document = {}
    for source_id, source_documents in sorted(docs_by_source.items()):
        documents = sorted(set(source_documents), key=lambda d: hashlib.sha256(f"{config['seed']}:{d}".encode()).hexdigest())
        if len(documents) < 3:
            raise ValueError(f"source {source_id} needs at least three eligible documents for source-stratified splits")
        train_end = max(1, int(len(documents) * ratios[0]))
        validation_count = max(1, int(len(documents) * ratios[1]))
        if train_end + validation_count >= len(documents):
            train_end = len(documents) - 2
            validation_count = 1
        split_by_document.update({doc: "train" if index < train_end else "validation" if index < train_end + validation_count else "test" for index, doc in enumerate(documents)})
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
        "schema_version": 1, "pipeline_version": "0.1.0", "dataset_status": "technically_prepared_candidate; human source review pending; not approved for training or distribution", "seed": int(config["seed"]),
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "normalization": "HTML entity decode, remove BOM/soft hyphen, Unicode NFC, collapse whitespace",
        "split_unit": "source document (Tatoeba sentence is its own document)",
        "split_ratios": {"train": ratios[0], "validation": ratios[1], "test": ratios[2]},
        "sources": [{**s, **snapshots[s["id"]]} for s in selected],
        "counts": {"input": len(all_rows), "accepted": len(accepted), "duplicates": duplicates, "rejected_by_reason": dict(rejected), "splits": dict(split_counts)},
        "distribution_by_domain": {domain: {split: sum(1 for row in accepted if row["domain"] == domain and row["split"] == split) for split in ("train", "validation", "test")} for domain in sorted({row["domain"] for row in accepted})},
        "documents_by_split_sha256": {name: hashlib.sha256("\n".join(ids).encode()).hexdigest() for name, ids in docs_by_split.items()},
        "quality_checks": {"min_characters": minimum, "max_characters": maximum, "url_filter": True, "unicode_controls": True, "letter_ratio_minimum": 0.35, "pii_pattern_screen": {pattern: sum(1 for row in accepted if pattern in pii_findings(row["text"])) for pattern in PII_PATTERNS}, "pii_limit": "pattern screen only; names and contextual personal data require human review", "factuality": "source authority and editorial process documented; factual claims require human sampling"},
        "resource_preflight": {"artifact_directory": str(output_dir.resolve()), "free_disk_bytes_before_run": shutil.disk_usage(output_dir).free, "available_ram_bytes_before_run": _available_memory_bytes(), "configured_min_free_disk_bytes": int(config["min_free_disk_bytes"]), "configured_min_available_memory_bytes": int(config.get("min_available_memory_bytes", 0)), "download_budget_bytes": int(config["max_total_download_bytes"]), "artifact_storage_cap_bytes": int(config["max_pipeline_storage_bytes"]), "tokenizer_max_train_documents": int(config["max_tokenizer_train_documents"]), "tokenizer_max_runtime_seconds": int(config.get("max_tokenizer_runtime_seconds", 0)), "tokenizer_candidates": config["vocab_candidates"]},
        "artifacts": {},
    }
    for split in ("train", "validation", "test"):
        path = processed_dir / f"{split}.jsonl"
        manifest["artifacts"][path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    (processed_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _check_output_size(output_dir, config)
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

    config_path = Path(__file__).resolve().parents[3] / "configs" / "data-pipeline.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    _check_capacity(output_dir, config)
    started = time.perf_counter()
    processed = output_dir / "processed"
    records = [json.loads(line) for line in (processed / "train.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if not records:
        raise ValueError("train split is empty")
    docs: dict[str, list[str]] = {}
    for row in records:
        docs.setdefault(row["document_hash"], []).append(row["text"])
    train_texts = ["\n".join(texts) for texts in docs.values()]
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
        train_chars = sum(len(r["text"]) for r in records)
        val_chars = sum(map(len, validation))
        train_tokens = sum(len(tokenizer.encode(r["text"]).ids) for r in records)
        val_tokens = sum(len(tokenizer.encode(t).ids) for t in validation)
        model_path = artifacts / f"bpe-vocab-{vocab}.json"
        tokenizer.save(str(model_path))
        reports.append({"requested_vocab": vocab, "actual_vocab": tokenizer.get_vocab_size(), "train_documents": len(train_texts), "train_characters": train_chars, "train_tokens": train_tokens, "train_tokens_per_character": train_tokens / max(1, train_chars), "validation_documents": validation_documents, "validation_records": len(validation), "validation_characters": val_chars, "validation_tokens": val_tokens, "validation_tokens_per_character": val_tokens / max(1, val_chars), "compression_ratio_characters_per_token_train": train_chars / max(1, train_tokens), "model_file": model_path.name, "model_sha256": sha256(model_path)})
        if time.perf_counter() - started > int(config.get("max_tokenizer_runtime_seconds", 0)) > 0:
            raise TimeoutError("tokenizer candidate search exceeded configured CPU time budget")
    selected = min(reports, key=lambda x: x["validation_tokens_per_character"])
    final_path = artifacts / "tokenizer.json"
    (artifacts / selected["model_file"]).replace(final_path)
    selected_tokenizer = Tokenizer.from_file(str(final_path))
    corpus_measurements: dict[str, dict] = {}
    overall_words: set[str] = set()
    overall_documents: set[str] = set()
    overall_domains: dict[str, dict] = {}
    overall = {"rows": 0, "characters": 0, "whitespace_words": 0, "bpe_tokens": 0}
    for split in ("train", "validation", "test"):
        split_rows = [json.loads(line) for line in (processed / f"{split}.jsonl").read_text(encoding="utf-8").splitlines() if line]
        domains: dict[str, dict] = {}
        for row in split_rows:
            domain = row.get("domain", row["source"])
            measure = domains.setdefault(domain, {"rows": 0, "documents": set(), "characters": 0, "whitespace_words": 0, "unique_whitespace_words": set(), "bpe_tokens": 0})
            words = row["text"].casefold().split()
            row_tokens = len(selected_tokenizer.encode(row["text"]).ids)
            overall["rows"] += 1
            overall["characters"] += len(row["text"])
            overall["whitespace_words"] += len(words)
            overall["bpe_tokens"] += row_tokens
            overall_words.update(words)
            overall_documents.add(row["document_hash"])
            aggregate = overall_domains.setdefault(domain, {"rows": 0, "documents": set(), "characters": 0, "whitespace_words": 0, "unique_whitespace_words": set(), "bpe_tokens": 0})
            aggregate["rows"] += 1
            aggregate["documents"].add(row["document_hash"])
            aggregate["characters"] += len(row["text"])
            aggregate["whitespace_words"] += len(words)
            aggregate["unique_whitespace_words"].update(words)
            aggregate["bpe_tokens"] += row_tokens
            measure["rows"] += 1
            measure["documents"].add(row["document_hash"])
            measure["characters"] += len(row["text"])
            measure["whitespace_words"] += len(words)
            measure["unique_whitespace_words"].update(words)
            measure["bpe_tokens"] += row_tokens
        finalized = {}
        for domain, measure in domains.items():
            unique_words = len(measure.pop("unique_whitespace_words"))
            measure["documents"] = len(measure["documents"])
            measure["unique_whitespace_words"] = unique_words
            measure["lexical_type_token_ratio"] = unique_words / max(1, measure["whitespace_words"])
            measure["bpe_tokens_per_character"] = measure["bpe_tokens"] / max(1, measure["characters"])
            finalized[domain] = measure
        total_tokens = sum(item["bpe_tokens"] for item in finalized.values())
        total_chars = sum(item["characters"] for item in finalized.values())
        corpus_measurements[split] = {"rows": len(split_rows), "documents": len({row["document_hash"] for row in split_rows}), "characters": total_chars, "whitespace_words": sum(item["whitespace_words"] for item in finalized.values()), "unique_whitespace_words": len({word for row in split_rows for word in row["text"].casefold().split()}), "bpe_tokens": total_tokens, "bpe_tokens_per_character": total_tokens / max(1, total_chars), "by_domain": finalized}
    overall["documents"] = len(overall_documents)
    overall["unique_whitespace_words"] = len(overall_words)
    overall["lexical_type_token_ratio"] = len(overall_words) / max(1, overall["whitespace_words"])
    overall["bpe_tokens_per_character"] = overall["bpe_tokens"] / max(1, overall["characters"])
    for measure in overall_domains.values():
        unique_words = len(measure.pop("unique_whitespace_words"))
        measure["documents"] = len(measure["documents"])
        measure["unique_whitespace_words"] = unique_words
        measure["lexical_type_token_ratio"] = unique_words / max(1, measure["whitespace_words"])
        measure["bpe_tokens_per_character"] = measure["bpe_tokens"] / max(1, measure["characters"])
    report = {"algorithm": "byte-level BPE", "library": "tokenizers", "normalization": "NFC", "training_data": "train documents only", "selection_metric": "lowest validation tokens per character", "candidate_measurements": reports, "corpus_measurements_with_selected_tokenizer": {"all": {**overall, "by_domain": overall_domains}, **corpus_measurements}, "selected_vocab": selected["requested_vocab"], "selected_actual_vocab": selected["actual_vocab"], "tokenizer_runtime_seconds": round(time.perf_counter() - started, 3), "configured_runtime_limit_seconds": int(config.get("max_tokenizer_runtime_seconds", 0)), "tokenizer_file": final_path.name, "tokenizer_sha256": sha256(final_path), "test_split_used_for_selection": False}
    (artifacts / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _check_output_size(output_dir, config)
    return report


def verify_offline(output_dir: Path) -> dict:
    """Verify frozen files with networking APIs blocked; requires no network."""
    from unittest.mock import patch

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access attempted in offline verification")

    with patch("urllib.request.urlopen", blocked), patch("socket.create_connection", blocked), patch("socket.socket.connect", blocked):
        report = validate(output_dir)
        manifest = json.loads((output_dir / "processed" / "manifest.json").read_text(encoding="utf-8"))
        raw_bytes = 0
        raw_files = 0
        for source in manifest.get("sources", []):
            source_type = source["type"]
            hashes = source.get("document_hashes")
            if hashes:
                actual = {}
                if source_type == "eltec_files":
                    paths = {name: output_dir / "raw" / source["id"] / name for name in hashes}
                elif source_type in {"boe_xml_documents", "cordis_html_documents"}:
                    extension = ".xml" if source_type == "boe_xml_documents" else ".html"
                    paths = {name: output_dir / "raw" / source["id"] / f"{name}{extension}" for name in hashes}
                else:
                    raise ValueError(f"unsupported raw snapshot manifest for offline verification: {source_type}")
                for name, path in paths.items():
                    if not path.is_file():
                        raise FileNotFoundError(f"offline source snapshot missing: {path}")
                    actual[name] = sha256(path)
                    if actual[name] != hashes[name]:
                        raise ValueError(f"source snapshot hash mismatch: {source['id']}:{name}")
                    raw_bytes += path.stat().st_size
                    raw_files += 1
                combined = hashlib.sha256("\n".join(f"{name}:{digest}" for name, digest in actual.items()).encode()).hexdigest()
                if combined != source["snapshot_sha256"]:
                    raise ValueError(f"source snapshot aggregate hash mismatch: {source['id']}")
                if sum(path.stat().st_size for path in paths.values()) != source["snapshot_bytes"]:
                    raise ValueError(f"source snapshot byte count mismatch: {source['id']}")
            else:
                path = output_dir / "raw" / source["filename"]
                if not path.is_file():
                    raise FileNotFoundError(f"offline source snapshot missing: {path}")
                if sha256(path) != source["snapshot_sha256"] or path.stat().st_size != source["snapshot_bytes"]:
                    raise ValueError(f"source snapshot integrity mismatch: {source['id']}")
                raw_bytes += path.stat().st_size
                raw_files += 1
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
        return {**report, "offline_network_blocked": True, "raw_source_files_verified": raw_files, "raw_source_bytes_verified": raw_bytes, "test_sample_tokens": len(ids), "test_sample_roundtrip_nonempty": True, "tokenizer_sha256": sha256(tokenizer_path)}
