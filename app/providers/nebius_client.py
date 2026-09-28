import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_NVIDIA_MODELS = [
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
    "meta-llama/Meta-Llama-3.1-70B-Instruct",
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "Qwen/Qwen2.5-Coder-32B-Instruct",
    "mistralai/Mistral-Large-Instruct-2407",
]


class NebiusClient:
    """OpenAI-compatible client for Nebius Token Factory and NVIDIA models."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.nebius.api_key
        self.base_url = base_url or settings.nebius.base_url
        self.default_model = default_model or settings.nebius.default_model
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    @property
    def raw(self) -> AsyncOpenAI:
        return self.client

    async def create_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> Any:
        target_model = model or self.default_model
        try:
            response = await self.client.chat.completions.create(
                model=target_model,
                messages=messages,  # type: ignore
                tools=tools if tools else None,  # type: ignore
                tool_choice="auto" if tools else None,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response
        except Exception as exc:
            logger.error(f"[NebiusClient] Error during chat completion ({target_model}): {exc}")
            raise

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[Any, None]:
        target_model = model or self.default_model
        stream = await self.client.chat.completions.create(
            model=target_model,
            messages=messages,  # type: ignore
            tools=tools if tools else None,  # type: ignore
            tool_choice="auto" if tools else None,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            yield chunk

    async def check_health(self) -> Dict[str, Any]:
        """Verify connectivity to Nebius endpoint."""
        try:
            models_response = await self.client.models.list()
            model_ids = [m.id for m in models_response.data]
            return {
                "ok": True,
                "message": "Connected to Nebius Token Factory successfully",
                "available_models": model_ids,
            }
        except Exception as exc:
            return {
                "ok": False,
                "message": f"Failed to connect to Nebius API ({self.base_url}): {exc}",
            }


default_nebius_client = NebiusClient()
