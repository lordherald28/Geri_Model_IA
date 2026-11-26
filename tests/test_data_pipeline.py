import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from geri.data.pipeline import _check_capacity, normalize, quality_reasons, sha256, validate


def test_normalization_is_unicode_nfc_and_collapses_space():
    assert normalize("  Cafe\u0301\u00ad  &amp;\n té ") == "Café & té"


def test_quality_filter_flags_short_url_and_low_letter_ratio():
    assert "too_short" in quality_reasons("hola", 20, 100)
    assert "url_or_boilerplate" in quality_reasons("Este texto contiene una URL https://example.org", 10, 100)
    assert "low_letter_ratio" in quality_reasons("1234 !!! ???", 1, 100)


def test_validator_checks_hashes_and_split_membership(tmp_path: Path):
    processed = tmp_path / "processed"
    processed.mkdir()
    artifacts = {}
    for split, document in (("train", "doc-a"), ("validation", "doc-b"), ("test", "doc-c")):
        path = processed / f"{split}.jsonl"
        row = {"text": f"Texto válido y largo para {split}", "document_hash": document, "split": split, "license": "CC0-1.0", "url": "https://example.test"}
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        artifacts[path.name] = {"sha256": sha256(path)}
    (processed / "manifest.json").write_text(json.dumps({"artifacts": artifacts}), encoding="utf-8")
    assert validate(tmp_path)["valid"]
    with (processed / "train.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate(tmp_path)


def test_capacity_guard_preserves_configured_reserve(tmp_path: Path, monkeypatch):
    config = {"min_free_disk_bytes": 1000, "max_pipeline_storage_bytes": 200}
    monkeypatch.setattr("geri.data.pipeline.shutil.disk_usage", lambda _: SimpleNamespace(free=1199))
    with pytest.raises(OSError, match="need at least 1200"):
        _check_capacity(tmp_path / "output", config)
    monkeypatch.setattr("geri.data.pipeline.shutil.disk_usage", lambda _: SimpleNamespace(free=1200))
    _check_capacity(tmp_path / "output", config)
