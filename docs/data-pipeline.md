# Corpus preparation and tokenization

## Source decisions

The initial reproducible corpus uses 22 explicitly listed Spanish ELTeC-spa v0.9.1 XML novels. The collection states that all included texts are public domain and that the textual markup is CC BY 4.0. Provenance, collection/editor attribution and a link to the license are carried into every example and the manifest. The upstream release and collection are pinned in `configs/sources.json`; the exact acquired file hashes are in the generated manifest. ELTeC is historical literary Spanish and is not representative of contemporary regional usage. Transcription quality varies; factuality and personal data have not had human review. This corpus is suitable for a technical pipeline demonstration, not a claim of comprehensive legal or linguistic clearance.

The v1 inventory was read-only audited. We did not copy prepared/segmented files, teacher reviewed examples, Tatoeba, or Wikimedia rows. Teacher reviewed examples lack individual provenance. The Tatoeba CC0 download contains only part of its sentences; the v1 source dump is about 41.9 MB, above this pipeline's 25 MB total-download cap, and cannot be treated as CC0 wholesale without row-level license checks. Wikimedia's CC BY-SA attribution/share-alike obligations require a separate distribution review. Two ELTeC paths in the v1 selected-document inventory are absent from pinned v0.9.1 and were excluded. Other selected novels were reacquired from the pinned primary source rather than copied from v1.

The selection contains copyright-sensitive dataset facts (release, file-level provenance, attribution and hashes); do not remove row-level attribution when exporting or redistributing. This is a technical compatibility assessment, not legal advice.

## Pipeline

Install with `python -m pip install -e ".[dev]"`. Data are written under `data/` by default; pass `--output` to place them elsewhere. Configure a maximum per-source-file and aggregate download budget in `configs/data-pipeline.json`. Acquisition uses atomic `.part` files, checks `Content-Length` and streamed size, and reuses cached source files. `--offline` fails if any pinned source snapshot is missing.

```powershell
geri-data prepare --source eltec_spa_v0.9.1 --output C:\geri2-corpus
geri-data validate --output C:\geri2-corpus
geri-data tokenizer --output C:\geri2-corpus
geri-data offline-check --output C:\geri2-corpus
```

Preparation decodes HTML entities, removes BOM/soft hyphen, applies Unicode NFC and collapses whitespace. It extracts TEI paragraph/head/line text, splits sentences deterministically, filters lengths, URLs, control/replacement characters and low alphabetic ratios, and deduplicates case-insensitive normalized text. It records reject counts and text/document hashes. Documents are assigned whole to train/validation/test using seed 20261125; there is no sentence-level split across a novel. The validator checks artifact hashes, required provenance, split membership, document isolation and cross-split exact duplicates.

The byte-level BPE is trained on all accepted training sentences grouped by training document. It is not loaded from Geri v1. Candidate vocabularies 256, 512, 1024 and 2048 are measured; selection uses lowest validation tokens per character. Test is never used for tokenizer selection. The generated tokenizer and metrics are self-contained; offline-check blocks network entry points and exercises loading/encoding from the frozen test artifact.

## Measured run (2026-11-25)

Output was kept outside Git on C: because D: had approximately 96 MiB free. The 22 pinned XML snapshots occupied 11,360,637 bytes. The generated processed corpus occupies 38,038,110 bytes, plus tokenizer artifacts. Input was 102,900 sentence candidates; 44,271 were accepted and 15 exact duplicates removed. Rejection reason counts were 58,614 too short and 257 with low letter ratio; reason counts can overlap. The split contains 32,503 train rows (19 novels), 7,978 validation rows (1 novel), and 3,790 test rows (2 novels). The small number of validation/test documents makes these measurements noisy and strongly domain-specific.

| Vocabulary | Actual size | Train chars/token | Validation tokens/char |
|---:|---:|---:|---:|
| 256 | 256 | 1.84 | 0.549 |
| 512 | 512 | 2.29 | 0.438 |
| 1024 | 1024 | 2.71 | 0.373 |
| 2048 | 2048 | 3.12 | 0.328 |

The measured selection is 2048 tokens; this is a measurement-based choice among the configured candidates, not a claim that it is optimal for a larger or more varied corpus. Full counts, configuration, license/provenance, per-file hashes, output hashes, and tokenization measurements are in generated `processed/manifest.json` and `tokenizer/metrics.json`.

## Validation and limits

- Focused automated tests: `3 passed`.
- Corpus validation: passed, 44,271 unique text rows across 22 documents; all three outputs matched their recorded SHA-256 values and document splits were disjoint.
- Offline check: passed with network access blocked; all corpus hashes verified and tokenizer loaded and encoded a test row (157 tokens).
- No model training, weights, checkpoints, or Geri v1 files were used or changed.
- Automatic checks do not establish factual correctness, human reading quality, PII absence, license ownership of every underlying public-domain transcription, or broad Spanish coverage. Review these before expanding or distributing a trained model. Test/test leakage checks cover exact normalized duplicates; fuzzy cross-source contamination requires additional sources and review.

## Commands

Run tests from the repository root with `python -m pytest -q`. To reproduce from already acquired files without network, run `geri-data prepare --source eltec_spa_v0.9.1 --offline --output C:\geri2-corpus`, followed by validate, tokenizer, and offline-check. The tokenizer vocabulary is selected by validation compression, so the configuration and exact corpus snapshot must remain fixed for a reproducible result.
