import hashlib
import json

import pytest

torch = pytest.importorskip("torch")

from geri.inference.runtime import _filter_logits, generate, load_promoted_model, serialize_history
from geri.model.transformer import GeriTransformer


def _write_approved_fixture(tmp_path):
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers

    tokenizer = Tokenizer(models.BPE(unk_token="<unk>"))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.train_from_iterator(
        ["<|user|>\nhola\n<|assistant|>\nHola, soy Geri.\n<eos>", "<|user|>\ncomo estas\n<|assistant|>\nEstoy bien.\n<eos>"],
        trainers.BpeTrainer(vocab_size=96, min_frequency=1, special_tokens=["<unk>", "<pad>", "<eos>"]),
    )
    tokenizer_path = tmp_path / "tokenizer.json"
    tokenizer.save(str(tokenizer_path))
    tok_hash = hashlib.sha256(tokenizer_path.read_bytes()).hexdigest()
    scope = {"purpose": "experimental_private_training_only", "network_during_training": False,
             "corpus_distribution_authorized": False, "model_weight_distribution_authorized": False,
             "factuality_certified": False}
    manifests = []
    for name in ("pretraining", "sft"):
        path = tmp_path / f"{name}.json"
        manifest = {"dataset_status": "approved_for_training", "training_authorization": "human_review_approved",
                    "human_review": {"decision": "approved", "reviewer": "fixture", "approved_at_utc": "2026-11-25T00:00:00Z"},
                    "sources": [{"review_status": "human_approved"}], "authorization_scope": scope,
                    "tokenizer_sha256": tok_hash}
        path.write_text(json.dumps(manifest), encoding="utf-8")
        manifests.append((path, hashlib.sha256(path.read_bytes()).hexdigest()))
    config = {"vocab_size": tokenizer.get_vocab_size(), "d_model": 16, "n_heads": 2, "n_layers": 1,
              "d_ff": 32, "max_seq_len": 32, "dropout": 0.0}
    model = GeriTransformer(config).eval()
    checkpoint = tmp_path / "promoted-sft.pt"
    torch.save({"model": model.state_dict(), "config": {"model": config},
                "pretraining_metadata": {"manifest_sha256": manifests[0][1]},
                "sft_metadata": {"manifest_sha256": manifests[1][1]}}, checkpoint)
    checkpoint.with_suffix(".pt.sha256").write_text(hashlib.sha256(checkpoint.read_bytes()).hexdigest(), encoding="ascii")
    return checkpoint, tokenizer_path, manifests


def test_sft_prompt_serialization_is_exact():
    assert serialize_history([{"role": "user", "content": " hola "},
                              {"role": "assistant", "content": "Buenos días"}]) == "<|user|>\nhola\n<|assistant|>\nBuenos días\n"


def test_sampling_filters_and_parameter_validation():
    logits = torch.tensor([4.0, 3.0, 2.0, 1.0])
    filtered = _filter_logits(logits, 1.0, 2, 1.0)
    assert torch.isfinite(filtered).sum().item() == 2
    greedy = _filter_logits(logits, 0.0, 0, 1.0)
    assert torch.equal(greedy, logits)
    with pytest.raises(ValueError):
        _filter_logits(logits, 1.0, 0, 0.0)


def test_load_generate_cpu_and_preserve_checkpoint_bytes(tmp_path):
    checkpoint, tokenizer_path, manifests = _write_approved_fixture(tmp_path)
    before = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    model, tokenizer = load_promoted_model(checkpoint, tokenizer_path, manifests[0][0], manifests[1][0])
    result = generate(model, tokenizer, [{"role": "user", "content": "hola"}],
                      temperature=0, top_k=0, top_p=1, max_new_tokens=3)
    assert model.training is False
    assert len(result["text"]) >= 0
    assert result["tokens"] <= 3 and result["seconds"] > 0 and result["tokens_per_second"] >= 0
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest() == before


def test_loader_rejects_changed_manifest_or_checkpoint(tmp_path):
    checkpoint, tokenizer_path, manifests = _write_approved_fixture(tmp_path)
    manifests[0][0].write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        load_promoted_model(checkpoint, tokenizer_path, manifests[0][0], manifests[1][0])
    checkpoint.with_suffix(".pt.sha256").write_text("invalid", encoding="ascii")
    with pytest.raises(ValueError, match="checkpoint integrity"):
        load_promoted_model(checkpoint, tokenizer_path, tmp_path / "pretraining.json", manifests[1][0])


def test_inference_respects_offline_guard(tmp_path):
    import socket

    from geri.training.offline import offline_execution

    with offline_execution(), pytest.raises(RuntimeError, match="network access is disabled"):
        socket.create_connection(("example.invalid", 443), timeout=0.1)
