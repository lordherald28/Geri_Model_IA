"""Offline chat inference for an approved Geriv2 SFT checkpoint."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import torch
from tokenizers import Tokenizer

from geri.model.transformer import GeriTransformer


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_manifest(path: Path, expected_hash: str, tokenizer_hash: str, name: str) -> None:
    if not path.is_file() or _sha256(path) != expected_hash:
        raise ValueError(f"{name} manifest is missing or differs from the checkpoint")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    scope = manifest.get("authorization_scope", {})
    review = manifest.get("human_review", {})
    sources = manifest.get("sources", [])
    if (manifest.get("dataset_status") != "approved_for_training"
            or manifest.get("training_authorization") != "human_review_approved"
            or review.get("decision") != "approved" or not review.get("reviewer") or not review.get("approved_at_utc")
            or not sources or any(source.get("review_status") != "human_approved" for source in sources)
            or scope.get("purpose") != "experimental_private_training_only"
            or scope.get("network_during_training") is not False
            or scope.get("corpus_distribution_authorized") is not False
            or scope.get("model_weight_distribution_authorized") is not False
            or scope.get("factuality_certified") is not False):
        raise ValueError(f"{name} manifest approval scope is missing or changed")
    if manifest.get("tokenizer_sha256") != tokenizer_hash:
        raise ValueError(f"{name} tokenizer hash does not match checkpoint tokenizer")


def load_promoted_model(checkpoint_path: Path, tokenizer_path: Path,
                        pretraining_manifest: Path, sft_manifest: Path):
    """Load weights read-only, validating file and frozen corpus provenance."""
    checkpoint_path, tokenizer_path = Path(checkpoint_path), Path(tokenizer_path)
    if not checkpoint_path.is_file() or not tokenizer_path.is_file():
        raise FileNotFoundError("promoted checkpoint and original tokenizer are required")
    digest_file = checkpoint_path.with_suffix(checkpoint_path.suffix + ".sha256")
    if not digest_file.is_file() or _sha256(checkpoint_path) != digest_file.read_text(encoding="ascii").strip():
        raise ValueError("promoted checkpoint integrity hash is missing or invalid")
    tokenizer_hash = _sha256(tokenizer_path)
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    required = {"model", "config", "pretraining_metadata", "sft_metadata"}
    if not required.issubset(state):
        raise ValueError("checkpoint is missing required inference metadata")
    _validate_manifest(Path(pretraining_manifest), state["pretraining_metadata"].get("manifest_sha256", ""), tokenizer_hash, "pretraining")
    _validate_manifest(Path(sft_manifest), state["sft_metadata"].get("manifest_sha256", ""), tokenizer_hash, "SFT")
    config = state["config"].get("model", {})
    if int(config.get("vocab_size", -1)) != tokenizer.get_vocab_size():
        raise ValueError("checkpoint model vocabulary does not match the original tokenizer")
    model = GeriTransformer(config)
    model.load_state_dict(state["model"], strict=True)
    model.eval()
    return model, tokenizer


def serialize_history(messages: list[dict[str, str]]) -> str:
    """Match SFT: alternating `<|role|>\ncontent\n` records, no BOS/system."""
    return "".join(f"<|{item['role']}|>\n{item['content'].strip()}\n" for item in messages)


def _filter_logits(logits: torch.Tensor, temperature: float, top_k: int, top_p: float) -> torch.Tensor:
    if temperature < 0 or top_k < 0 or not 0 < top_p <= 1:
        raise ValueError("temperature and top-k must be nonnegative; top-p must be in (0, 1]")
    logits = logits.float().clone()
    if temperature == 0:
        return logits
    logits /= temperature
    if top_k:
        count = min(top_k, logits.numel())
        threshold = torch.topk(logits, count).values[-1]
        logits[logits < threshold] = -torch.inf
    if top_p < 1:
        sorted_logits, sorted_indices = torch.sort(logits, descending=True)
        cumulative = torch.softmax(sorted_logits, dim=-1).cumsum(dim=-1)
        remove = cumulative - torch.softmax(sorted_logits, dim=-1) >= top_p
        sorted_logits[remove] = -torch.inf
        logits.fill_(-torch.inf).scatter_(0, sorted_indices, sorted_logits)
    return logits


@torch.inference_mode()
def generate(model: GeriTransformer, tokenizer: Tokenizer, messages: list[dict[str, str]], *,
             temperature: float = 0.8, top_k: int = 40, top_p: float = 0.9,
             max_new_tokens: int = 96) -> dict:
    if not messages or messages[-1].get("role") != "user":
        raise ValueError("chat history must end with a user message")
    if max_new_tokens < 1:
        raise ValueError("max_new_tokens must be positive")
    config = model.config
    context = int(config["max_seq_len"])
    prompt = serialize_history(messages) + "<|assistant|>\n"
    ids = tokenizer.encode(prompt).ids
    ids = ids[-context:]
    eos_id = tokenizer.token_to_id("<eos>")
    generated: list[int] = []
    started = time.perf_counter()
    for _ in range(max_new_tokens):
        input_ids = torch.tensor([ids[-context:]], dtype=torch.long)
        logits = model(input_ids)[0, -1]
        filtered = _filter_logits(logits, temperature, top_k, top_p)
        next_id = int(torch.argmax(filtered).item()) if temperature == 0 else int(torch.multinomial(torch.softmax(filtered, dim=-1), 1).item())
        if next_id == eos_id:
            break
        generated.append(next_id)
        ids.append(next_id)
    elapsed = max(time.perf_counter() - started, 1e-9)
    text = tokenizer.decode(generated, skip_special_tokens=True)
    for marker in ("\n<|user|>", "\n<|assistant|>"):
        if marker in text:
            text = text.split(marker, 1)[0]
    return {"text": text.strip(), "tokens": len(generated), "seconds": elapsed,
            "tokens_per_second": len(generated) / elapsed}
