"""LLM adapters (NVIDIA NIM OpenAI-compatible API)."""

from ais.llm.nvidia import (
    NvidiaWatchtowerEvaluator,
    openai_client,
    parse_watchtower_llm_json,
    stream_nvidia_chat,
    watchtower_evaluator_from_settings,
)

__all__ = [
    "NvidiaWatchtowerEvaluator",
    "openai_client",
    "parse_watchtower_llm_json",
    "stream_nvidia_chat",
    "watchtower_evaluator_from_settings",
]
