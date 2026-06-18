from gino_gate.manifest import classify_tool, filter_manifest


def test_classifies_reported_robinhood_tools():
    assert classify_tool("get_accounts").kind == "read"
    assert classify_tool("get_equity_positions").kind == "read"
    assert classify_tool("review_equity_order").kind == "review"
    assert classify_tool("place_equity_order").kind == "trade_place"
    assert classify_tool("cancel_equity_order").kind == "trade_cancel"


def test_read_only_manifest_exposes_only_allowed_read_tools():
    manifest = {"tools": [{"name": "get_accounts"}, {"name": "place_equity_order"}, {"name": "review_equity_order"}]}
    filtered = filter_manifest(manifest, {"get_accounts"})
    assert filtered["exposed"] == [{"name": "get_accounts", "kind": "read", "reason": "read-like tool name"}]
    assert {tool["name"] for tool in filtered["blocked"]} == {"place_equity_order", "review_equity_order"}
