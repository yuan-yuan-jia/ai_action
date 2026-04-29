import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    """Token usage statistics for a single LLM request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """Unified response from any LLM provider.

    Attributes:
        content: The text content of the model's reply.
        usage: Token consumption breakdown.
        provider: Provider name (deepseek / qwen / openai).
        model: The specific model that generated the response.
        cost_usd: Estimated cost in USD for this request.
    """

    content: str
    usage: Usage = field(default_factory=Usage)
    provider: str = ""
    model: str = ""
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

PROVIDER_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-v4-pro",
        "env_api_key": "DEEPSEEK_API_KEY",
        "price_input_per_mtok": 0.27,
        "price_output_per_mtok": 1.10,
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "env_api_key": "DASHSCOPE_API_KEY",
        "price_input_per_mtok": 2.00,
        "price_output_per_mtok": 6.00,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "env_api_key": "OPENAI_API_KEY",
        "price_input_per_mtok": 2.50,
        "price_output_per_mtok": 10.00,
    },
}

_DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()
_DEFAULT_MODEL_ENV = os.getenv("LLM_MODEL")
_REQUEST_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))

if _DEFAULT_PROVIDER not in PROVIDER_CONFIG:
    raise ValueError(
        f"Unknown LLM_PROVIDER '{_DEFAULT_PROVIDER}'. "
        f"Supported: {list(PROVIDER_CONFIG.keys())}"
    )


def _resolve_api_key(provider_name: str) -> str:
    """Look up the API key for a provider.

    Checks the provider-specific env var first, then the generic
    ``LLM_API_KEY`` as a fallback.

    Args:
        provider_name: One of ``deepseek`` / ``qwen`` / ``openai``.

    Returns:
        The API key string.

    Raises:
        ValueError: If no API key is found.
    """
    cfg = PROVIDER_CONFIG[provider_name]
    key = os.getenv(cfg["env_api_key"]) or os.getenv("LLM_API_KEY", "")
    if not key:
        raise ValueError(
            f"API key not set. Please set {cfg['env_api_key']} or LLM_API_KEY."
        )
    return key


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Abstract interface for LLM backends.

    All concrete providers must implement ``chat`` and ``estimate_cost``.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat-completion request and return a unified response.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            model: Override the default model for this provider.
            temperature: Sampling temperature (0-2).
            max_tokens: Maximum tokens in the response.

        Returns:
            An ``LLMResponse`` with content, usage stats, and cost estimate.
        """
        ...

    @abstractmethod
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate the USD cost of a request.

        Args:
            prompt_tokens: Number of input tokens.
            completion_tokens: Number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        ...


# ---------------------------------------------------------------------------
# OpenAI-compatible HTTP implementation
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider(LLMProvider):
    """Concrete provider backed by any OpenAI-compatible HTTP API.

    Works with DeepSeek, Qwen (DashScope), OpenAI, and any self-hosted
    endpoints that expose the ``/chat/completions`` path.

    Args:
        provider_name: Key into ``PROVIDER_CONFIG`` (deepseek / qwen / openai).
        api_key: Override the env-var-derived API key.
        http_client: An optional pre-configured ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        provider_name: str | None = None,
        *,
        api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._name = provider_name or _DEFAULT_PROVIDER
        if self._name not in PROVIDER_CONFIG:
            raise ValueError(f"Unknown provider: {self._name}")

        self._cfg = PROVIDER_CONFIG[self._name]
        self._api_key = api_key or _resolve_api_key(self._name)
        self._http = http_client

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def default_model(self) -> str:
        return self._cfg["default_model"]

    @property
    def base_url(self) -> str:
        return self._cfg["base_url"]

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        model_name = model or _DEFAULT_MODEL_ENV or self._cfg["default_model"]
        url = f"{self._cfg['base_url']}/chat/completions"
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        logger.info("Calling %s model=%s", url, model_name)
        logger.debug("Payload: %s", payload)

        client = self._http or httpx.AsyncClient()
        try:
            own_client = self._http is None
            if own_client:
                client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

            resp = await client.post(url, headers=self._auth_headers(), json=payload)
            resp.raise_for_status()
            body = resp.json()
        finally:
            if own_client:
                await client.aclose()

        choice = body["choices"][0]
        content = choice["message"]["content"]
        usage_raw = body.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            total_tokens=usage_raw.get("total_tokens", 0),
        )
        cost = self.estimate_cost(usage.prompt_tokens, usage.completion_tokens)

        logger.info(
            "Response: %d tokens, cost=$%.6f, model=%s",
            usage.total_tokens,
            cost,
            body.get("model", model_name),
        )

        return LLMResponse(
            content=content,
            usage=usage,
            provider=self._name,
            model=body.get("model", model_name),
            cost_usd=cost,
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        input_price = self._cfg["price_input_per_mtok"] / 1_000_000
        output_price = self._cfg["price_output_per_mtok"] / 1_000_000
        return prompt_tokens * input_price + completion_tokens * output_price

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token-count estimate (≈4 chars per token for English/Chinese).

        Args:
            text: Arbitrary text.

        Returns:
            Approximate token count.
        """
        return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Global helper — lazy singleton
# ---------------------------------------------------------------------------

_provider_instance: LLMProvider | None = None


def _get_provider() -> LLMProvider:
    """Return a cached provider instance based on ``LLM_PROVIDER`` env var."""
    global _provider_instance  # noqa: PLW0603
    if _provider_instance is None:
        _provider_instance = OpenAICompatibleProvider()
        logger.info(
            "Initialised LLM provider: %s (model=%s)",
            _provider_instance.provider_name,  # type: ignore[attr-defined]
            _provider_instance.default_model,  # type: ignore[attr-defined]
        )
    return _provider_instance


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def chat_with_retry(
    messages: list[dict[str, str]] | str,
    *,
    model: str | None = None,
    provider: LLMProvider | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    max_retries: int = _MAX_RETRIES,
) -> LLMResponse:
    """Send a chat request with automatic retry on transient failures.

    Retries up to ``max_retries`` times using exponential backoff
    (1 s, 2 s, 4 s, …).  Non-retryable HTTP status codes (400, 401, 403)
    are raised immediately.

    Args:
        messages: Either a single user prompt string (converted to a
            single-message list) or a list of ``{"role": "...", "content":
            "..."}`` dicts.
        model: Override the default model.
        provider: An existing ``LLMProvider`` instance (uses the global
            singleton when omitted).
        temperature: Sampling temperature.
        max_tokens: Maximum output tokens.
        max_retries: Maximum number of attempts (default from
            ``LLM_MAX_RETRIES`` env or 3).

    Returns:
        ``LLMResponse`` with the model output, usage stats, and cost.

    Raises:
        httpx.HTTPStatusError: For non-retryable HTTP errors.
        RuntimeError: When all retry attempts are exhausted.
    """
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]

    llm = provider or _get_provider()
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            return await llm.chat(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 401, 403):
                logger.error(
                    "Non-retryable error %d: %s",
                    exc.response.status_code,
                    exc,
                )
                raise
            last_exc = exc
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc

        delay = 2**attempt
        logger.warning(
            "Attempt %d/%d failed: %s. Retrying in %ds...",
            attempt + 1,
            max_retries,
            last_exc,
            delay,
        )
        await asyncio.sleep(delay)

    raise RuntimeError(
        f"All {max_retries} retry attempts failed. Last error: {last_exc}"
    ) from last_exc


def quick_chat(
    prompt: str,
    *,
    model: str | None = None,
    provider: LLMProvider | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """One-shot synchronous convenience wrapper around :func:`chat_with_retry`.

    Args:
        prompt: A plain-text user prompt.
        model: Override the default model.
        provider: An existing ``LLMProvider`` instance.
        temperature: Sampling temperature.
        max_tokens: Maximum output tokens.

    Returns:
        The model's text response (content only).
    """
    return asyncio.run(
        chat_with_retry(
            prompt,
            model=model,
            provider=provider,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    ).content


async def quick_chat_async(
    prompt: str,
    *,
    model: str | None = None,
    provider: LLMProvider | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Async variant of :func:`quick_chat`.

    Args:
        prompt: A plain-text user prompt.
        model: Override the default model.
        provider: An existing ``LLMProvider`` instance.
        temperature: Sampling temperature.
        max_tokens: Maximum output tokens.

    Returns:
        The model's text response (content only).
    """
    resp = await chat_with_retry(
        prompt,
        model=model,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.content


# ---------------------------------------------------------------------------
# Smoke test (requires a valid API key)
# ---------------------------------------------------------------------------


async def _smoke_test(provider_key: str) -> None:
    """Run a minimal round-trip smoke test against a provider.

    Args:
        provider_key: Key into ``PROVIDER_CONFIG``.
    """
    llm = OpenAICompatibleProvider(provider_key)
    resp = await chat_with_retry(
        [{"role": "user", "content": "Say 'hello' in exactly one word."}],
        provider=llm,
        max_tokens=32,
    )
    logger.info(
        "Smoke test [%s] OK: %r (cost=$%.6f)",
        provider_key,
        resp.content,
        resp.cost_usd,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    provider_name = _DEFAULT_PROVIDER
    default_model = PROVIDER_CONFIG[provider_name]["default_model"]
    logger.info(
        "Provider: %s | Model: %s",
        provider_name,
        _DEFAULT_MODEL_ENV or default_model,
    )

    # Quick sync test
    print(">>> quick_chat test:")
    result = quick_chat("用一句话介绍 Python 语言。", max_tokens=128)
    print(result)
    print()

    # Async smoke tests for all available providers
    if os.getenv("RUN_ALL_SMOKE"):
        asyncio.run(_smoke_test("deepseek"))
        asyncio.run(_smoke_test("qwen"))
        asyncio.run(_smoke_test("openai"))

    logger.info("All tests completed.")
