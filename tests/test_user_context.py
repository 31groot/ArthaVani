from finance_agent.user_context import get_current_user_id, user_scope


def test_user_scope_is_isolated():
    assert get_current_user_id() is None

    with user_scope("user-1"):
        assert get_current_user_id() == "user-1"

    assert get_current_user_id() is None
