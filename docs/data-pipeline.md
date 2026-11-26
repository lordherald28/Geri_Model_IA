# Corpus preparation and tokenization

## Source decisions (2026-11-25)

The corpus combines three source groups. Exact URLs, selection metadata, licensing terms, per-document update dates, and acquired-file hashes are recorded in `configs/sources.json` and the external corpus manifest.

| Source | Scope | Terms and review limits |
|---|---|---|
| COST ELTeC-spa v0.9.1, 22 novels | Historical literary Spanish | Text stated as public domain; TEI markup/metadata CC BY 4.0. Transcription rights/quality and historical personal names need human review. Pinned Git revision `6c0160ea2524cead72904b11992959748434aa57`. |
| AEBOE consolidated API, 4 statutes | Education, public administration, science/technology, climate/energy | AEBOE standard reuse terms allow commercial/non-commercial reuse, extraction, adaptation and combination, subject to attribution, preserving meaning, date and an explicit informational-only consolidated-text notice. The API reported `Finalizado` at acquisition; snapshots retain `fecha_actualizacion`. Legal accuracy/current effect requires human review. |
| CORDIS, 3 Results/Results in Brief articles | Life sciences and AI, water management, biodiversity | EU-owned editorial content defaults to CC BY 4.0; text only, no third-party images. CORDIS says Results in Brief are written by scientific authors with project participants and, where needed, a Commission project officer. Spanish pages are machine translations by Commission eTranslation; factual claims and named public coordinators require human review. |

CC BY-SA sources are excluded per user direction, including Wikipedia/CEDEC material and the mixed NOS_Científico package. The CSIC Spanish Corpus was excluded: its README states CC BY-NC-SA 4.0 and says it was not anonymized, despite the dataset record's conflicting license metadata. Common Crawl/OSCAR-derived and other mixed-license sets were excluded when rights could not be established at document level. Geri v1 data, tokenizers and weights were not reused.

This is a technical license/provenance assessment, not a legal opinion about distributing model weights. Review the obligations again before any model release.

## Pipeline and reproducibility

Install with `python -m pip install -e ".[dev]"`. The CLI defaults to `C:\geri2-corpus`; pass `--output` explicitly to select another volume. Raw source snapshots, processed splits, manifests and tokenizer artifacts stay outside Git. The project remains in its existing D: checkout; no project or user files were moved or deleted.

```powershell
geri-data prepare --offline --output C:\geri2-corpus
geri-data validate --output C:\geri2-corpus
geri-data tokenizer --output C:\geri2-corpus
geri-data offline-check --output C:\geri2-corpus
```

The source adapters acquire fixed ELTeC XML, consolidated BOE XML and selected CORDIS HTML. BOE extraction keeps the most recent version per text block. CORDIS extraction keeps article headings, teaser and editorial paragraphs, excluding navigation, project contacts and images. Normalization applies HTML entity decoding, removes BOM/soft hyphen, NFC and whitespace collapse; segmentation is deterministic. Quality filters log too-short text, long text, URLs, controls/replacement characters and low letter ratio. Deduplication is case-insensitive at normalized sentence level; duplicate provenance is retained. Documents are split before sentence use and never cross partitions; splits are stratified within each source group.

The manifest records source URLs, terms, dates/statuses, hashes, row counts, split/document hashes, theme distribution, quality findings and resource preflight. The PII screen checks email, Spanish DNI/NIE and common phone formats; it is not a named-entity or contextual privacy detector. An offline check blocks the pipeline's network entry points, verifies original source snapshot and processed corpus hashes, and loads/encodes with the frozen tokenizer.

## Measured corpus

Prepared from locally cached snapshots on 2026-11-25; the reproducibility rerun used `--offline` and downloaded 0 bytes.

| Split | Rows | Documents | BPE tokens (2,048) | Characters | Whitespace words |
|---|---:|---:|---:|---:|---:|
| Train | 34,117 | 22 | 1,883,060 | 5,931,900 | 1,040,842 |
| Validation | 9,156 | 3 | 563,753 | 1,707,724 | 291,862 |
| Test | 5,675 | 4 | 402,290 | 1,227,115 | 204,494 |
| **Total** | **48,948** | **29** | **2,849,103** | **8,866,739** | **1,537,198** |

There are 119,303 distinct case-folded whitespace-delimited word forms across the corpus (type/token ratio 0.0776). By prepared rows, historical ELTeC novels supply 44,271 (90.45%), BOE 4,602 (9.40%), and CORDIS 75 (0.15%). By BPE tokens they supply 2,473,714 (86.83%), 369,590 (12.97%), and 5,799 (0.20%) respectively. The added scientific/technical source is useful for pipeline coverage but far too small to balance the corpus; contemporary general Spanish, broad education and technical/scientific prose remain underrepresented.

Input contained 112,034 sentence candidates. The pipeline accepted 48,948, removed 53 exact duplicates, and rejected 63,033 for length and 2,130 for letter ratio (reason counts can overlap). The pattern screen found 0 email, 0 phone and 0 DNI/NIE matches. The articles do include public project coordinator names; contextual/name review remains pending. ELTeC also needs human review for transcription quality, rights of individual transcriptions and historical personal names. BOE excerpts are informational consolidated legal texts, not authoritative legal advice; reviewers should confirm update state and avoid claims that they are official versions.

## Tokenizer measurement

Byte-level BPE was trained only on 22 train documents and measured on all 9,156 validation rows across 3 documents. Test was excluded from selection. Row-level train/validation measurements:

| Vocabulary | Train tokens | Train chars/token | Validation tokens | Validation tokens/char |
|---:|---:|---:|---:|---:|
| 256 | 3,230,232 | 1.84 | 941,636 | 0.55140 |
| 512 | 2,574,051 | 2.30 | 754,043 | 0.44155 |
| 1,024 | 2,179,376 | 2.72 | 642,893 | 0.37646 |
| 2,048 | 1,883,060 | 3.15 | 563,753 | 0.33012 |

The selected vocabulary remains 2,048, the best among tested candidates. It yields 3.15 characters per token on training text. The four-candidate CPU run took 29.374 seconds against a 600-second ceiling. Validation is source-stratified but small (one document per source), so these are tokenizer compression measurements, not broad linguistic generalization evidence. The test set was not used to select the vocabulary.

## Resources and operating limits

The project was left on D: and artifacts on C:, without moving/deleting files. At the latest run preflight, C: had about 192.4 GiB free, D: about 43.4 GiB free and available physical RAM was 11.6 GiB; the machine reports a Ryzen 5 7530U (6 cores/12 threads) and 31.35 GiB RAM. Pipeline limits: 2.5 MB per downloaded file, 25 MB total source-download budget, 200 MB total artifact cap, 1 GiB free-space reserve, 4 GiB minimum available RAM, 5,000 tokenizer training documents, four BPE candidates and a 600-second CPU-time limit. The current C: corpus occupies 68,718,729 bytes; its raw snapshots total 14,127,903 bytes. Tokenizer fitting is CPU-only and used 22 documents; no GPU or model training is involved.

These limits leave roughly 2.9x headroom over present artifacts and 1.8x over a complete source-snapshot acquisition. The runtime guard rejects insufficient RAM/disk, and final artifact size is checked against its cap. The source budget prevents accidentally fetching large dumps. Current workspace measurements should be repeated before any corpus expansion because free space and RAM availability can change.

## Validation results and remaining review

- Focused tests: 7 passed, including latest BOE version extraction, CORDIS article-only extraction, PII-pattern detection and disk/RAM guard behavior.
- Corpus validation: passed; 48,948 unique accepted rows, 29 source documents, disjoint document splits and verified processed-file hashes.
- Offline verification: passed with network entry points blocked; corpus files and tokenizer loaded locally.
- Source acquisition: 7 additional source snapshots fetched within limits; subsequent offline rebuild downloaded 0 bytes.
- No Geri v1 files, checkpoints or weights were modified or reused; model training was not run.
- Human review still needed for ELTeC transcription rights/quality and personal names; BOE legal update/interpretation; CORDIS machine-translation quality, factual claims and named public coordinators. Broad contemporary Spanish and a larger education/general-knowledge corpus remain open coverage gaps.
- Current review aid: `C:\geri2-corpus\review\human_review_sample.jsonl`, 29 deterministic source/document examples (22 ELTeC works, 4 BOE texts, 3 CORDIS articles); SHA-256 and pending decision list are recorded in the external corpus manifest. The full corpus scan found no replacement characters or common-pattern PII; neither scan resolves names, contextual identifiers, transcription rights or factual/legal accuracy.

Generated exact counts, per-domain/per-split measurements, source hashes and tokenizer SHA-256 are in the external files `C:\geri2-corpus\processed\manifest.json` and `C:\geri2-corpus\tokenizer\metrics.json`.
