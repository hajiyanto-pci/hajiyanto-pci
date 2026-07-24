"""Tests agent planner (understand → plan)."""

from __future__ import annotations

from screener.agent import format_understanding, understand


def test_agent_ihsg_natural():
    for phrase in [
        "dapatkah cek potensi ihsg",
        "Dapatkh cek potensi ihsg",
        "bagaimana ihsg kedepan",
        "tolong analisa makro hari ini",
    ]:
        plan = understand(phrase, prefer_llm=False)
        assert plan.kind == "ihsg", f"{phrase} -> {plan.kind}"
        assert plan.understanding
        assert "IHSG" in format_understanding(plan) or "ihsg" in plan.understanding.lower()


def test_agent_screen():
    plan = understand("cek saham potensi kemarin", prefer_llm=False)
    assert plan.kind == "screen"
    assert plan.screen_label == "kemarin"
    assert plan.confidence >= 0.7


def test_agent_stock():
    plan = understand("please cek saham emtk", prefer_llm=False)
    assert plan.kind == "stock"
    assert plan.stock_code == "EMTK"


def test_agent_clarify_on_garbage():
    plan = understand("halo apa kabar cuaca", prefer_llm=False)
    assert plan.kind in {"clarify", "unknown"}
    assert plan.clarify_question or plan.needs_clarify


if __name__ == "__main__":
    test_agent_ihsg_natural()
    test_agent_screen()
    test_agent_stock()
    test_agent_clarify_on_garbage()
    print("OK: agent planner tests passed")
