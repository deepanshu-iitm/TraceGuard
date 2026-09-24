from backend.config import settings
from backend.investigate.explain import explain_answer
from backend.models.answer import Answer
from tests.test_answer import EXAMPLE


def test_explain_leaves_answer_unchanged_without_a_key() -> None:
    answer = Answer.model_validate(EXAMPLE)
    assert explain_answer(answer) == answer


def test_explain_rewrites_summary_and_sar_narrative(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(
        "backend.investigate.explain.complete",
        lambda _prompt: (
            {
                "summary": "Card testing on a new Android device, denied by the customer.",
                "sar_narrative": "Three small online tests then a larger purchase on C00377-K1.",
            },
            42,
        ),
    )
    original = Answer.model_validate(EXAMPLE)
    explained = explain_answer(original)

    assert explained.case.summary == "Card testing on a new Android device, denied by the customer."
    assert explained.sar.narrative == "Three small online tests then a larger purchase on C00377-K1."
    assert explained.tokens == original.tokens + 42
    assert explained.case.verdict == original.case.verdict
    assert explained.next_best_actions == original.next_best_actions
    assert explained.sar.file is True
    assert explained.sar.total_amount_usd == original.sar.total_amount_usd


def test_explain_keeps_original_text_if_the_model_call_fails(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(
        "backend.investigate.explain.complete",
        lambda _prompt: (_ for _ in ()).throw(OSError("offline")),
    )
    answer = Answer.model_validate(EXAMPLE)
    assert explain_answer(answer) == answer
