import unittest
from unittest.mock import patch

from app.dependencies import clear_llm_cache, get_llm
from app.runtime_settings import RuntimeSettings, default_settings


class LLMSelectionTests(unittest.TestCase):
    def tearDown(self):
        clear_llm_cache()

    def test_selected_provider_model_and_reasoning_mode_reach_client(self):
        payload = default_settings().model_dump()
        payload["llm"].update({
            "provider": "openai_compatible",
            "base_url": "https://example.test/v1",
            "model": "research-model",
            "temperature": 0.3,
            "fast_max_tokens": 512,
            "deep_max_tokens": 2048,
            "reasoning_supported": True,
        })
        settings = RuntimeSettings.model_validate(payload)

        with patch("app.dependencies.get_runtime_settings", return_value=settings), patch(
            "app.dependencies.get_llm_api_key", return_value="secret"
        ), patch("app.dependencies.ChatOpenAI") as chat_openai:
            get_llm(False)
            get_llm(True)

        fast = chat_openai.call_args_list[0].kwargs
        deep = chat_openai.call_args_list[1].kwargs
        self.assertEqual(fast["base_url"], "https://example.test/v1")
        self.assertEqual(fast["model"], "research-model")
        self.assertEqual(fast["api_key"], "secret")
        self.assertEqual(fast["max_tokens"], 512)
        self.assertEqual(fast["reasoning_effort"], "none")
        self.assertEqual(deep["max_tokens"], 2048)
        self.assertEqual(deep["reasoning_effort"], "high")

    def test_reasoning_parameter_is_omitted_for_unsupported_endpoint(self):
        payload = default_settings().model_dump()
        payload["llm"]["reasoning_supported"] = False
        settings = RuntimeSettings.model_validate(payload)

        with patch("app.dependencies.get_runtime_settings", return_value=settings), patch(
            "app.dependencies.get_llm_api_key", return_value="ollama"
        ), patch("app.dependencies.ChatOpenAI") as chat_openai:
            get_llm(True)

        self.assertNotIn("reasoning_effort", chat_openai.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
