"""Collection management + health check APIs."""

import logging
import shutil
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter
from pymilvus import connections, utility

from config import Config
from app.runtime_settings import get_llm_api_key, get_runtime_settings
from app.store import clear_all_files, store_backend

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["management"])


@router.delete("/collection")
async def clear_collection():
    try:
        alias = "clear_conn"
        connections.connect(alias=alias, uri=Config.MILVUS_URI)
        dropped = []
        for suffix in ("_children", "_parents"):
            name = f"{Config.COLLECTION_NAME}{suffix}"
            if utility.has_collection(name, using=alias):
                utility.drop_collection(name, using=alias)
                dropped.append(name)
        connections.disconnect(alias)

        # Clear all uploaded PDFs
        upload_dir = Path(Config.UPLOAD_DIR)
        if upload_dir.exists():
            for f in upload_dir.iterdir():
                if f.suffix == ".pdf":
                    f.unlink(missing_ok=True)

        # Clear all extracted figures
        figures_dir = Path("data/figures")
        if figures_dir.exists():
            shutil.rmtree(figures_dir)

        # Clear file records from store
        clear_all_files()

        return {"ok": True, "dropped": dropped}
    except Exception as e:
        logger.exception("Failed to clear collection")
        return {"ok": False, "detail": str(e)}


@router.get("/health")
async def health():
    status = {"milvus": False, "llm": False, "metadata": store_backend()}

    try:
        alias = "health_conn"
        connections.connect(alias=alias, uri=Config.MILVUS_URI)
        utility.list_collections(using=alias)
        connections.disconnect(alias)
        status["milvus"] = True
    except Exception:
        pass

    try:
        settings = get_runtime_settings()
        llm = settings.llm
        headers = {}
        if llm.provider == "ollama":
            parsed = urlparse(llm.base_url.rstrip("/"))
            path = parsed.path.rstrip("/")
            if path.endswith("/v1"):
                path = path[:-3]
            root = urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")
            url = f"{root}/api/tags"
        else:
            url = f"{llm.base_url.rstrip('/')}/models"
            api_key = get_llm_api_key(settings)
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        if llm.provider == "ollama":
            names = {
                item.get("name") or item.get("model")
                for item in response.json().get("models", [])
            }
            status["llm"] = llm.model in names
        else:
            status["llm"] = True
    except Exception:
        pass

    ok = all(status.values())
    return {"ok": ok, **status}
