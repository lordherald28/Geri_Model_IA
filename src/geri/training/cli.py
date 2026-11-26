"""Manual entry point for offline local training and benchmarks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .offline import offline_execution
from .sft_prepare import prepare_sft


def _require_private_experimental_scope(manifest: dict, dataset_name: str) -> None:
    scope = manifest.get("authorization_scope", {})
    if scope.get("purpose") != "experimental_private_training_only":
        raise SystemExit(f"{dataset_name} approval is not scoped to experimental private training")
    if scope.get("network_during_training") is not False:
        raise SystemExit(f"{dataset_name} approval does not require offline training")
    if scope.get("corpus_distribution_authorized") is not False or scope.get("model_weight_distribution_authorized") is not False:
        raise SystemExit(f"{dataset_name} approval unexpectedly permits distribution")
    if scope.get("factuality_certified") is not False:
        raise SystemExit(f"{dataset_name} approval must not claim factuality certification")


def main() -> None:
    parser = argparse.ArgumentParser(prog="geri-train", description="Geri 2.0 offline manual training engine")
    parser.add_argument("command", choices=["benchmark", "train", "smoke", "prepare-sft", "preflight"])
    parser.add_argument("--config", type=Path, default=Path("configs/training.json"))
    parser.add_argument("--data", type=Path, default=Path("C:/Geriv2-Data/corpus/pretraining"))
    parser.add_argument("--tokenizer", type=Path, default=Path("C:/Geriv2-Data/corpus/pretraining/tokenizer/tokenizer.json"))
    parser.add_argument("--sft-data", type=Path)
    parser.add_argument("--sft-tokenizer", type=Path)
    parser.add_argument("--input", type=Path, help="source conversation JSONL for prepare-sft")
    parser.add_argument("--sources", type=Path, help="source/license registry for prepare-sft")
    parser.add_argument("--output", type=Path, default=Path("C:/Geriv2-Data/training/runs"))
    parser.add_argument("--steps", type=int, default=5, help="synthetic smoke steps")
    parser.add_argument("--benchmark-steps", type=int, default=20)
    parser.add_argument("--benchmark-repeats", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--authorize-pretraining", action="store_true")
    parser.add_argument("--authorize-sft", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.command == "prepare-sft":
        if not args.input or not args.sources:
            raise SystemExit("prepare-sft requires --input and --sources")
        with offline_execution():
            manifest = prepare_sft(args.input, args.sources, args.data, args.tokenizer, int(config["seed"]))
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return
    if args.command == "preflight":
        if not args.sft_data or not args.sft_tokenizer:
            raise SystemExit("preflight requires approved pretraining and SFT data plus both tokenizer paths")
        import hashlib
        import time

        import torch
        from tokenizers import Tokenizer

        from .data import load_frozen_corpus, load_sft_corpus
        from .engine import preflight
        from geri.model.transformer import GeriTransformer

        context = int(config["model"]["max_seq_len"])
        tokenizer = Tokenizer.from_file(str(args.tokenizer))
        actual_vocab = tokenizer.get_vocab_size()
        expected_vocab = int(config["model"]["vocab_size"])
        if actual_vocab != expected_vocab:
            raise SystemExit(f"model vocab_size {expected_vocab} does not match tokenizer vocabulary {actual_vocab}")
        if args.sft_tokenizer.read_bytes() != args.tokenizer.read_bytes():
            raise SystemExit("SFT and pretraining must use identical tokenizer bytes in this engine version")
        started = time.perf_counter()
        with offline_execution():
            pre_manifest = json.loads((args.data / "processed" / "manifest.json").read_text(encoding="utf-8"))
            sft_manifest = json.loads((args.sft_data / "processed" / "manifest.json").read_text(encoding="utf-8"))
            _require_private_experimental_scope(pre_manifest, "pretraining")
            _require_private_experimental_scope(sft_manifest, "SFT")
            preflight_resources = preflight(config, args.output, torch.device(config.get("device", "cpu")))
            pre_splits, _ = load_frozen_corpus(args.data, args.tokenizer, block_size=context)
            sft_splits, _ = load_sft_corpus(args.sft_data, args.sft_tokenizer, context)
            model = GeriTransformer(config["model"]).eval()
            probe = torch.zeros((1, context), dtype=torch.long)
            with torch.no_grad():
                logits = model(probe)
            expected_shape = (1, context, expected_vocab)
            if tuple(logits.shape) != expected_shape:
                raise SystemExit(f"model output shape {tuple(logits.shape)} does not match expected {expected_shape}")
        report = {
            "valid": True,
            "training_started": False,
            "optimizer_created": False,
            "checkpoint_written": False,
            "network_guard": "enabled during preflight; launcher also verifies frozen snapshots offline",
            "model": {"context": context, "vocab_size": expected_vocab, "parameters": model.parameter_count(), "probe_logits_shape": list(logits.shape)},
            "pretraining": {"manifest_sha256": hashlib.sha256((args.data / "processed" / "manifest.json").read_bytes()).hexdigest(), "rows": pre_manifest["counts"]["accepted"], "train_windows": len(pre_splits["train"]), "context": context},
            "sft": {"manifest_sha256": hashlib.sha256((args.sft_data / "processed" / "manifest.json").read_bytes()).hexdigest(), "conversations": sft_manifest["quality_screen"]["conversations"], "train_conversations": len(sft_splits["train"]), "context": context},
            "tokenizer_sha256": hashlib.sha256(args.tokenizer.read_bytes()).hexdigest(),
            "authorization_scope": "experimental_private_training_only; no corpus/model-weight distribution; no factuality certification",
            "resources": preflight_resources,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        report_path = args.output / "startup-preflight.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({**report, "report_path": str(report_path)}, ensure_ascii=False, indent=2))
        return
    if args.command == "benchmark":
        from .benchmark import run_benchmark

        with offline_execution():
            result = run_benchmark(config, args.output, args.benchmark_steps, args.benchmark_repeats)
        print(json.dumps(result, indent=2))
        return
    if args.command == "smoke":
        from .data import create_synthetic_smoke_data, load_frozen_corpus
        from .engine import run_phase
        from geri.model.transformer import GeriTransformer

        with offline_execution():
            create_synthetic_smoke_data(args.data, args.tokenizer, int(config["seed"]))
        if not args.authorize_pretraining:
            raise SystemExit("synthetic smoke created. Re-run with --authorize-pretraining to execute limited synthetic training")
        smoke = json.loads(json.dumps(config))
        smoke["model"]["vocab_size"] = max(256, smoke["model"]["vocab_size"])
        smoke["model"]["max_seq_len"] = min(32, smoke["model"]["max_seq_len"])
        smoke["pretraining"].update({"max_steps": args.steps, "eval_interval": max(1, args.steps), "patience_evaluations": 2})
        with offline_execution():
            datasets, manifest = load_frozen_corpus(args.data, args.tokenizer, allow_synthetic=True, block_size=smoke["model"]["max_seq_len"])
        smoke["pretraining"]["batch_size"] = min(2, smoke["pretraining"]["batch_size"])
        model = GeriTransformer(smoke["model"])
        with offline_execution():
            result = run_phase("smoke", model, datasets["train"], datasets["validation"], smoke["pretraining"], smoke, args.output,
                               {"dataset_status": manifest["dataset_status"]})
        print(json.dumps(result, indent=2))
        return
    if not args.authorize_pretraining:
        raise SystemExit("pretraining requires --authorize-pretraining")
    if not args.sft_data or not args.sft_tokenizer:
        raise SystemExit("training requires a separate approved SFT dataset and tokenizer (--sft-data, --sft-tokenizer)")
    if not args.authorize_sft:
        raise SystemExit("SFT requires --authorize-sft; this is separate from pretraining authorization")
    from .data import load_frozen_corpus, load_sft_corpus
    from .engine import train

    model_context = int(config["model"]["max_seq_len"])
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(args.tokenizer))
    if tokenizer.get_vocab_size() != int(config["model"]["vocab_size"]):
        raise SystemExit("model vocab_size does not match the frozen tokenizer vocabulary")
    with offline_execution():
        datasets, manifest = load_frozen_corpus(args.data, args.tokenizer, block_size=model_context)
    if manifest.get("dataset_status") != "approved_for_training":
        raise SystemExit("pretraining blocked: corpus has not passed human review and approval")
    _require_private_experimental_scope(manifest, "pretraining")
    import hashlib
    pre_metadata = {"manifest_sha256": hashlib.sha256((args.data / "processed" / "manifest.json").read_bytes()).hexdigest(), "dataset_status": manifest["dataset_status"]}
    with offline_execution():
        sft_splits, sft_manifest = load_sft_corpus(args.sft_data, args.sft_tokenizer, model_context)
    _require_private_experimental_scope(sft_manifest, "SFT")
    if args.sft_tokenizer.read_bytes() != args.tokenizer.read_bytes():
        raise SystemExit("SFT and pretraining must use identical tokenizer bytes in this engine version")
    datasets.update({"sft_train": sft_splits["train"], "sft_validation": sft_splits["validation"], "sft_test": sft_splits["test"],
                     "sft_metadata": {"manifest_sha256": hashlib.sha256((args.sft_data / "processed" / "manifest.json").read_bytes()).hexdigest(), "dataset_status": sft_manifest["dataset_status"]}})
    with offline_execution():
        result = train(config, datasets, args.output, pre_metadata, args.resume)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
