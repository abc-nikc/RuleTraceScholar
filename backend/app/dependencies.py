"""Shared application dependencies (singletons, lifespan)."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from config import Config
from rag.retrieval import Retriever
from rag.citation import CitationExtractor
from rag.integration import PDFParser, RAGIntegration
from app.store import close_store, initialize_store
from app.runtime_settings import get_llm_api_key, get_runtime_settings, selected_llm_model

logger = logging.getLogger(__name__)


async def _ensure_postgres_db():
    """Create the database if it doesn't exist."""
    uri = Config.POSTGRES_URI
    # Connect to default 'postgres' db to create target db
    idx = uri.rfind("/")
    db_name = uri[idx + 1:]
    base_uri = uri[:idx] + "/postgres"
    try:
        conn = await psycopg.AsyncConnection.connect(base_uri, autocommit=True)
        async with conn:
            cur = await conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if not await cur.fetchone():
                await conn.execute(f'CREATE DATABASE "{db_name}"')
                logger.info(f"Created database: {db_name}")
    except Exception as e:
        logger.warning(f"Could not auto-create database: {e}")


class RetrieverTool:
    def __init__(self, retriever: Retriever):
        self._retriever = retriever

    def invoke(
        self,
        query: str,
        section_type_filter=None,
        paper_ids=None,
        rerank: bool | None = None,
        expand_parent: bool | None = None,
    ):
        settings = get_runtime_settings().retrieval
        return self._retriever.retrieve(
            query=query,
            k=settings.top_k,
            use_hyde=False,
            rerank=settings.rerank if rerank is None else rerank,
            expand_parent=settings.expand_parent if expand_parent is None else expand_parent,
            rrf_k=settings.rrf_k,
            fetch_k=settings.fetch_k,
            section_type_filter=section_type_filter,
            paper_ids=paper_ids,
            diversify=settings.diversify,
            diversity_weight=settings.diversity_weight,
        )


_llm_clients: dict[tuple, ChatOpenAI] = {}
_retriever: Retriever | None = None
_retriever_tool: RetrieverTool | None = None
_pdf_parser: PDFParser | None = None
_rag_integration: RAGIntegration | None = None
_checkpointer: AsyncPostgresSaver | None = None


def get_llm(thinking: bool | None = None) -> ChatOpenAI:
    """Return a cached client for the model/provider selected in the UI."""
    settings = get_runtime_settings()
    llm_settings = settings.llm
    use_deep = Config.LLM_THINKING if thinking is None else thinking
    selected_model = selected_llm_model(settings, use_deep)
    api_key = get_llm_api_key(settings)
    cache_key = (
        llm_settings.provider,
        llm_settings.base_url,
        selected_model,
        api_key,
        llm_settings.temperature,
        llm_settings.fast_max_tokens,
        llm_settings.deep_max_tokens,
        llm_settings.reasoning_supported,
        use_deep,
    )
    if cache_key not in _llm_clients:
        options = dict(
            base_url=llm_settings.base_url,
            model=selected_model,
            api_key=api_key or "not-configured",
            temperature=llm_settings.temperature,
            max_tokens=(
                llm_settings.deep_max_tokens if use_deep else llm_settings.fast_max_tokens
            ),
            timeout=(
                Config.LLM_DEEP_TIMEOUT_SECONDS
                if use_deep
                else Config.LLM_FAST_TIMEOUT_SECONDS
            ),
            max_retries=0,
        )
        if llm_settings.reasoning_supported:
            options["reasoning_effort"] = "high" if use_deep else "none"
        _llm_clients[cache_key] = ChatOpenAI(**options)
    return _llm_clients[cache_key]


def clear_llm_cache() -> None:
    _llm_clients.clear()


def get_retriever() -> Retriever:
    return _retriever  # type: ignore


def get_retriever_tool() -> RetrieverTool:
    return _retriever_tool  # type: ignore


def get_pdf_parser() -> PDFParser:
    return _pdf_parser  # type: ignore


def get_rag_integration() -> RAGIntegration:
    return _rag_integration  # type: ignore


def get_checkpointer() -> AsyncPostgresSaver:
    return _checkpointer  # type: ignore


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _retriever, _retriever_tool, _pdf_parser, _rag_integration, _checkpointer

    logger.info("Starting up — loading models …")

    await _ensure_postgres_db()
    selected_store = initialize_store(Config.POSTGRES_URI, Config.METADATA_BACKEND)
    logger.info("Selected metadata backend: %s", selected_store)

    _retriever = Retriever(
        embedding_model=Config.EMBEDDING_MODEL,
        reranker_model=Config.RERANKER_MODEL,
        milvus_uri=Config.MILVUS_URI,
        collection_name=Config.COLLECTION_NAME,
        enable_cache=Config.ENABLE_CACHE,
    )
    _retriever_tool = RetrieverTool(_retriever)

    _pdf_parser = PDFParser(llm=get_llm(False))
    _rag_integration = RAGIntegration(
        embedding_model=Config.EMBEDDING_MODEL,
        milvus_uri=Config.MILVUS_URI,
        collection_name=Config.COLLECTION_NAME,
    )

    upload_dir = Path(Config.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncPostgresSaver.from_conn_string(Config.POSTGRES_URI) as cp:
        await cp.setup()
        _checkpointer = cp
        logger.info("Startup complete.")
        yield

    _checkpointer = None
    close_store()
    logger.info("Shutting down.")
