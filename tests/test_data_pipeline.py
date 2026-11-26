import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from geri.data.pipeline import _boe_latest_text, _check_capacity, _cordis_text, _merge_duplicate_provenance, normalize, pii_findings, quality_reasons, sha256, validate


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


def test_capacity_guard_enforces_available_ram(tmp_path: Path, monkeypatch):
    config = {"min_free_disk_bytes": 0, "max_pipeline_storage_bytes": 0, "min_available_memory_bytes": 1000}
    monkeypatch.setattr("geri.data.pipeline._available_memory_bytes", lambda: 999)
    with pytest.raises(OSError, match="insufficient available RAM"):
        _check_capacity(tmp_path / "output", config)


def test_boe_extractor_keeps_latest_version_per_block(tmp_path: Path):
    path = tmp_path / "law.xml"
    path.write_text("""<response><data><texto><bloque id='a'>
      <version fecha_publicacion='20200101'><p>Texto anterior vigente.</p></version>
      <version fecha_publicacion='20240101'><p>Texto consolidado actual.</p></version>
    </bloque></texto></data></response>""", encoding="utf-8")
    assert _boe_latest_text(path) == "Texto consolidado actual."


def test_cordis_extractor_keeps_article_body_and_discards_page_chrome(tmp_path: Path):
    path = tmp_path / "article.html"
    path.write_text("""<main id='c-main'><h1>Título científico</h1>
      <p class='c-teaser'>Resumen editorial.</p>
      <p class='c-article__text'>Texto con <b>formato</b>.</p>
      <footer>Enlaces y navegación ignorados.</footer></main>""", encoding="utf-8")
    assert _cordis_text(path) == "Título científico\nResumen editorial.\nTexto con formato."


def test_pii_pattern_screen_detects_contact_identifiers():
    assert set(pii_findings("Escribe a persona@example.org o llama al +34 612 345 678; DNI 12345678Z")) == {"email", "phone", "dni_nie"}


def test_duplicate_merge_keeps_secondary_provenance_once():
    primary = {"text": "frase", "source": "one", "source_id": "a", "license": "CC BY 4.0", "url": "https://example.org/a"}
    duplicate = {"text": "frase", "source": "two", "source_id": "b", "license": "CC0-1.0", "url": "https://example.org/b"}
    _merge_duplicate_provenance(primary, duplicate)
    _merge_duplicate_provenance(primary, duplicate)
    assert len(primary["additional_provenance"]) == 1
    assert primary["additional_provenance"][0]["source"] == "two"
