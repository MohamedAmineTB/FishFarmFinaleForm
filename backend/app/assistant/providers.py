"""LLM provider layer: one small interface, three implementations.

    stream_chat(system, messages, tools, max_tokens) -> AsyncIterator[event]

events: {"type": "text", "text": ...}, {"type": "tool_use", "id", "name", "input"},
        {"type": "usage", "input": n, "output": n, "cache_read": n}, {"type": "stop", "reason": ...}

Messages use the Anthropic content-block format (text / tool_use / tool_result); the
OpenAI-compatible provider converts them. Selected with LLM_PROVIDER; without an API key the
deterministic mock is used automatically (demo mode).
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..config import get_settings

# USD per million tokens (input, output) used for the cost estimate on the AI Ops page
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}


def estimate_cost(model: str, tokens_in: int, tokens_out: int, cache_read: int = 0) -> float:
    pi, po = PRICES.get(model, (0.0, 0.0))
    return round(((tokens_in - cache_read) * pi + cache_read * pi * 0.1 + tokens_out * po) / 1_000_000, 6)


class LLMProvider:
    name = "base"
    model = ""

    async def stream_chat(
        self, system: list[dict], messages: list[dict], tools: list[dict], max_tokens: int
    ) -> AsyncIterator[dict]:  # pragma: no cover - interface
        raise NotImplementedError
        yield {}


class AnthropicProvider(LLMProvider):
    """Claude through the official `anthropic` SDK, streaming, with the system prompt cached."""

    name = "anthropic"

    def __init__(self, model: str, api_key: str):
        import anthropic

        self.anthropic = anthropic
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def stream_chat(self, system, messages, tools, max_tokens):
        sys_blocks = [dict(b) for b in system]
        # cache the stable part (prompt + tool definitions come before it): the farm index changes per request
        sys_blocks[0]["cache_control"] = {"type": "ephemeral"}
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=sys_blocks,
            messages=messages,
            tools=tools,
            # short, grounded answers: thinking off keeps the 800-token output budget for the answer itself
            thinking={"type": "disabled"},
        ) as stream:
            async for event in stream:
                if event.type == "text":
                    yield {"type": "text", "text": event.text}
            final = await stream.get_final_message()
        for block in final.content:
            if block.type == "tool_use":
                yield {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
        u = final.usage
        yield {
            "type": "usage",
            "input": (u.input_tokens or 0) + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
            "output": u.output_tokens or 0,
            "cache_read": u.cache_read_input_tokens or 0,
        }
        yield {"type": "stop", "reason": final.stop_reason}


class OpenAICompatProvider(LLMProvider):
    """Any OpenAI-compatible chat endpoint (OpenAI, Ollama for offline use), streamed with httpx."""

    name = "openai_compat"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @staticmethod
    def _convert(system: list[dict], messages: list[dict]) -> list[dict]:
        out: list[dict[str, Any]] = [{"role": "system", "content": "\n\n".join(b["text"] for b in system)}]
        for m in messages:
            if isinstance(m["content"], str):
                out.append({"role": m["role"], "content": m["content"]})
                continue
            texts = [b["text"] for b in m["content"] if b["type"] == "text"]
            calls = [b for b in m["content"] if b["type"] == "tool_use"]
            results = [b for b in m["content"] if b["type"] == "tool_result"]
            if m["role"] == "assistant":
                msg: dict[str, Any] = {"role": "assistant", "content": "".join(texts) or None}
                if calls:
                    msg["tool_calls"] = [
                        {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["input"])}}
                        for c in calls
                    ]
                out.append(msg)
            else:
                for r in results:
                    out.append({"role": "tool", "tool_call_id": r["tool_use_id"], "content": r["content"]})
                if texts:
                    out.append({"role": "user", "content": "\n".join(texts)})
        return out

    async def stream_chat(self, system, messages, tools, max_tokens):
        body = {
            "model": self.model,
            "stream": True,
            "max_tokens": max_tokens,
            "messages": self._convert(system, messages),
            "tools": [
                {
                    "type": "function",
                    "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
                }
                for t in tools
            ],
            "stream_options": {"include_usage": True},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        calls: dict[int, dict] = {}
        usage = {"input": 0, "output": 0, "cache_read": 0}
        reason = "end_turn"
        async with (
            httpx.AsyncClient(timeout=120) as client,
            client.stream("POST", f"{self.base_url}/chat/completions", json=body, headers=headers) as r,
        ):
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data: ") or line.strip() == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                if chunk.get("usage"):
                    usage["input"] = chunk["usage"].get("prompt_tokens", 0)
                    usage["output"] = chunk["usage"].get("completion_tokens", 0)
                for ch in chunk.get("choices", []):
                    d = ch.get("delta", {})
                    if d.get("content"):
                        yield {"type": "text", "text": d["content"]}
                    for tc in d.get("tool_calls", []) or []:
                        c = calls.setdefault(tc.get("index", 0), {"id": tc.get("id"), "name": "", "args": ""})
                        c["id"] = tc.get("id") or c["id"]
                        f = tc.get("function", {})
                        c["name"] += f.get("name") or ""
                        c["args"] += f.get("arguments") or ""
                    if ch.get("finish_reason"):
                        reason = ch["finish_reason"]
        for i, c in sorted(calls.items()):
            try:
                args = json.loads(c["args"] or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_use", "id": c["id"] or f"call_{i}", "name": c["name"], "input": args}
        yield {"type": "usage", **usage}
        yield {"type": "stop", "reason": reason}


def get_provider() -> LLMProvider:
    s = get_settings()
    p = s.effective_llm_provider
    if p == "anthropic" and s.anthropic_api_key:
        return AnthropicProvider(s.llm_model, s.anthropic_api_key)
    if p == "openai_compat":
        return OpenAICompatProvider(s.openai_base_url, s.openai_api_key, s.openai_model)
    from .mock import MockProvider

    return MockProvider()
