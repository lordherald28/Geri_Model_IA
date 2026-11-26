"""Offline, hash-verified train/validation loading with approval gates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import torch
from torch.utils.data import Dataset
from geri.data.pipeline import pii_findings, quality_reasons


class TokenBlockDataset(Dataset):
    def __init__(self, tokens: list[int], block_size: int):
        if len(tokens) < block_size + 1:
            raise ValueError("split has fewer than block_size + 1 tokens")
        self.tokens = torch.tensor(tokens, dtype=torch.long)
        self.block_size = block_size

    def __len__(self) -> int:
        return self.tokens.numel() - self.block_size

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        block = self.tokens[index:index + self.block_size + 1]
        return block[:-1], block[1:]


class ConversationDataset(Dataset):
    """Fixed-length causal examples whose loss is masked on user/system text."""
    def __init__(self, examples: list[tuple[list[int], list[int]]], block_size: int, pad_id: int):
        self.examples = examples
        self.block_size = block_size
        self.pad_id = pad_id

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        inputs, labels = self.examples[index]
        padding = self.block_size - len(inputs)
        return (torch.tensor(inputs + [self.pad_id] * padding, dtype=torch.long),
                torch.tensor(labels + [-100] * padding, dtype=torch.long))


def _require_human_approval(manifest: dict) -> None:
    if manifest.get("dataset_status") != "approved_for_training" or manifest.get("training_authorization") != "human_review_approved":
        raise ValueError("dataset lacks explicit human approval for training")
    review = manifest.get("human_review", {})
    if review.get("decision") != "approved" or not review.get("reviewer") or not review.get("approved_at_utc"):
        raise ValueError("dataset human review record is incomplete")
    sources = manifest.get("sources", [])
    if not sources or any(s.get("review_status") != "human_approved" for s in sources):
        raise ValueError("one or more corpus sources lack human review approval")


def _check_tokenizer_hash(manifest: dict, tokenizer_path: Path) -> None:
    expected = manifest.get("tokenizer_sha256")
    if not expected or hashlib.sha256(tokenizer_path.read_bytes()).hexdigest() != expected:
        raise ValueError("tokenizer missing from manifest or hash mismatch")


def load_frozen_corpus(root: Path, tokenizer_path: Path, allow_synthetic: bool = False, block_size: int | None = None) -> tuple[dict[str, TokenBlockDataset], dict]:
    from tokenizers import Tokenizer

    manifest_path = root / "processed" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    status = manifest.get("dataset_status", "")
    if status != "approved_for_training" and not (allow_synthetic and status == "synthetic_smoke_test_only"):
        raise ValueError(f"dataset not approved for training: {status or 'missing approval status'}")
    manifest_block_size = manifest.get("max_seq_len")
    if status == "approved_for_training" and block_size is not None and manifest_block_size is not None and int(block_size) != int(manifest_block_size):
        raise ValueError(f"configured block_size {block_size} does not match manifest max_seq_len {manifest_block_size}")
    effective_block_size = block_size if block_size is not None else manifest_block_size
    if not isinstance(effective_block_size, int) or effective_block_size <= 0:
        raise ValueError("block_size is required when the corpus manifest has no positive max_seq_len")
    if status == "approved_for_training":
        _require_human_approval(manifest)
        _check_tokenizer_hash(manifest, tokenizer_path)
    approved_sources = {source.get("id", source.get("source_id")): source for source in manifest.get("sources", [])
                        if source.get("review_status") == "human_approved"}
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    if status == "synthetic_smoke_test_only" and allow_synthetic:
        _check_tokenizer_hash(manifest, tokenizer_path)
    splits: dict[str, TokenBlockDataset] = {}
    split_docs: dict[str, set[str]] = {}
    split_texts: dict[str, set[str]] = {}
    for split in ("train", "validation", "test"):
        path = root / "processed" / f"{split}.jsonl"
        expected = manifest.get("artifacts", {}).get(path.name, {}).get("sha256")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if not expected or digest != expected:
            raise ValueError(f"missing or mismatched frozen hash for {path.name}")
        tokens: list[int] = []
        docs, texts = set(), set()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            row = json.loads(line)
            if row.get("split") != split or not row.get("text") or not row.get("document_hash"):
                raise ValueError(f"invalid {split} row")
            if status == "approved_for_training":
                source = approved_sources.get(row.get("source"))
                if not source or source.get("license") != row.get("license"):
                    raise ValueError(f"row source/license not approved at {path.name}:{line_no}")
            docs.add(row["document_hash"])
            texts.add(hashlib.sha256(row["text"].casefold().encode()).hexdigest())
            tokens.extend(tokenizer.encode(row["text"]).ids)
            eos = tokenizer.token_to_id("<eos>")
            if eos is not None:
                tokens.append(eos)
        splits[split] = TokenBlockDataset(tokens, effective_block_size)
        split_docs[split], split_texts[split] = docs, texts
    for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
        if split_docs[left] & split_docs[right] or split_texts[left] & split_texts[right]:
            raise ValueError(f"{left}/{right} leakage detected")
    if manifest.get("dataset_status") == "synthetic_smoke_test_only" and not allow_synthetic:
        raise ValueError("synthetic data is restricted to explicit smoke-test mode")
    return splits, manifest


def load_sft_corpus(root: Path, tokenizer_path: Path, block_size: int) -> tuple[dict[str, ConversationDataset], dict]:
    """Load separately approved JSONL conversations with provenance and assistant-only loss."""
    from tokenizers import Tokenizer

    processed = root / "processed"
    manifest = json.loads((processed / "manifest.json").read_text(encoding="utf-8"))
    manifest_block_size = manifest.get("max_seq_len")
    if manifest_block_size is not None and int(block_size) != int(manifest_block_size):
        raise ValueError(f"configured block_size {block_size} does not match SFT manifest max_seq_len {manifest_block_size}")
    _require_human_approval(manifest)
    _check_tokenizer_hash(manifest, tokenizer_path)
    approved_sources = {s["source_id"]: s for s in manifest["sources"] if s.get("review_status") == "human_approved" and s.get("license")}
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    pad_id = tokenizer.token_to_id("<pad>")
    eos_id = tokenizer.token_to_id("<eos>")
    if pad_id is None or eos_id is None:
        raise ValueError("SFT tokenizer requires <pad> and <eos> tokens")
    datasets: dict[str, ConversationDataset] = {}
    seen_doc_ids: dict[str, set[str]] = {}
    seen_content: dict[str, set[str]] = {}
    for split in ("train", "validation", "test"):
        path = processed / f"{split}.jsonl"
        expected = manifest.get("artifacts", {}).get(path.name, {}).get("sha256")
        if not expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"missing or mismatched frozen hash for {path.name}")
        examples, doc_ids, content_hashes = [], set(), set()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            row = json.loads(line)
            if row.get("split") != split:
                raise ValueError(f"split mismatch at {path.name}:{line_no}")
            for field in ("conversation_id", "source_id", "source_url", "license", "attribution"):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError(f"missing {field} at {path.name}:{line_no}")
            approved = approved_sources.get(row["source_id"])
            if not approved or approved["license"] != row["license"] or approved.get("source_url") != row["source_url"] or approved.get("attribution") != row["attribution"]:
                raise ValueError(f"conversation source has no matching approved license at {path.name}:{line_no}")
            messages = row.get("messages")
            if not isinstance(messages, list) or len(messages) < 2 or len(messages) % 2:
                raise ValueError(f"invalid message count at {path.name}:{line_no}")
            if [m.get("role") for m in messages] != [role for _ in range(len(messages)//2) for role in ("user", "assistant")]:
                raise ValueError(f"messages must alternate user/assistant at {path.name}:{line_no}")
            if any(not isinstance(m.get("content"), str) or not m["content"].strip() for m in messages):
                raise ValueError(f"empty or invalid message at {path.name}:{line_no}")
            for message in messages:
                content = message["content"].strip()
                if pii_findings(content):
                    raise ValueError(f"pattern-detected PII at {path.name}:{line_no}")
                if {"too_long", "control_or_replacement_character"} & set(quality_reasons(content, 1, 8000)):
                    raise ValueError(f"message failed structural quality screen at {path.name}:{line_no}")
            ids: list[int] = []
            supervised: list[bool] = []
            for message in messages:
                prefix = f"<|{message['role']}|>\n"
                part = tokenizer.encode(prefix + message["content"].strip() + "\n").ids
                ids.extend(part)
                supervised.extend([message["role"] == "assistant"] * len(part))
            ids.append(eos_id)
            supervised.append(True)
            if len(ids) > block_size:
                raise ValueError(f"conversation exceeds max_seq_len at {path.name}:{line_no}")
            if len(ids) < 3:
                raise ValueError(f"conversation too short at {path.name}:{line_no}")
            labels = [-100 if not supervised[i + 1] else ids[i + 1] for i in range(len(ids) - 1)]
            doc_ids.add(row["conversation_id"])
            content_hashes.add(hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
            examples.append((ids[:-1], labels))
        if not examples:
            raise ValueError(f"empty SFT {split} split")
        datasets[split] = ConversationDataset(examples, block_size, pad_id)
        seen_doc_ids[split], seen_content[split] = doc_ids, content_hashes
    for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
        if seen_doc_ids[left] & seen_doc_ids[right] or seen_content[left] & seen_content[right]:
            raise ValueError(f"SFT conversation leakage across {left}/{right}")
    return datasets, manifest


def create_synthetic_smoke_data(root: Path, tokenizer_path: Path, seed: int = 20261125) -> dict:
    """Build a deterministic tiny fixture; never reads the candidate corpus."""
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers

    root.mkdir(parents=True, exist_ok=True)
    processed = root / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    examples = [f"<user> ejemplo sintetico numero {i} <assistant> respuesta local de prueba {i}" for i in range(80)]
    tokenizer = Tokenizer(models.BPE(unk_token="<unk>"))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.train_from_iterator(examples, trainers.BpeTrainer(vocab_size=256, min_frequency=1, special_tokens=["<unk>", "<pad>", "<eos>"]))
    tokenizer_path.parent.mkdir(parents=True, exist_ok=True)
    tokenizer.save(str(tokenizer_path))
    rows = {"train": [], "validation": [], "test": []}
    for i, text in enumerate(examples):
        split = "train" if i < 64 else "validation" if i < 72 else "test"
        rows[split].append({"split": split, "text": text, "document_hash": hashlib.sha256(f"synthetic-{i}".encode()).hexdigest(), "source": "synthetic_smoke_test"})
    artifacts = {}
    for split, items in rows.items():
        path = processed / f"{split}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in items), encoding="utf-8")
        artifacts[path.name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"dataset_status": "synthetic_smoke_test_only", "max_seq_len": 32, "artifacts": artifacts,
                "tokenizer_sha256": hashlib.sha256(tokenizer_path.read_bytes()).hexdigest(),
                "seed": seed, "source": "deterministic synthetic fixture; not product training data"}
    (processed / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
