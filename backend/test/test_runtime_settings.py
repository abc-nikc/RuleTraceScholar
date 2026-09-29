import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from app.runtime_settings import (
    ChunkingSettings,
    RetrievalSettings,
    RuntimeSettings,
    default_settings,
    get_runtime_settings,
    reset_runtime_settings,
    save_runtime_settings,
)


class RuntimeSettingsTests(unittest.TestCase):
    def test_rejects_invalid_candidate_pool_and_overlap(self):
        with self.assertRaises(ValidationError):
            RetrievalSettings(
                top_k=10, fetch_k=5, rrf_k=60, rerank=True,
                expand_parent=True, diversify=True, diversity_weight=0.25,
            )
        with self.assertRaises(ValidationError):
            ChunkingSettings(chunk_size=300, chunk_overlap=300)

    def test_settings_round_trip_and_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime_settings.json"
            with patch("app.runtime_settings.SETTINGS_PATH", path):
                settings = default_settings()
                payload = settings.model_dump()
                payload["retrieval"]["top_k"] = 7
                payload["retrieval"]["fetch_k"] = 21
                payload["chunking"]["chunk_size"] = 720
                payload["memory"]["window_size"] = 10
                saved = save_runtime_settings(RuntimeSettings.model_validate(payload))
                loaded = get_runtime_settings()
                self.assertEqual(saved, loaded)
                self.assertEqual(loaded.retrieval.top_k, 7)
                self.assertEqual(loaded.chunking.chunk_size, 720)
                self.assertEqual(loaded.memory.window_size, 10)

                restored = reset_runtime_settings()
                self.assertFalse(path.exists())
                self.assertEqual(restored, default_settings())


if __name__ == "__main__":
    unittest.main()
