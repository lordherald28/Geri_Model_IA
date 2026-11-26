"""CPU/RAM/tokens-per-second measurements using synthetic next-token batches."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import torch
from torch import nn

from geri.model.transformer import GeriTransformer
from .engine import preflight, _process_rss_bytes


def run_benchmark(base_config: dict, output: Path, steps: int = 20, repeats: int = 3) -> dict:
    if steps < 2 or repeats < 1:
        raise ValueError("benchmark requires steps >= 2 and repeats >= 1")
    if base_config.get("device", "cpu") != "cpu":
        raise ValueError("dimensioning benchmark currently measures CPU only")
    output.mkdir(parents=True, exist_ok=True)
    candidates = [
        {"name": "tiny", "d_model": 64, "n_heads": 2, "n_layers": 2, "d_ff": 256, "max_seq_len": int(base_config["model"]["max_seq_len"]), "batch_size": 4},
        {"name": "small", "d_model": 128, "n_heads": 4, "n_layers": 4, "d_ff": 512, "max_seq_len": int(base_config["model"]["max_seq_len"]), "batch_size": 4},
        {"name": "medium", "d_model": 192, "n_heads": 6, "n_layers": 4, "d_ff": 768, "max_seq_len": int(base_config["model"]["max_seq_len"]), "batch_size": 4},
    ]
    trial = json.loads(json.dumps(base_config))
    trial["resources"]["min_free_disk_bytes"] = 0
    trial["resources"]["min_available_memory_bytes"] = 0
    pre = preflight(trial, output, torch.device("cpu"))
    torch.set_num_threads(int(base_config.get("num_threads", 1)))
    records = []
    for candidate in candidates:
        model_config = {**base_config["model"], **{k: v for k, v in candidate.items() if k != "name"}}
        repeats_result = []
        model = None
        for repeat in range(repeats):
            torch.manual_seed(int(base_config["seed"]) + repeat)
            model = GeriTransformer(model_config)
            optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
            tokens = torch.randint(0, model_config["vocab_size"], (candidate["batch_size"], model_config["max_seq_len"] + 1))
            inputs, targets = tokens[:, :-1], tokens[:, 1:]
            elapsed, count = 0.0, 0
            baseline_rss = _process_rss_bytes()
            peak_rss = baseline_rss
            for index in range(steps + 2):
                start = time.perf_counter()
                optimizer.zero_grad(set_to_none=True)
                loss = nn.functional.cross_entropy(model(inputs).reshape(-1, model_config["vocab_size"]), targets.reshape(-1))
                loss.backward()
                optimizer.step()
                duration = time.perf_counter() - start
                if index >= 2:
                    elapsed += duration
                    count += 1
                rss = _process_rss_bytes()
                if rss is not None:
                    peak_rss = max(peak_rss or 0, rss)
            checkpoint = output / f"benchmark-{candidate['name']}-{repeat}.tmp.pt"
            torch.save({"model": model.state_dict(), "optimizer": optimizer.state_dict()}, checkpoint)
            checkpoint_bytes = checkpoint.stat().st_size
            checkpoint.unlink()
            tokens_per_step = candidate["batch_size"] * model_config["max_seq_len"]
            repeats_result.append({"tokens_per_second": tokens_per_step * count / max(elapsed, 1e-9),
                                  "step_seconds": elapsed / count, "rss_baseline_bytes": baseline_rss,
                                  "rss_peak_bytes": peak_rss, "checkpoint_bytes": checkpoint_bytes})
        records.append({"candidate": candidate["name"], "config": model_config, "batch_size": candidate["batch_size"],
                        "parameters": model.parameter_count(), "repeats": repeats_result,
                        "tokens_per_second_mean": sum(r["tokens_per_second"] for r in repeats_result) / repeats,
                        "tokens_per_second_min": min(r["tokens_per_second"] for r in repeats_result),
                        "step_seconds_mean": sum(r["step_seconds"] for r in repeats_result) / repeats,
                        "process_rss_peak_observed_bytes": max((r["rss_peak_bytes"] or 0 for r in repeats_result), default=0) or None,
                        "checkpoint_bytes": repeats_result[-1]["checkpoint_bytes"], "preflight": pre})
    result = {"benchmark": "synthetic CPU only; excludes corpus loading/tokenization and is not product quality evidence",
              "python": os.sys.version, "torch": torch.__version__, "cpu_count": os.cpu_count(),
              "steps_per_repeat": steps, "repeat_count": repeats,
              "ram_measurement": "process RSS sampled via psutil or Windows GetProcessMemoryInfo",
              "candidates": records,
              "fastest_candidate_by_tokens_per_second": max(records, key=lambda row: row["tokens_per_second_mean"])["candidate"],
              "selection_criteria": "throughput is reported, not used as a model-quality or capacity decision"}
    (output / "model-benchmark.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
