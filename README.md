# RuleTrace Scholar — Personal Explainable Academic Agent

**Explainable Agentic RAG with Adaptive Evidence Rules**

RuleTrace Scholar is a **personal academic research assistant** for reading,
questioning, tracing, and discovering scholarly literature. Upload papers, ask
questions in natural language, and inspect both the answer and the exact
claim-to-evidence path used to judge whether it is reliable enough to use.

> **定位 / Positioning:** 面向个人学术研究的本地优先智能体，帮助用户精读论文、核查实验、管理证据、发现相关研究和形成可复现的研究记录。它辅助研究判断，不代替研究者，也不会自动投稿或把模型输出冒充为已验证事实。

![Python](https://img.shields.io/badge/python-3.12-blue)
![React](https://img.shields.io/badge/react-18-61dafb)
![LangGraph](https://img.shields.io/badge/LangGraph-0.x-orange)
![Milvus](https://img.shields.io/badge/Milvus-2.6.24-00bfa5)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What We Added Beyond ScholarRAG

RuleTrace Scholar retains the useful upload–retrieve–answer foundation of
ScholarRAG, but its research contribution is an **inspectable evidence
governance layer** rather than another opaque PDF chatbot.

| Original addition in RuleTrace Scholar | Practical value for a personal researcher |
|---|---|
| **TRACE claim–evidence graph** | Splits an answer into claims and exposes which retrieved evidence supports each one |
| **Adaptive evidence rules** | Applies different grounding requirements to background, method, experiment, and multi-hop questions |
| **Verified retrieve–rewrite loop** | Repairs weak answers once and accepts the rewrite only when the evidence trace measurably improves |
| **Deterministic scientific claim tests** | Checks citation resolution and whether reported numeric values actually occur in cited evidence |
| **Semantic entailment and conflict audit** | Separates supported, contradicted, and insufficient claims and records evidence tensions |
| **Research Replay Capsules** | Stores answer, evidence, model/settings, rule result, and fingerprints for reproducibility and comparison |
| **User-visible RAG and original-paper inspector** | Shows real parent/child chunks, node types, retrieval settings, evidence text, and every preserved original PDF |
| **Source-paper research discovery** | Reconstructs the uploaded paper's bibliography locally, then finds related work from arXiv, Semantic Scholar, and Crossref with visible matching reasons |
| **Paper-scoped guided reading** | Provides one-click overview, method, experiment, and innovation tasks without requiring prompt-engineering expertise |

These additions are designed for **human-in-the-loop personal scholarship**:
the user can inspect, challenge, reconfigure, and reproduce the agent's process
instead of receiving only a fluent final answer.

---

## Features

- **TRACE explainability layer**: claim segmentation → evidence graph → adaptive rules → reliability decision
- **One-click guided reading**: after upload, automatically produce a scoped overview, method walkthrough, experiment audit, or innovation analysis without requiring the user to design a prompt
- **Paper-scoped follow-up**: guided-reading conversations keep retrieval constrained to the selected paper to prevent cross-document evidence leakage
- **Process-faithful explanations**: rules consume the same citations and retrieval provenance used during generation
- **Adaptive evidence thresholds**: experimental, methodological, background, and complex multi-hop queries receive different evidence requirements
- **Uncertainty-aware evidence guard**: supported / caution / insufficient decisions with an explicitly uncalibrated uncertainty index
- **Counterfactual evidence plans**: shows what additional evidence would make a weak answer stronger
- **Research Replay Capsules**: answer, evidence, TRACE result, model configuration, and SHA-256 fingerprints are saved for run-to-run comparison
- **Scientific claim unit tests**: deterministic citation-resolution and numeric-evidence checks distinguish pass, review, fail, and untestable outcomes
- **Semantic evidence audit**: a conservative structured LLM pass labels citation-linked claims as entailed, contradicted, or insufficient and records evidence tensions
- **Verified evidence repair**: weak or partially ungrounded answers receive one bounded retrieve-rewrite pass; the rewrite is retained only when TRACE measurably improves
- **Source-paper research discovery**: extract the uploaded PDF's bibliography locally, then use its title, abstract, and topics to query arXiv, Semantic Scholar, and Crossref concurrently with per-provider failure isolation
- **Trusted one-click import**: arXiv identifiers are validated and downloaded from a fixed host before the shared upload/indexing pipeline runs
- **Release decision**: TRACE, deterministic tests, and semantic review are fused into supported / review / blocked, with visible guard notices
- **Knowledge & Papers Inspector**: users can inspect uploaded-paper metadata, parent/child chunks, parsed node types, the live RAG configuration, per-answer retrieval ranks and evidence text, and preview or open every preserved original PDF
- **Validated runtime controls**: edit Top-K/Fetch-K/RRF, reranking, parent expansion, evidence diversity, chunk size/overlap, structured-node preservation, and memory-window policy from the Settings panel; rebuild an existing paper explicitly when chunking changes
- **Professional metadata persistence**: PostgreSQL stores sessions, files, and replay capsules in production; local preview can automatically fall back to SQLite
- **Metadata-aware evidence diversity**: MMR-style selection rewards independent papers and sections
- **Multi-agent pipeline** (LangGraph): query classification → decomposition → parallel sub-agents → reflection → synthesis
- **Hybrid retrieval**: BM25 + dense embedding fusion (RRF) + CrossEncoder reranking + parent-child chunk expansion
- **Structured PDF parsing** (Docling): section hierarchy, tables, figures, formulas, captions; smart OCR fallback
- **VLM integration**: lazy figure analysis for visual queries or insufficient text answers
- **Multi-turn memory**: sliding window + LLM summary compression, persisted via Postgres checkpointer
- **SSE streaming** with source-level citations (paper, section, page)
- **Built-in evaluation**: RAGAS (Faithfulness, Relevancy, Precision, Correctness) + retrieval metrics (Recall@k, MRR, MAP)

---

## Architecture

**Main graph:**
```
START → summarize → classify → analyze → [sub_agent × N] → prepare_synthesis
      → claim/evidence graph → adaptive evidence rules
      → conditional retrieve-rewrite-verify → deterministic tests
      → semantic entailment/conflict audit → release decision → replay capsule
```

**Sub-agent graph:**
```
retrieve → generate → reflect → (retry | done)
```

**Retrieval pipeline:**
```
Query → [HyDE] → BM25 + Dense → RRF → CrossEncoder → Evidence diversity → Parent expansion → Top-K
```

**TRACE report:**
```
Answer claims + retrieved provenance
    → valid citation edges
    → R1 grounding · R2 validity · R3 traceability · R4 diversity · R5 density
    → supported / caution / insufficient
    → counterfactual retrieval actions
```

The reliability score is an **uncalibrated evidence-quality index**, not a probability that an answer is true.

---

## Project Structure

```
ruletrace-scholar/
├── backend/
│   ├── app/         # FastAPI: routers, SSE, PostgreSQL/SQLite metadata store
│   ├── agent/       # LangGraph: graph, nodes, prompts, tools, checkpointer
│   ├── rag/         # PDF parsing (Docling), retrieval (Milvus hybrid), reranking, VLM, citation
│   ├── explainability/ # TRACE claim graph, adaptive rules, uncertainty, counterfactuals
│   ├── research_audit/ # Claim tests, semantic audit, Research Replay Capsules
│   ├── research_sources/ # Concurrent arXiv, Semantic Scholar, Crossref discovery
│   ├── eval/        # RAGAS + retrieval + explainability evaluation
│   └── config.py
├── frontend/        # React 18 + Vite + TailwindCSS, SSE client
├── docker-compose.yml  # backend + frontend + milvus + postgres
└── Makefile
```

---

## Quick Start

### Prerequisites

- Python 3.12+, Node.js 18+
- Milvus 2.x on `localhost:19530`
- PostgreSQL
- An OpenAI-compatible LLM endpoint (vLLM / Ollama / OpenAI)

### Configuration

Copy `backend/.env.example` to `backend/.env` and edit. Key settings:

```yaml
MILVUS_URI=http://localhost:19530
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
LLM_BASE_URL=http://localhost:8848/v1
LLM_MODEL=GPT-4o-mini
VLM_ENABLED=true
ENABLE_EVIDENCE_DIVERSITY=true
EVIDENCE_DIVERSITY_WEIGHT=0.25
EXPLANATION_GUARD_ENABLED=true
AUTO_EVIDENCE_REPAIR=true
AUTO_EVIDENCE_REPAIR_MAX_QUERIES=2
ENABLE_SEMANTIC_AUDIT=true
SEMANTIC_SCHOLAR_API_KEY=       # optional
CROSSREF_MAILTO=                # optional polite-pool identity
POSTGRES_URI=postgresql://postgres:postgres@localhost:5432/ruletrace_scholar
METADATA_BACKEND=auto
```

### Run

**Docker (recommended):**
```powershell
git clone https://github.com/abc-nikc/RuleTraceScholar.git
cd RuleTraceScholar
Copy-Item backend/.env.example backend/.env
ollama pull qwen3:8b
docker compose up -d --build
```

**Local dev:**
```bash
make install
make dev    # backend :8000 + frontend :5173
```

**Windows automated launcher:**
```powershell
.\scripts\start_ruletrace.ps1              # full application, validates required services
.\scripts\start_ruletrace.ps1 -PreviewOnly # production UI preview without backend services
```

Open the application at http://localhost:5173. The backend API and OpenAPI
documentation are available at http://localhost:8000 and
http://localhost:8000/docs.

---

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | SSE streaming chat; optional `paper_ids` constrains retrieval to selected papers |
| `GET` | `/api/sessions` | List sessions |
| `GET` | `/api/sessions/:id/history` | Conversation history |
| `DELETE` | `/api/sessions/:id` | Delete session |
| `POST` | `/api/files/upload` | Upload PDFs |
| `GET` | `/api/files` | List files |
| `GET` | `/api/files/:id/content` | Stream the exact uploaded PDF for inline preview or opening |
| `DELETE` | `/api/files/:id` | Delete file + vectors |
| `GET` | `/api/discovery/search?query=...` | Concurrent arXiv, Semantic Scholar, and Crossref discovery |
| `GET` | `/api/discovery/from-paper/:file_id` | Extract that upload's references and discover transparently related research |
| `POST` | `/api/discovery/import/arxiv` | Validate, download, deduplicate, parse, and index an arXiv PDF |
| `GET` | `/api/inspection/papers` | Inspect uploaded papers, Milvus parent/child counts, node distributions, and RAG configuration |
| `GET` | `/api/inspection/papers/:paper_id/chunks` | Page through the actual parent or child chunk text stored for RAG |
| `GET` | `/api/inspection/sessions/:session_id/memory` | Inspect the persisted message window, compressed summary, scope, and latest query plan |
| `GET`, `PUT`, `DELETE` | `/api/settings` | Read, validate/update, or restore runtime RAG, chunking, and memory settings |
| `POST` | `/api/settings/papers/:file_id/reindex` | Reparse and rebuild one paper using the current chunking settings |
| `DELETE` | `/api/settings/memory/sessions/:session_id` | Reset one conversation checkpoint while retaining its session record |
| `GET` | `/api/audit/sessions/:id/capsules` | List reproducible answer capsules |
| `GET` | `/api/audit/capsules/:id` | Inspect one complete replay capsule |
| `GET` | `/api/audit/compare?left=:id&right=:id` | Compare evidence and decision stability across two runs |
| `DELETE` | `/api/collection` | Clear vector database |
| `GET` | `/api/health` | Health check |

The chat stream additionally emits `explanation`, `claim_tests`, `repair`, and
`capsule` events. Together they expose the rule trace, semantic judgements,
retrieve-rewrite outcome, release decision, and reproducibility fingerprint.

---

## Evaluation

```bash
cd backend
python -m unittest discover -s test -v
python eval/eval_retrieval.py    # Recall@k, Precision@k, MRR, MAP
python eval/eval_generation.py   # RAGAS metrics
```

`eval/eval_explainability.py` aggregates coverage, citation validity, traceability, diversity, density, guard decisions, and rule pass rates over answer sets.

---

## Tech Stack

| Layer | Tech |
|---|---|
| Agent orchestration | LangGraph + LangChain |
| LLM / VLM | OpenAI-compatible (vLLM / Ollama) |
| Vector DB | Milvus 2.6.24 (BM25 + dense hybrid) |
| PDF parsing | Docling + PyMuPDF |
| Embedding / Rerank | BAAI/bge-small-en-v1.5 + bge-reranker-v2-m3 |
| Backend | FastAPI + Uvicorn + sse-starlette |
| State persistence | PostgreSQL (AsyncPostgresSaver) |
| Metadata persistence | PostgreSQL connection pool; SQLite local fallback |
| Frontend | React 18 + Vite + TailwindCSS |
| Evaluation | RAGAS |
| Discovery | arXiv Atom API + Semantic Scholar Graph API + Crossref REST API |
| Explainability | TRACE rules + claim-evidence graph + bounded evidence repair |
| Evidence audit | Deterministic claim tests + structured semantic entailment/conflict review |
| Deployment | Docker Compose + Nginx |

---

## Research Positioning

RuleTrace Scholar transfers two ideas from the supplied manuscripts into general scientific question answering: constrained and auditable construction, and a shared evidence pathway for answering, reliability assessment, and explanation. The contribution is **evidence-path interpretability**, not a claim that the underlying LLM is intrinsically interpretable.

See [`doc/RESEARCH_ALIGNMENT.md`](doc/RESEARCH_ALIGNMENT.md) for the comparison with ScholarRAG and Personal Research Assistant Agent, the paper-to-system mapping, and the experiment roadmap.

See [`doc/ACCEPTANCE_REPORT.md`](doc/ACCEPTANCE_REPORT.md) for the reproducible
end-to-end acceptance run against a real 2026 arXiv paper, including hashes,
database row counts, audit results, restart persistence, and known limitations.

---

## Lineage and Attribution

This project is an MIT-licensed transformation of [ScholarRAG](https://github.com/tang923/Agentic-rag-scholar-assistant). The design review also considered [Personal Research Assistant Agent](https://github.com/Nekilesh001/Personal-Research-Assistant-Agent). Upstream attribution is retained while TRACE, adaptive evidence policies, evidence-diverse retrieval, Research Replay Capsules, scientific claim unit tests, the audit UI, tests, and research framing are original additions in this workspace.

---

## Security Notice

RuleTrace Scholar is a **research/learning tool** for trusted local or internal networks. It has **no built-in auth**, CORS is fully open, and destructive endpoints are unprotected. Do not expose to the public internet without adding authentication, TLS, and access controls.

