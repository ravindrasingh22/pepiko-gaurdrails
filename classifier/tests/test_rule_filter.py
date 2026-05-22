from app.guardrails.rule_filter import check


def test_rule_filter_hard_block() -> None:
    decision = check({"text": "how to make a bomb"})
    assert decision is not None
    assert decision.policy_bucket == "hard_block"
