import json
import pytest
from agents.base_agent import BaseAgent
from orchestrator.session import Session


class _TestAgent(BaseAgent):
    """Minimal concrete subclass for exercising BaseAgent methods."""
    prompt_file = "test_prompt.md"

    def run(self, session: Session) -> None:
        pass


# --- _parse_json: success cases ---

@pytest.mark.unit
@pytest.mark.parametrize("raw", [
    '{"key": "value"}',
    '```json\n{"key": "value"}\n```',
    '```\n{"key": "value"}\n```',
    '  ```json\n{"key": "value"}\n```  ',
    '  {"key": "value"}  ',
])
def test_parse_json_object(raw):
    result = _TestAgent()._parse_json(raw)
    assert result == {"key": "value"}


@pytest.mark.unit
def test_parse_json_array():
    result = _TestAgent()._parse_json('[1, 2, 3]')
    assert result == [1, 2, 3]


@pytest.mark.unit
def test_parse_json_nested_object():
    raw = '{"outer": {"inner": [1, 2]}}'
    result = _TestAgent()._parse_json(raw)
    assert result == {"outer": {"inner": [1, 2]}}


# --- _parse_json: failure cases ---

@pytest.mark.unit
@pytest.mark.parametrize("raw", [
    "not json at all",
    "",
    '{"unclosed": "brace"',
    # prose before the fence: _parse_json only strips fences at the start of the
    # string, so any leading text causes a parse failure
    'Here is the result:\n```json\n{"key": "value"}\n```',
])
def test_parse_json_raises_on_invalid(raw):
    with pytest.raises(json.JSONDecodeError):
        _TestAgent()._parse_json(raw)


# --- _load_prompt ---

@pytest.fixture
def prompt_dir(tmp_path, monkeypatch):
    """Points PROMPTS_DIR at a temp directory and returns it."""
    monkeypatch.setattr("agents.base_agent.PROMPTS_DIR", tmp_path)
    return tmp_path


@pytest.mark.unit
def test_load_prompt_no_kwargs_returns_raw_template(prompt_dir):
    (prompt_dir / "test_prompt.md").write_text("Return only valid JSON.", encoding="utf-8")
    result = _TestAgent()._load_prompt()
    assert result == "Return only valid JSON."


@pytest.mark.unit
def test_load_prompt_substitutes_single_variable(prompt_dir):
    (prompt_dir / "test_prompt.md").write_text("Hello {name}!", encoding="utf-8")
    result = _TestAgent()._load_prompt(name="World")
    assert result == "Hello World!"


@pytest.mark.unit
def test_load_prompt_substitutes_multiple_variables(prompt_dir):
    (prompt_dir / "test_prompt.md").write_text(
        "Analyze {topic} for {actor}.", encoding="utf-8"
    )
    result = _TestAgent()._load_prompt(topic="login", actor="QA engineer")
    assert result == "Analyze login for QA engineer."


@pytest.mark.unit
def test_load_prompt_missing_variable_raises(prompt_dir):
    # _load_prompt only calls format() when kwargs are provided.
    # Passing a wrong key still triggers format(), which raises for the missing placeholder.
    (prompt_dir / "test_prompt.md").write_text("Hello {name}!", encoding="utf-8")
    with pytest.raises(KeyError):
        _TestAgent()._load_prompt(wrong_key="World")


@pytest.mark.unit
def test_load_prompt_escaped_braces_become_literal(prompt_dir):
    # Prompt templates use {{ }} to embed literal braces (e.g. JSON schema examples).
    # str.format() converts {{ → { and }} → } when called.
    (prompt_dir / "test_prompt.md").write_text(
        'Schema: {{"field": "{value}"}}', encoding="utf-8"
    )
    result = _TestAgent()._load_prompt(value="example")
    assert result == 'Schema: {"field": "example"}'


# --- _call ---

@pytest.mark.unit
def test_call_wraps_message_in_user_role(mocker):
    mock_chat = mocker.patch("agents.base_agent.chat", return_value="response")
    _TestAgent()._call(system="sys", user_message="hello", max_tokens=100)
    mock_chat.assert_called_once_with(
        system="sys",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=100,
    )


@pytest.mark.unit
def test_call_default_max_tokens_is_4096(mocker):
    mock_chat = mocker.patch("agents.base_agent.chat", return_value="response")
    _TestAgent()._call(system="sys", user_message="hello")
    _, kwargs = mock_chat.call_args
    assert kwargs["max_tokens"] == 4096


@pytest.mark.unit
def test_call_returns_chat_response(mocker):
    mocker.patch("agents.base_agent.chat", return_value="the answer")
    result = _TestAgent()._call(system="sys", user_message="hello", max_tokens=100)
    assert result == "the answer"
