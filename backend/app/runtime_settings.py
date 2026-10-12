"""Validated, persistent settings that may be changed from the local UI.

Environment variables remain the boot-time defaults. User overrides are kept
under ``data/`` so the Docker volume preserves them across container rebuilds.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from config import Config


SETTINGS_PATH = Path("data/runtime_settings.json")
LLM_SECRET_PATH = Path("data/llm_api_key")
_LOCK = threading.RLock()


class RetrievalSettings(BaseModel):
    top_k: int = Field(ge=1, le=20)
    fetch_k: int = Field(ge=1, le=100)
    rrf_k: int = Field(ge=1, le=200)
    rerank: bool = True
    expand_parent: bool = True
    diversify: bool = True
    diversity_weight: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_candidate_pool(self):
        if self.fetch_k < self.top_k:
            raise ValueError("fetch_k must be greater than or equal to top_k")
        return self


class ChunkingSettings(BaseModel):
    chunk_size: int = Field(default=500, ge=200, le=2000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)
    preserve_structured_nodes: bool = True

    @model_validator(mode="after")
    def validate_overlap(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class MemorySettings(BaseModel):
    window_size: int = Field(default=6, ge=2, le=30)
    summarization_enabled: bool = True


class LLMSettings(BaseModel):
    provider: Literal["ollama", "openai_compatible"] = "ollama"
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    fast_model: str = Field(default="", max_length=200)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    fast_max_tokens: int = Field(default=1024, ge=64, le=32768)
    deep_max_tokens: int = Field(default=4096, ge=64, le=65536)
    reasoning_supported: bool = True

    @model_validator(mode="after")
    def validate_endpoint(self):
        self.base_url = self.base_url.strip().rstrip("/")
        self.model = self.model.strip()
        self.fast_model = self.fast_model.strip()
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be a valid HTTP(S) endpoint")
        if not self.model:
            raise ValueError("model cannot be empty")
        if self.deep_max_tokens < self.fast_max_tokens:
            raise ValueError("deep_max_tokens must be greater than or equal to fast_max_tokens")
        return self


class RuntimeSettings(BaseModel):
    retrieval: RetrievalSettings
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    llm: LLMSettings = Field(default_factory=lambda: default_llm_settings())


def default_llm_settings() -> LLMSettings:
    is_ollama = Config.LLM_PROVIDER == "ollama"
    return LLMSettings(
        provider="ollama" if is_ollama else "openai_compatible",
        base_url=Config.LLM_BASE_URL,
        model=Config.LLM_MODEL,
        fast_model=Config.LLM_FAST_MODEL,
        temperature=Config.LLM_TEMPERATURE,
        fast_max_tokens=Config.LLM_FAST_MAX_TOKENS,
        deep_max_tokens=Config.LLM_MAX_TOKENS,
        reasoning_supported=is_ollama,
    )


def default_settings() -> RuntimeSettings:
    return RuntimeSettings(
        retrieval=RetrievalSettings(
            top_k=Config.TOP_K,
            fetch_k=Config.FETCH_K,
            rrf_k=Config.RRF_K,
            rerank=True,
            expand_parent=True,
            diversify=Config.ENABLE_EVIDENCE_DIVERSITY,
            diversity_weight=Config.EVIDENCE_DIVERSITY_WEIGHT,
        )
    )


def get_runtime_settings() -> RuntimeSettings:
    with _LOCK:
        if not SETTINGS_PATH.exists():
            return default_settings()
        try:
            return RuntimeSettings.model_validate_json(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            # A corrupt local override must never prevent application startup.
            return default_settings()


def save_runtime_settings(settings: RuntimeSettings) -> RuntimeSettings:
    with _LOCK:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_PATH.with_suffix(".tmp")
        temporary.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(SETTINGS_PATH)
        return settings


def get_llm_api_key(settings: RuntimeSettings | None = None) -> str:
    active = settings or get_runtime_settings()
    if active.llm.provider == "ollama":
        return "ollama"
    with _LOCK:
        try:
            secret = LLM_SECRET_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            secret = ""
    if secret:
        return secret
    return "" if Config.LLM_API_KEY == "ollama" else Config.LLM_API_KEY


def selected_llm_model(settings: RuntimeSettings, thinking: bool) -> str:
    """Resolve the actual model used by a mode, preserving old saved settings."""
    return settings.llm.model if thinking else (settings.llm.fast_model or settings.llm.model)


def save_llm_api_key(api_key: str) -> None:
    secret = api_key.strip()
    if not secret:
        return
    with _LOCK:
        LLM_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = LLM_SECRET_PATH.with_suffix(".tmp")
        temporary.write_text(secret, encoding="utf-8")
        temporary.replace(LLM_SECRET_PATH)


def clear_llm_api_key() -> None:
    with _LOCK:
        LLM_SECRET_PATH.unlink(missing_ok=True)


def llm_api_key_configured(settings: RuntimeSettings | None = None) -> bool:
    active = settings or get_runtime_settings()
    if active.llm.provider == "ollama":
        return False
    return bool(get_llm_api_key(active))


def reset_runtime_settings() -> RuntimeSettings:
    with _LOCK:
        SETTINGS_PATH.unlink(missing_ok=True)
        LLM_SECRET_PATH.unlink(missing_ok=True)
        return default_settings()
