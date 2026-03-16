"""Groq cloud API client for free LLM inference."""

from __future__ import annotations

import os
from typing import Optional, cast

try:
    from groq import Groq

    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False


class GroqClient:
    """Client for Groq cloud API (free LLM inference)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.3-70b-versatile",  # Updated to current model
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ):
        """Initialize Groq client.

        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
            model: Model name to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        if not GROQ_AVAILABLE:
            raise RuntimeError("Groq is not available. Install with: pip install groq")

        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY environment variable not set. "
                "Get your free API key at https://console.groq.com"
            )

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.client = Groq(api_key=self.api_key)

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text using Groq.

        Args:
            prompt: The user prompt
            system: Optional system prompt
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Returns:
            Generated text
        """
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )

        return cast(str, response.choices[0].message.content)

    def check_health(self) -> bool:
        """Check if the Groq API is accessible.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            self.generate("Hello", max_tokens=5)
            return True
        except Exception:
            return False

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from anthropic import Anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class OpenAIClient:
    """Client for OpenAI API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ):
        """Initialize OpenAI client."""
        if not OPENAI_AVAILABLE:
            raise RuntimeError("OpenAI is not available. Install with: pip install openai")

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable not set.")

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = OpenAI(api_key=self.api_key)

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text using OpenAI."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        return cast(str, response.choices[0].message.content)

    def check_health(self) -> bool:
        """Check if the OpenAI API is accessible."""
        try:
            self.generate("Hello", max_tokens=5)
            return True
        except Exception:
            return False


class AnthropicClient:
    """Client for Anthropic API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20240620",
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ):
        """Initialize Anthropic client."""
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("Anthropic is not available. Install with: pip install anthropic")

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = Anthropic(api_key=self.api_key)

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text using Anthropic."""
        response = self.client.messages.create(
            model=self.model,
            system=system if system else None,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        return cast(str, response.content[0].text)

    def check_health(self) -> bool:
        """Check if the Anthropic API is accessible."""
        try:
            self.generate("Hello", max_tokens=5)
            return True
        except Exception:
            return False
