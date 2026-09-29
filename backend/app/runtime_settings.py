"""Validated, persistent settings that may be changed from the local UI.

Environment variables remain the boot-time defaults. User overrides are kept
under ``data/`` so the Docker volume preserves them across container rebuilds.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from config import Config


SETTINGS_PATH = Path("data/runtime_settings.json")
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


class RuntimeSettings(BaseModel):
    retrieval: RetrievalSettings
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)


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


def reset_runtime_settings() -> RuntimeSettings:
    with _LOCK:
        SETTINGS_PATH.unlink(missing_ok=True)
        return default_settings()
