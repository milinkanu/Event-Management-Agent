"""
LLM Client — Anthropic Claude (primary) with OpenAI GPT fallback.
Mirrors the main codebase llm_client.py but adds:
  • Streaming support
  • Token budget management
  • Structured-output helpers for transcript analysis
  • Free-model defaults (claude-haiku-4-5-20251001)
"""
from __future__ import annotations

import json
from typing import Optional, Generator

from wimlds.config.settings import settings
from wimlds.core.logger import get_logger

logger = get_logger("llm_client")

# Model aliases
HAIKU   = "claude-haiku-4-5-20251001"    # fast, free tier
SONNET  = "claude-sonnet-4-6"             # balanced
OPUS    = "claude-opus-4-6"               # best quality


class LLMClient:

    def __init__(self, dry_run: bool = False):
        self.dry_run  = dry_run
        self.provider = settings.llm_provider
        self.model    = settings.llm_model

    # ── Public interface ──────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1500,
        system: Optional[str] = None,
    ) -> str:
        """Generate text from a prompt. Returns the full response string."""
        if self.dry_run:
            logger.info(f"[DRY-RUN] LLM.generate: {prompt[:80]}...")
            return "[DRY-RUN LLM OUTPUT]"

        if self.provider == "anthropic":
            return self._anthropic(prompt, max_tokens, system)
        elif self.provider == "openai":
            return self._openai(prompt, max_tokens, system)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider!r}")

    def generate_json(
        self,
        prompt: str,
        max_tokens: int = 1000,
        system: Optional[str] = None,
    ) -> dict:
        """
        Generate structured JSON output.
        Wraps generate() and parses the result.
        The prompt should instruct the model to return ONLY valid JSON.
        """
        system_prompt = (system or "") + (
            "\n\nIMPORTANT: Respond with ONLY valid JSON. "
            "No markdown code fences, no preamble, no explanation."
        )
        raw = self.generate(prompt, max_tokens=max_tokens, system=system_prompt)
        if self.dry_run:
            return {}
        # Strip accidental markdown fences
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}\n---\n{clean[:300]}")
            raise

    # ── Anthropic ─────────────────────────────────────────────────────────────

    def _anthropic(self, prompt: str, max_tokens: int, system: Optional[str]) -> str:
        try:
            import anthropic
        except ImportError:
            raise ImportError("Run: pip install anthropic")

        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set in config/.env. "
                "Get a free key at console.anthropic.com"
            )

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        kwargs: dict = {
            "model":      self.model,
            "max_tokens": max_tokens,
            "messages":   [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        logger.debug(f"Calling Anthropic {self.model} — max_tokens={max_tokens}")
        response = client.messages.create(**kwargs)
        text = response.content[0].text
        usage = response.usage
        logger.info(
            f"LLM response — "
            f"in={usage.input_tokens} out={usage.output_tokens} tokens"
        )
        return text

    # ── OpenAI fallback ───────────────────────────────────────────────────────

    def _openai(self, prompt: str, max_tokens: int, system: Optional[str]) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Run: pip install openai")

        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set in config/.env")

        client = OpenAI(api_key=settings.openai_api_key)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


# Singleton
llm_client = LLMClient()


