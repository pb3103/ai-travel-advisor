import json
from collections.abc import Callable, Iterator

from openai import OpenAI

from .config import settings

_client = OpenAI(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key)

# Safety cap on tool round-trips per reply, in case a model keeps requesting tools
# instead of ever answering in text.
MAX_TOOL_ROUNDS = 6


def complete_with_tools(
    model: str,
    messages: list[dict],
    tools: list[dict],
    tool_choice: dict | str | None = None,
    max_tokens: int = 4096,
):
    """One-shot (non-streaming) completion — for tools/agents that need their own nested model call.

    max_tokens is capped explicitly (rather than left to the provider's default, which for
    some models is enormous, e.g. 65536) since OpenRouter reserves credit for the full
    max_tokens up front — an unset/huge cap can make a request fail on a low remaining
    balance even though the actual reply would've been far smaller.
    """
    return _client.chat.completions.create(
        model=model, messages=messages, tools=tools, tool_choice=tool_choice, max_tokens=max_tokens
    )


def complete_text(model: str, system: str, message: str, max_tokens: int = 60) -> str:
    """One-shot, tool-free completion for small utility tasks (e.g. title generation)."""
    response = _client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": message}],
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


def stream_chat(
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_handlers: dict[str, Callable[..., dict]] | None = None,
    max_tokens: int = 2048,
) -> Iterator[dict]:
    """Call the model via OpenRouter and yield events as they arrive:
    {"type": "text", "text": str} for reply text, or {"type": "tool_call", "name": str}
    right before a tool is executed — so callers can show progress during a tool call.

    If the model requests a tool call, the corresponding handler is executed and its
    result is fed back in a follow-up call, looping until the model replies with text
    (or MAX_TOOL_ROUNDS is hit).

    max_tokens is capped explicitly per round — see complete_with_tools for why.
    """
    conversation = [{"role": "system", "content": system}, *messages]

    for _ in range(MAX_TOOL_ROUNDS + 1):
        stream = _client.chat.completions.create(
            model=model,
            messages=conversation,
            tools=tools,
            stream=True,
            max_tokens=max_tokens,
        )

        content_parts: list[str] = []
        pending_calls: dict[int, dict] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                yield {"type": "text", "text": delta.content}
            for tool_call in delta.tool_calls or []:
                entry = pending_calls.setdefault(tool_call.index, {"id": "", "name": "", "arguments": ""})
                if tool_call.id:
                    entry["id"] = tool_call.id
                if tool_call.function and tool_call.function.name:
                    entry["name"] += tool_call.function.name
                if tool_call.function and tool_call.function.arguments:
                    entry["arguments"] += tool_call.function.arguments

        if not pending_calls:
            return

        conversation.append(
            {
                "role": "assistant",
                "content": "".join(content_parts) or None,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["name"], "arguments": call["arguments"]},
                    }
                    for call in pending_calls.values()
                ],
            }
        )

        for call in pending_calls.values():
            yield {"type": "tool_call", "name": call["name"]}
            handler = (tool_handlers or {}).get(call["name"])
            if handler is None:
                result = {"error": f"Unknown tool: {call['name']}"}
            else:
                try:
                    arguments = json.loads(call["arguments"] or "{}")
                    result = handler(**arguments)
                except Exception as exc:
                    result = {"error": str(exc)}

            conversation.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
