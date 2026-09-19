"""Translation adapters for the preservation-focused PDF core."""

from __future__ import annotations

import html
import json
import logging
import os
import re
import threading
import time
import unicodedata
from typing import Any, ClassVar

import requests

from pdf2zh.cache import TranslationCache

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

logger = logging.getLogger(__name__)

PLACEHOLDER_PATTERN = re.compile(r"</?b\d+>")


def remove_control_characters(value: str) -> str:
    """Remove control characters that cannot be emitted safely into PDF text."""
    return "".join(character for character in value if unicodedata.category(character)[0] != "C")


class BaseTranslator:
    """Cache-aware translator interface consumed by the PDF converter."""

    name = "base"
    lang_map: ClassVar[dict[str, str]] = {}

    def __init__(
        self,
        lang_in: str,
        lang_out: str,
        model: str | None = None,
        *,
        ignore_cache: bool = False,
        **_: Any,
    ) -> None:
        self.lang_in = self.lang_map.get(lang_in.lower(), lang_in)
        self.lang_out = self.lang_map.get(lang_out.lower(), lang_out)
        self.model = model
        self.ignore_cache = ignore_cache
        self.cache = TranslationCache(
            self.name,
            {
                "lang_in": self.lang_in,
                "lang_out": self.lang_out,
                "model": model,
            },
        )

    def translate(self, text: str, ignore_cache: bool = False) -> str:
        """Translate text, consulting the persistent cache unless bypassed."""
        if not (self.ignore_cache or ignore_cache):
            cached = self.cache.get(text)
            if cached is not None:
                return cached
        translated = self.do_translate(text)
        if not (self.ignore_cache or ignore_cache):
            self.cache.set(text, translated)
        return translated

    def do_translate(self, text: str) -> str:
        """Translate one engine-sized text segment."""
        raise NotImplementedError

    def get_rich_text_left_placeholder(self, identifier: int) -> str:
        return f"<b{identifier}>"

    def get_rich_text_right_placeholder(self, identifier: int) -> str:
        return f"</b{identifier}>"

    def get_formular_placeholder(self, identifier: int) -> str:
        return self.get_rich_text_left_placeholder(identifier) + self.get_rich_text_right_placeholder(identifier)


def normalize_placeholders(text: str) -> str:
    """Normalize any accidental spaces inside formula placeholder tags, e.g. < b0 > -> <b0>."""
    return re.sub(r"<\s*(/?)\s*b\s*(\d+)\s*>", r"<\1b\2>", text)


class GoogleTranslator(BaseTranslator):
    """Translate through Google's endpoints without an API key with multi-tier fallback."""

    name = "google"
    lang_map: ClassVar[dict[str, str]] = {"zh": "zh-CN"}

    def __init__(
        self,
        lang_in: str,
        lang_out: str,
        model: str | None = None,
        *,
        ignore_cache: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            lang_in,
            lang_out,
            model,
            ignore_cache=ignore_cache,
            **kwargs,
        )
        self.session = requests.Session()
        self.endpoint = "https://clients5.google.com/translate_a/t"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
            )
        }

    def _translate_clients5(self, text: str) -> str:
        response = self.session.get(
            "https://clients5.google.com/translate_a/t",
            params={
                "client": "dict-chrome-ex",
                "sl": self.lang_in,
                "tl": self.lang_out,
                "q": text[:5000],
            },
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            if data and isinstance(data[0], str):
                return "".join(data)
            elif data and isinstance(data[0], list):
                parts = []
                for item in data:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, list) and item and isinstance(item[0], str):
                        parts.append(item[0])
                return "".join(parts)
        elif isinstance(data, str):
            return data
        raise ValueError(f"Unexpected response format from clients5: {data}")

    def _translate_googleapis(self, text: str) -> str:
        response = self.session.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "dict-chrome-ex",
                "dt": "t",
                "sl": self.lang_in,
                "tl": self.lang_out,
                "q": text[:5000],
            },
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data and isinstance(data[0], list):
            parts = [
                part[0] for part in data[0] if part and len(part) > 0 and isinstance(part[0], str)
            ]
            return "".join(parts)
        raise ValueError(f"Unexpected response format from googleapis: {data}")

    def _translate_mobile_web(self, text: str) -> str:
        response = self.session.get(
            "https://translate.google.com/m",
            params={"tl": self.lang_out, "sl": self.lang_in, "q": text[:5000]},
            headers=self.headers,
            timeout=30,
        )
        if response.status_code == 400:
            raise RuntimeError("Google Translate rejected the text segment")
        response.raise_for_status()
        match = re.search(
            r'(?s)class="(?:t0|result-container)">(.*?)<',
            response.text,
        )
        if match is None:
            raise RuntimeError("Google Translate response did not contain a translation result")
        return match.group(1)

    def do_translate(self, text: str) -> str:
        if not text or not text.strip():
            return text
        errors = []
        for method in (self._translate_clients5, self._translate_googleapis, self._translate_mobile_web):
            try:
                result = method(text)
                if result:
                    result = normalize_placeholders(result)
                    return remove_control_characters(html.unescape(result))
            except Exception as e:
                method_name = getattr(method, "__name__", str(method))
                errors.append(f"{method_name}: {e}")
                continue
        raise RuntimeError(f"All Google Translate endpoints failed: {'; '.join(errors)}")


def placeholders(text: str) -> list[str]:
    """Return the formula placeholder tags in order, e.g. ['<b0>', '</b0>']."""
    return PLACEHOLDER_PATTERN.findall(text)


def load_segment_table(path: str | None) -> dict[str, str]:
    """Load a source-to-translation table from a JSONL file of {"src", "dst"} records.

    Entries whose translation dropped or reordered a formula placeholder are
    skipped, so the next pass re-emits them instead of silently losing a formula.
    """
    if not path:
        return {}
    table: dict[str, str] = {}
    with open(path, encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                source, translation = record["src"], record["dst"]
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(
                    f"{path} line {number}: expected a JSON object with 'src' and 'dst'"
                ) from error
            if not isinstance(source, str) or not isinstance(translation, str):
                raise ValueError(f"{path} line {number}: 'src' and 'dst' must be strings")
            if not translation:
                continue
            if placeholders(source) != placeholders(translation):
                logger.warning(
                    "%s line %d: formula placeholders differ between src and dst; "
                    "segment left untranslated",
                    path,
                    number,
                )
                continue
            table[source] = translation
    return table


class HandoffTranslator(BaseTranslator):
    """Translate from a table produced outside the pipeline, such as by an agent.

    Two passes: the first runs with no table and records every segment it could
    not translate, the caller fills those in, and the second runs with the filled
    table to emit the real document.
    """

    name = "handoff"

    def __init__(
        self,
        lang_in: str,
        lang_out: str,
        model: str | None = None,
        *,
        ignore_cache: bool = False,
        envs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # Misses fall through untranslated, so the shared cache must never see them
        # or "translation == original" is memoised for every later run.
        super().__init__(lang_in, lang_out, model, ignore_cache=True, **kwargs)
        envs = envs or {}
        self.table = load_segment_table(envs.get("segments_in"))
        self.misses_path = envs.get("segments_out")
        self._seen: set[str] = set()
        self._lock = threading.Lock()
        if self.misses_path:
            open(self.misses_path, "w", encoding="utf-8").close()

    def do_translate(self, text: str) -> str:
        translation = self.table.get(text)
        if translation is not None:
            return translation
        self._record_miss(text)
        return text

    def _record_miss(self, text: str) -> None:
        """Append one untranslated segment, deduplicated, for the caller to fill in."""
        if not self.misses_path:
            return
        with self._lock:
            if text in self._seen:
                return
            self._seen.add(text)
            with open(self.misses_path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps({"src": text}, ensure_ascii=False) + "\n")


class OpenAITranslator(BaseTranslator):
    """Translate through an OpenAI-compatible API (e.g. 9router, OpenAI, Anthropic)."""

    name = "openai"

    def __init__(
        self,
        lang_in: str,
        lang_out: str,
        model: str | None = None,
        *,
        ignore_cache: bool = False,
        envs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        envs = envs or {}
        # Model from constructor > envs > env var > default
        resolved_model = model or envs.get("llm_model") or os.environ.get("LLM_MODEL", "ag/gemini-3.8-flash-low")
        super().__init__(lang_in, lang_out, resolved_model, ignore_cache=ignore_cache, **kwargs)

        self.base_url = envs.get("llm_base_url") or os.environ.get("LLM_BASE_URL", "http://localhost:20128/v1")
        self.api_key = envs.get("llm_api_key") or os.environ.get("LLM_API_KEY", "")

        if not self.api_key:
            raise ValueError(
                "OpenAI translator requires an API key. "
                "Set LLM_API_KEY in your environment or .env file."
            )

        # Load system prompt
        self.system_prompt = self._load_system_prompt(envs.get("system_prompt"))

        # Load glossary context
        self.glossary_context = self._load_glossary(envs.get("glossary"))

        # Rate limiting
        self._last_request_time = 0.0
        self._min_request_interval = float(envs.get("request_interval", "0.5"))
        self._rate_lock = threading.Lock()

        if OpenAI is None:
            raise ImportError(
                "The 'openai' package is required for the OpenAI translator. "
                "Install it with: pip install openai"
            )
        self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)

        logger.info(
            "OpenAI translator initialized: base_url=%s model=%s",
            self.base_url, self.model,
        )

    def _load_system_prompt(self, path: str | None) -> str:
        """Load system prompt from file or use default."""
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        # Default minimal prompt
        lang_out_name = {"vi": "Vietnamese", "en": "English"}.get(self.lang_out, self.lang_out)
        return (
            f"You are a professional translator. Translate the following text to {lang_out_name}. "
            f"Return ONLY the translated text, no explanations or formatting. "
            f"Preserve any placeholder tags like <b0></b0> exactly as they appear."
        )

    def _load_glossary(self, path: str | None) -> str:
        """Load glossary terms for inclusion in the prompt."""
        if not path or not os.path.isfile(path):
            return ""
        terms = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    en = record.get("en", "")
                    vi = record.get("vi", "")
                    if en and vi:
                        terms.append(f"  {en} = {vi}")
        except Exception as e:
            logger.warning("Failed to load glossary from %s: %s", path, e)
            return ""
        if not terms:
            return ""
        return "\n\nTerminology glossary (use these translations consistently):\n" + "\n".join(terms)

    def _rate_limit(self) -> None:
        """Enforce minimum interval between API requests."""
        with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._min_request_interval:
                time.sleep(self._min_request_interval - elapsed)
            self._last_request_time = time.monotonic()

    def do_translate(self, text: str) -> str:
        """Send text to the OpenAI-compatible API for translation."""
        self._rate_limit()

        system_content = self.system_prompt
        if self.glossary_context:
            system_content += self.glossary_context

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": text},
        ]

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=min(len(text) * 4, 4096),  # Rough estimate
            )
            translated = response.choices[0].message.content
            if not translated or not translated.strip():
                raise RuntimeError("LLM returned empty translation")
            return remove_control_characters(translated.strip())
        except Exception as e:
            if "openai" in type(e).__module__.lower() if hasattr(type(e), '__module__') else False:
                logger.error("OpenAI API error: %s", e)
            raise


ENGINES: dict[str, type[BaseTranslator]] = {
    engine.name: engine for engine in (GoogleTranslator, HandoffTranslator, OpenAITranslator)
}
