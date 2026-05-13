import anthropic
from config import ANTHROPIC_API_KEY, DEFAULT_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def chat(
    system: str,
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
) -> str:
    response = _client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )
    return response.content[0].text
