"""Tests for the OpenAI translator adapter."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pdf2zh.cache import clean_test_db, init_test_db


class OpenAITranslatorConfigTests(unittest.TestCase):
    """Test OpenAITranslator initialization and configuration."""

    def setUp(self) -> None:
        self.test_db = init_test_db()
        self._orig_env = {}
        for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
            self._orig_env[key] = os.environ.get(key)

    def tearDown(self) -> None:
        clean_test_db(self.test_db)
        for key, value in self._orig_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_raises_without_api_key(self):
        os.environ.pop("LLM_API_KEY", None)
        from pdf2zh.translator import OpenAITranslator
        with self.assertRaises(ValueError):
            OpenAITranslator("en", "vi", envs={"llm_api_key": ""})

    @patch("pdf2zh.translator.OpenAI")
    def test_reads_config_from_env(self, mock_openai_cls):
        os.environ["LLM_BASE_URL"] = "http://test:1234/v1"
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["LLM_MODEL"] = "test-model"
        from pdf2zh.translator import OpenAITranslator
        t = OpenAITranslator("en", "vi")
        self.assertEqual(t.base_url, "http://test:1234/v1")
        self.assertEqual(t.api_key, "test-key")
        self.assertEqual(t.model, "test-model")

    @patch("pdf2zh.translator.OpenAI")
    def test_envs_override_env_vars(self, mock_openai_cls):
        os.environ["LLM_BASE_URL"] = "http://env:1234/v1"
        os.environ["LLM_API_KEY"] = "env-key"
        os.environ["LLM_MODEL"] = "env-model"
        from pdf2zh.translator import OpenAITranslator
        t = OpenAITranslator(
            "en", "vi",
            envs={
                "llm_base_url": "http://envs:5678/v1",
                "llm_api_key": "envs-key",
                "llm_model": "envs-model",
            },
        )
        self.assertEqual(t.base_url, "http://envs:5678/v1")
        self.assertEqual(t.api_key, "envs-key")
        self.assertEqual(t.model, "envs-model")

    @patch("pdf2zh.translator.OpenAI")
    def test_loads_system_prompt_from_file(self, mock_openai_cls):
        os.environ["LLM_API_KEY"] = "test-key"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Custom system prompt for testing")
            f.flush()
            from pdf2zh.translator import OpenAITranslator
            t = OpenAITranslator("en", "vi", envs={"system_prompt": f.name})
            self.assertEqual(t.system_prompt, "Custom system prompt for testing")
        os.unlink(f.name)

    @patch("pdf2zh.translator.OpenAI")
    def test_loads_glossary_from_file(self, mock_openai_cls):
        os.environ["LLM_API_KEY"] = "test-key"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"en": "mandible", "vi": "xương hàm dưới"}\n')
            f.write('{"en": "maxilla", "vi": "xương hàm trên"}\n')
            f.flush()
            from pdf2zh.translator import OpenAITranslator
            t = OpenAITranslator("en", "vi", envs={"glossary": f.name})
            self.assertIn("mandible", t.glossary_context)
            self.assertIn("xương hàm dưới", t.glossary_context)
        os.unlink(f.name)

    @patch("pdf2zh.translator.OpenAI")
    def test_default_prompt_mentions_target_language(self, mock_openai_cls):
        os.environ["LLM_API_KEY"] = "test-key"
        from pdf2zh.translator import OpenAITranslator
        t = OpenAITranslator("en", "vi")
        self.assertIn("Vietnamese", t.system_prompt)


class OpenAITranslatorEngineRegistration(unittest.TestCase):
    def test_openai_is_registered(self):
        from pdf2zh.translator import ENGINES
        self.assertIn("openai", ENGINES)


if __name__ == "__main__":
    unittest.main()
