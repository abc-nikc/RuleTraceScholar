# RuleTrace Scholar Acceptance Report

Acceptance date: 2026-09-29 (Asia/Shanghai)

This report records a real end-to-end run of the local Docker deployment. It
demonstrates that the implemented pipeline works on the tested environment; it
does not claim that every future LLM answer is semantically correct.

## Acceptance source

- Paper: *Explainable Innovation Engine: Dual-Tree Agent-RAG with
  Methods-as-Nodes and Verifiable Write-Back*
- Author: Renwei Meng
- Source: [arXiv:2603.09192](https://arxiv.org/abs/2603.09192)
- DOI: [10.48550/arXiv.2603.09192](https://doi.org/10.48550/arXiv.2603.09192)
- arXiv submission date: 2026-03-10
- Local acceptance copy: `resource/acceptance/arxiv-2603.09192.pdf`
- PDF size: 12,135,709 bytes; 15 pages
- SHA-256: `D3D1880033DD6EE1F6AF47D6526B5115372C3AC55E9BCB08BA77B7140E88F48D`

The paper was selected because it is recent, directly concerns Agent-RAG and
explainability, and has a stable arXiv identifier and DOI. It is a preprint, so
its presence here is an integration test source rather than an endorsement or
peer-review claim.

## Verified deployment

| Component | Verified configuration |
|---|---|
| Frontend | React/Vite production build on `http://127.0.0.1:5173` |
| Backend | FastAPI on `http://127.0.0.1:8000` |
| LLM | Ollama OpenAI-compatible endpoint, `qwen3:8b` |
| Metadata | PostgreSQL 16 |
| Vector database | Milvus 2.6.24 standalone |
| Dense retrieval | BAAI/bge-small-en-v1.5, HNSW/COSINE |
| Sparse retrieval | Milvus BM25 function, SPARSE_INVERTED_INDEX/BM25 |
| Reranking | BAAI/bge-reranker-v2-m3 after RRF fusion |
| PDF runtime | Docling, PyMuPDF, OpenCV headless 5.0.0 |

The Docker image verifies the vendored OpenCV headless wheel against the
official SHA-256 before installation. Milvus is pinned to 2.6.24 and explicitly
uses `DEPLOY_MODE=STANDALONE`, which is required when embedded etcd is enabled.

## End-to-end results

1. The API accepted the real PDF with HTTP 200 and reported 15 pages and 280
   child chunks.
2. Direct database queries found 280 child rows and 236 parent rows (536 total).
3. Both collections expose a dense HNSW/COSINE index and a sparse
   SPARSE_INVERTED_INDEX/BM25 index.
4. A paper-scoped Agent request completed without an error event. It decomposed
   the question into three sub-queries, retrieved five results for each, emitted
   a 1,906-character answer, and returned 15 evidence records. Every evidence
   record belonged to `Explainable_Innovation_Engine_2026`; observed pages were
   3, 11, 12, 13, and 15.
5. The stream emitted `citations`, `explanation`, `claim_tests`, `capsule`, and
   `done`. The saved capsule ID was
   `214347bb-4bfd-4e69-ae07-72883ec568c2`, with SHA-256
   `d09d830b850e4ca54397306e8fa4448c1cc8eb3543124616a269543b4d9be23a`.
6. Capsule listing, capsule replay, and conversation-history APIs returned the
   saved explanation and claim-test data after the response finished.
7. Milvus and the backend were restarted. The file record, 280 child rows, 236
   parent rows, and capsule hash remained available after restart.

## Explainability outcome

The acceptance answer was deliberately evaluated rather than automatically
labelled correct. TRACE returned `caution`, an uncalibrated evidence-quality
index of 0.5882, perfect citation validity and source traceability, but only
0.4545 claim citation coverage. The deterministic claim tests therefore
reported six passes and six failures for uncited factual claims.

This is expected guard behaviour: the system surfaces insufficiently grounded
parts instead of presenting an opaque confidence score. The index is not a
probability of truth, and a valid citation can still be misinterpreted.

## Automated checks

- Full backend test discovery after the final build: 26/26 passed, including
  discovery parsing and input validation, Milvus retrieval regressions,
  TRACE, verified evidence repair, semantic audit, replay persistence, and
  inspection-filter escaping. The added regression tests cover source-paper
  bibliography extraction and related-result explanations.
- Frontend ESLint: passed.
- Frontend Vite production build: passed (1,909 modules transformed).
- Docker services after final restart: frontend running, backend running,
  PostgreSQL healthy, Milvus healthy.

## Final evidence-governance acceptance

A second paper-scoped request asked for the core architecture, experimental
results, and acknowledged limitations. The graph classified the request,
generated four sub-queries, triggered one reflection/retrieval retry, and
returned 20 citations. The post-generation pipeline emitted, in order,
`citations`, `explanation`, `claim_tests`, `repair`, `capsule`, and `done`.

- TRACE: `supported`, score 0.7484, 25 extracted claims.
- Deterministic checks: 12 pass, 4 warning, 3 fail, 7 untestable.
- Semantic review: 5 entailed, 5 insufficient, 0 contradicted, 0 conflicts;
  therefore the answer remains reviewable rather than silently trusted.
- Replay capsule: `aa6d6129-e151-430e-b8a6-61310996c107`, SHA-256
  `c28ae81576e3d6c50cdadc2d4442530ba1b29533754edbe8323245750a89e823`.

The discovery endpoint was also exercised online. arXiv and Crossref both
returned results and were fairly interleaved; Semantic Scholar returned HTTP
429 under anonymous rate limiting and was isolated as an unavailable provider
without failing the request. Trusted import of arXiv `2603.09192` downloaded
the real PDF and correctly returned `duplicate` based on its content hash.

After adding final release gating, a third scoped request verified the complete
repair path. It returned 15 citations and found two locally ungrounded claims.
The repair stage retrieved six additional candidate evidence items and produced
a rewrite, but rejected that rewrite because TRACE would have fallen from
`supported` / 0.7313 to `insufficient` / 0.5038. The semantic pass reported a
conflict and deterministic checks included four failures, so the combined
release decision was correctly set to `blocked` and a visible evidence guard
was appended. Capsule `65d74683-994f-4f9b-a6d0-bcc960d5b00c` (SHA-256
`2120c9f8fee13fecb712c48e9c6cbe167f443db5842118d86bbe823b2a063447`)
persisted all 15 evidence records, semantic output, release decision, and the
rejected repair report. This verifies that the system does not adopt a rewrite
merely because an LLM produced it.

The final settings acceptance confirmed a single indexed paper and exercised
the editable runtime-control API. Defaults were Top-K 5, Fetch-K 20, RRF-K 60,
chunk size 500, overlap 50, and memory window 6. An invalid update with Fetch-K
below Top-K was rejected with HTTP 422 and did not alter the active settings.
The narrow-screen UI exposed validated retrieval, chunking, and memory controls,
plus explicit per-paper reindex and session-memory reset actions. Merely editing
chunking parameters does not mutate existing vectors.

## Defects found and resolved during acceptance

- Replaced GUI OpenCV in the Linux image with a hash-verified headless wheel.
- Prevented the upload API from returning success when Milvus insertion fails.
- Replaced the invalid sparse HNSW index with Milvus BM25 sparse inverted index.
- Upgraded and pinned Milvus to 2.6.24 and set the required standalone deploy
  mode for embedded etcd.
- Corrected function-based RRF parameters for Milvus 2.6+.
- Replaced parent expansion's accidental second hybrid search with an exact
  metadata query, eliminating repeated-ranker corruption.
- Corrected the documented application URL from backend port 8000 to frontend
  port 5173.
- Added layout-aware title and bibliography reconstruction for conference PDFs
  whose title and each citation span multiple PDF text blocks.
- Recovered from an interrupted embedded-etcd state by rebuilding the active
  Milvus index from the preserved original PDF in a new volume. The previous
  `milvus_data` volume remains intact as a recoverable backup.

## User-visible RAG, source-paper, and discovery inspection

The final UI acceptance also exercised the read-only Knowledge & Papers
Inspector against the running services. It displayed the imported paper's 280
child chunks, 236 parent chunks, pages 1-15, node/section distributions, the
active hybrid-retrieval pipeline, embedding and reranker models, and paginated
stored chunk text with identifiers. A real answer exposed its query
decomposition and all 15 retrieved evidence records with rank, relevance,
page, section, node type, excerpt, and chunk ID.

The second inspector tab lists every uploaded paper and can preview or open the
exact original PDF. Discover Papers uses the selected upload as its starting
point: for this acceptance source it reconstructed 18 bibliography entries,
exposed available DOI/arXiv source links, and returned 11 related works with
the matched source-paper topic terms shown for every result. Semantic Scholar's
live 429 rate limit was isolated and displayed while arXiv and Crossref results
remained available.

## Remaining boundaries

- No RAG system can guarantee truth for arbitrary papers or prompts. TRACE
  measures observable evidence structure and exposes uncertainty.
- The selected acceptance source is an arXiv preprint, not a peer-reviewed
  benchmark.
- Authentication and TLS are not included; keep this deployment local unless a
  security layer is added.
- Visual-language analysis is optional and requires a vision-capable model.
- A single-paper question naturally receives a lower cross-source-diversity
  score; multi-paper research questions should be tested separately.

## Reproduction

```powershell
docker compose up -d --build
curl.exe http://127.0.0.1:8000/api/health
```

Then open `http://127.0.0.1:5173`, select the imported paper, and use a guided
reading action or ask a scoped question. The TRACE panel should be reviewed
alongside the answer whenever the decision is `caution` or `insufficient`.
