import pytest
from pydantic import BaseModel

from app.providers.mock import MockTextLLM
from app.services import prompts
from app.services.llm import LLMOutputError, structured

REQUIRED = ["analyze_source", "propose_themes", "propose_formats", "plan_pages", "character_brief", "character_edit",
            "page_image_prompt", "story_text", "qa_content", "qa_vision_check", "planning_prompt_export"]


def test_all_required_prompts_exist_and_are_versioned():
    names = prompts.list_prompts()
    for n in REQUIRED:
        assert n in names
        assert prompts.prompt_version(n) >= 1


@pytest.mark.parametrize("name", ["analyze_source", "propose_themes", "propose_formats", "plan_pages", "character_brief", "story_text"])
def test_prompts_touching_reference_include_originality_rule(name):
    assert "{originality_rule}" in prompts.load_prompt(name)


def test_fill_keeps_json_braces_and_injects_rules():
    out = prompts.fill('Rule: {originality_rule}\nReturn {"a": 1} for {x}', {"x": "X"})
    assert '{"a": 1}' in out and "ORIGINALITY RULE" in out and out.endswith("for X")


def test_missing_placeholder_raises():
    with pytest.raises(prompts.PromptError):
        prompts.render("propose_themes", {})


class Out(BaseModel):
    value: int


def test_structured_repairs_once():
    calls = []

    def bad_then_good(prompt, meta):
        calls.append(meta["attempt"])
        return {"value": "nope"} if meta["attempt"] == 0 else {"value": 3}

    llm = MockTextLLM({"t": bad_then_good})
    out = structured("t", {}, Out, text_llm=llm, prompt="give value")
    assert out.value == 3 and calls == [0, 1]
    assert "previous answer was not valid" in llm.calls[1]["prompt"]


def test_structured_fails_after_one_repair():
    llm = MockTextLLM({"t": "not json at all"})
    with pytest.raises(LLMOutputError):
        structured("t", {}, Out, text_llm=llm, prompt="p")
    assert len(llm.calls) == 2


def test_structured_accepts_fenced_json_text():
    llm = MockTextLLM({"t": 'Sure!\n```json\n{"value": 7}\n```'})
    assert structured("t", {}, Out, text_llm=llm, prompt="p").value == 7
