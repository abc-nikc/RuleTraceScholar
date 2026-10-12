import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from app.runtime_settings import (
    ChunkingSettings,
    LLMSettings,
    RetrievalSettings,
    RuntimeSettings,
    clear_llm_api_key,
    default_settings,
    get_llm_api_key,
    get_runtime_settings,
    llm_api_key_configured,
    reset_runtime_settings,
    save_llm_api_key,
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
        with self.assertRaises(ValidationError):
            LLMSettings(
                provider="openai_compatible",
                base_url="not-a-url",
                model="example",
                fast_max_tokens=1024,
                deep_max_tokens=512,
            )

    def test_settings_round_trip_and_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime_settings.json"
            secret_path = Path(directory) / "llm_api_key"
            with patch("app.runtime_settings.SETTINGS_PATH", path), patch(
                "app.runtime_settings.LLM_SECRET_PATH", secret_path
            ):
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
                self.assertEqual(loaded.llm.model, settings.llm.model)

                payload = loaded.model_dump()
                payload["llm"]["provider"] = "openai_compatible"
                external = RuntimeSettings.model_validate(payload)
                save_runtime_settings(external)
                self.assertFalse(llm_api_key_configured(external))
                save_llm_api_key("secret-test-key")
                self.assertTrue(llm_api_key_configured(external))
                self.assertEqual(get_llm_api_key(external), "secret-test-key")
                clear_llm_api_key()
                self.assertFalse(secret_path.exists())

                restored = reset_runtime_settings()
                self.assertFalse(path.exists())
                self.assertEqual(restored, default_settings())


if __name__ == "__main__":
    unittest.main()
