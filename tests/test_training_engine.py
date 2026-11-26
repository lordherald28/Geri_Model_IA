import json
import hashlib

import pytest

torch = pytest.importorskip("torch")

from geri.evaluation.regression import compare_regression
from geri.training.data import create_synthetic_smoke_data, load_frozen_corpus, load_sft_corpus
from geri.training.sft_prepare import prepare_sft
from geri.training.offline import offline_execution


def test_synthetic_fixture_is_separate_and_hash_verified(tmp_path):
    data, tokenizer = tmp_path / "data", tmp_path / "tokenizer" / "tokenizer.json"
    manifest = create_synthetic_smoke_data(data, tokenizer)
    assert manifest["dataset_status"] == "synthetic_smoke_test_only"
    with pytest.raises(ValueError, match="not approved"):
        load_frozen_corpus(data, tokenizer)
    splits, _ = load_frozen_corpus(data, tokenizer, allow_synthetic=True)
    assert len(splits["train"]) > 0
    assert len(splits["validation"]) > 0
    rows = {name: [json.loads(line) for line in (data / "processed" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()] for name in ("train", "validation", "test")}
    assert {r["document_hash"] for r in rows["train"]}.isdisjoint({r["document_hash"] for r in rows["validation"]})
    assert {r["document_hash"] for r in rows["train"]}.isdisjoint({r["document_hash"] for r in rows["test"]})


def test_loader_rejects_pending_corpus(tmp_path):
    root = tmp_path / "data"
    processed = root / "processed"
    processed.mkdir(parents=True)
    (processed / "manifest.json").write_text(json.dumps({"dataset_status": "technically_prepared_candidate; human source review pending"}), encoding="utf-8")
    with pytest.raises(ValueError, match="not approved for training"):
        load_frozen_corpus(root, tmp_path / "missing-tokenizer.json")


def test_approved_pretraining_loader_checks_source_license(tmp_path):
    data, tokenizer = tmp_path / "data", tmp_path / "tokenizer" / "tokenizer.json"
    manifest = create_synthetic_smoke_data(data, tokenizer)
    source = {"id": "synthetic_smoke_test", "license": "fixture-only", "review_status": "human_approved"}
    for split in ("train", "validation", "test"):
        path = data / "processed" / f"{split}.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            row["license"] = source["license"]
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        manifest["artifacts"][path.name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest.update({"dataset_status": "approved_for_training", "training_authorization": "human_review_approved",
        "human_review": {"decision": "approved", "reviewer": "fixture", "approved_at_utc": "2026-11-25T00:00:00Z"},
        "sources": [source]})
    (data / "processed" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    splits, _ = load_frozen_corpus(data, tokenizer)
    assert set(splits) == {"train", "validation", "test"}


def test_hash_mismatch_is_rejected(tmp_path):
    data, tokenizer = tmp_path / "data", tmp_path / "tokenizer" / "tokenizer.json"
    manifest = create_synthetic_smoke_data(data, tokenizer)
    manifest["training_authorization"] = "human_review_approved"
    (data / "processed" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    path = data / "processed" / "train.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        load_frozen_corpus(data, tokenizer, allow_synthetic=True)


def test_held_out_regression_gate():
    assert compare_regression({"loss": 2.0}, {"loss": 2.1})["passed"]
    assert not compare_regression({"loss": 2.0}, {"loss": 2.3})["passed"]


def _write_sft_fixture(tmp_path, existing_tokenizer=None):
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers
    data, tokenizer_path = tmp_path / "sft", existing_tokenizer or tmp_path / "sft-tokenizer.json"
    if existing_tokenizer is None:
        tokenizer = Tokenizer(models.BPE(unk_token="<unk>"))
        tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
        examples = ["<|user|>\nhola\n<|assistant|>\nhola\n", "<|user|>\nbuenos dias\n<|assistant|>\nbuenos dias\n"]
        tokenizer.train_from_iterator(examples, trainers.BpeTrainer(vocab_size=128, min_frequency=1, special_tokens=["<unk>", "<pad>", "<eos>"]))
        tokenizer.save(str(tokenizer_path))
    processed = data / "processed"
    processed.mkdir(parents=True)
    source = {"source_id": "authored_fixture", "source_url": "local://synthetic-fixture", "license": "fixture-only", "attribution": "synthetic test fixture", "review_status": "human_approved"}
    rows = {"train": [], "validation": [], "test": []}
    for i in range(8):
        split = "train" if i < 6 else "validation" if i == 6 else "test"
        rows[split].append({"split": split, "conversation_id": f"fixture-{i}", "source_id": source["source_id"],
            "source_url": source["source_url"], "license": source["license"], "attribution": source["attribution"],
            "messages": [{"role": "user", "content": f"hola {i}"}, {"role": "assistant", "content": f"respuesta {i}"}]})
    artifacts = {}
    for split, values in rows.items():
        path = processed / f"{split}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in values), encoding="utf-8")
        artifacts[path.name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"dataset_status": "approved_for_training", "training_authorization": "human_review_approved",
        "human_review": {"decision": "approved", "reviewer": "test", "approved_at_utc": "2026-11-25T00:00:00Z"},
        "sources": [source], "tokenizer_sha256": hashlib.sha256(tokenizer_path.read_bytes()).hexdigest(), "artifacts": artifacts}
    (processed / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return data, tokenizer_path


def test_sft_loader_checks_provenance_and_masks_user_loss(tmp_path):
    data, tokenizer = _write_sft_fixture(tmp_path)
    splits, _ = load_sft_corpus(data, tokenizer, block_size=64)
    inputs, labels = splits["train"][0]
    assert inputs.shape == labels.shape == (64,)
    assert (labels == -100).any()
    assert (labels != -100).any()
    assert len(splits["test"]) > 0


def test_sft_preparation_builds_hashed_candidate_but_never_approves_it(tmp_path):
    source = {"source_id": "source-a", "source_url": "local://fixture", "license": "fixture-only", "attribution": "fixture"}
    source_path = tmp_path / "sources.json"
    source_path.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
    input_path = tmp_path / "conversations.jsonl"
    input_path.write_text("".join(json.dumps({"conversation_id": f"id-{i}", "source_id": "source-a",
        "messages": [{"role": "user", "content": f"pregunta {i}"}, {"role": "assistant", "content": f"respuesta {i}"}]}) + "\n" for i in range(20)), encoding="utf-8")
    _, tokenizer_path = _write_sft_fixture(tmp_path)
    output = tmp_path / "prepared"
    manifest = prepare_sft(input_path, source_path, output, tokenizer_path)
    assert manifest["dataset_status"].startswith("prepared_candidate")
    assert manifest["human_review"]["decision"] == "pending"
    assert {row["review_status"] for row in manifest["sources"]} == {"pending_human_review"}
    assert set(manifest["split_conversation_ids"]) == {"train", "validation", "test"}
    with pytest.raises(ValueError, match="explicit human approval"):
        load_sft_corpus(output, tokenizer_path, block_size=64)


def test_sft_preparation_rejects_pattern_detected_pii(tmp_path):
    source = {"source_id": "source-a", "source_url": "local://fixture", "license": "fixture-only", "attribution": "fixture"}
    source_path = tmp_path / "sources.json"
    source_path.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
    input_path = tmp_path / "private.jsonl"
    rows = [{"conversation_id": f"id-{i}", "source_id": "source-a", "messages": [
        {"role": "user", "content": f"pregunta {i}"}, {"role": "assistant", "content": "contacta a demo@example.com" if i == 1 else f"respuesta {i}"}]} for i in range(20)]
    input_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    _, tokenizer_path = _write_sft_fixture(tmp_path)
    with pytest.raises(ValueError, match="PII"):
        prepare_sft(input_path, source_path, tmp_path / "prepared", tokenizer_path)


def test_offline_guard_rejects_socket_connections():
    import socket
    with offline_execution(), pytest.raises(RuntimeError, match="network access is disabled"):
        socket.create_connection(("example.invalid", 443), timeout=0.1)


def test_pretraining_then_sft_smoke_keeps_baseline_checkpoint(tmp_path):
    from geri.training.engine import train
    from tokenizers import Tokenizer
    create_synthetic_smoke_data(tmp_path / "pre", tmp_path / "shared-tokenizer.json")
    vocab_size = Tokenizer.from_file(str(tmp_path / "shared-tokenizer.json")).get_vocab_size()
    pre_splits, _ = load_frozen_corpus(tmp_path / "pre", tmp_path / "shared-tokenizer.json", allow_synthetic=True, block_size=64)
    sft_root, sft_tokenizer = _write_sft_fixture(tmp_path, tmp_path / "shared-tokenizer.json")
    sft_splits, _ = load_sft_corpus(sft_root, sft_tokenizer, block_size=64)
    datasets = {**pre_splits, "sft_train": sft_splits["train"], "sft_validation": sft_splits["validation"],
                "sft_test": sft_splits["test"], "sft_metadata": {"manifest_sha256": "synthetic-only"}}
    config = {"seed": 91, "device": "cpu", "num_threads": 2,
        "model": {"vocab_size": vocab_size, "d_model": 16, "n_heads": 2, "n_layers": 1, "d_ff": 32, "max_seq_len": 64, "dropout": 0.0},
        "pretraining": {"batch_size": 2, "learning_rate": 0.001, "weight_decay": 0.0, "max_steps": 2, "eval_interval": 1, "patience_evaluations": 3, "min_delta": 0.0, "max_grad_norm": 1.0},
        "sft": {"batch_size": 2, "learning_rate": 0.0005, "weight_decay": 0.0, "max_steps": 2, "eval_interval": 1, "patience_evaluations": 3, "min_delta": 0.0, "max_grad_norm": 1.0},
        "regression": {"max_loss_ratio": 1000.0},
        "resources": {"min_free_disk_bytes": 0, "min_available_memory_bytes": 0, "max_eval_batches": 2}}
    with offline_execution():
        result = train(config, datasets, tmp_path / "run", {"manifest_sha256": "synthetic-only"})
    assert result["pretraining"]["step"] == 2
    assert result["sft"]["step"] == 2
    assert result["sft_promoted"] is True
    assert (tmp_path / "run" / "pretraining" / "best.pt").is_file()
    assert (tmp_path / "run" / "promoted-sft.pt").is_file()


def test_checkpoint_recovery_after_interrupted_atomic_save(tmp_path, monkeypatch):
    from geri.model.transformer import GeriTransformer
    import geri.training.engine as engine
    from tokenizers import Tokenizer
    create_synthetic_smoke_data(tmp_path / "data", tmp_path / "tok.json")
    vocab_size = Tokenizer.from_file(str(tmp_path / "tok.json")).get_vocab_size()
    tokenizer = tmp_path / "tok.json"
    data_root = tmp_path / "data"
    # The synthetic fixture is explicitly isolated to this smoke test.
    splits, _ = load_frozen_corpus(data_root, tokenizer, allow_synthetic=True, block_size=8)
    config = {"seed": 91, "device": "cpu", "num_threads": 2,
        "model": {"vocab_size": vocab_size, "d_model": 16, "n_heads": 2, "n_layers": 1, "d_ff": 32, "max_seq_len": 8, "dropout": 0.0},
        "resources": {"min_free_disk_bytes": 0, "min_available_memory_bytes": 0, "max_eval_batches": 2}}
    phase = {"batch_size": 2, "learning_rate": 0.001, "weight_decay": 0.0, "max_steps": 3,
        "eval_interval": 1, "patience_evaluations": 5, "min_delta": 0.0, "max_grad_norm": 1.0}
    original = engine._atomic_checkpoint
    interrupted = {"value": False}
    def interrupt_after_latest(path, state):
        original(path, state)
        if path.name == "latest.pt" and not interrupted["value"]:
            interrupted["value"] = True
            raise RuntimeError("simulated process interruption")
    monkeypatch.setattr(engine, "_atomic_checkpoint", interrupt_after_latest)
    model = GeriTransformer(config["model"])
    with pytest.raises(RuntimeError, match="simulated"):
        engine.run_phase("recovery", model, splits["train"], splits["validation"], phase, config, tmp_path / "runs", {"fixture": True})
    monkeypatch.setattr(engine, "_atomic_checkpoint", original)
    resumed = GeriTransformer(config["model"])
    result = engine.run_phase("recovery", resumed, splits["train"], splits["validation"], phase, config, tmp_path / "runs", {"fixture": True}, resume=True)
    assert result["step"] == phase["max_steps"]
    assert (tmp_path / "runs" / "recovery" / "latest.pt.sha256").is_file()


def test_corrupt_latest_checkpoint_falls_back_to_previous_verified_copy(tmp_path):
    from geri.training.engine import _atomic_checkpoint, _verified_checkpoint
    path = tmp_path / "latest.pt"
    _atomic_checkpoint(path, {"step": 1})
    _atomic_checkpoint(path, {"step": 2})
    path.write_bytes(path.read_bytes() + b"corrupt")
    fallback = _verified_checkpoint(path)
    assert fallback == tmp_path / "latest.pt.prev"
    assert torch.load(fallback, weights_only=False)["step"] == 1
