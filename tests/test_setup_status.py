from gino_gate.policy import PolicyEnvelope
from gino_gate.setup_status import assess_manifest_for_read_only_visit


def test_assess_manifest_ready_when_read_and_trade_tools_present():
    policy = PolicyEnvelope.from_dict(
        {
            "policy_id": "test",
            "mode": "read_only",
            "allowed_tools_by_mode": {"read_only": ["get_accounts"]},
        }
    )
    manifest = {"tools": [{"name": "get_accounts"}, {"name": "place_equity_order"}]}

    status = assess_manifest_for_read_only_visit(manifest, policy)

    assert status.ready_for_visit is True
    assert status.manifest_loaded is True
    assert status.read_tools == ["get_accounts"]
    assert status.blocked_tools == ["place_equity_order"]
    assert status.blockers == []


def test_assess_manifest_blocks_without_manifest():
    policy = PolicyEnvelope.from_dict(
        {
            "policy_id": "test",
            "mode": "read_only",
            "allowed_tools_by_mode": {"read_only": ["get_accounts"]},
        }
    )

    status = assess_manifest_for_read_only_visit(None, policy)

    assert status.ready_for_visit is False
    assert status.manifest_loaded is False
    assert status.blockers == ["no_manifest_loaded"]
