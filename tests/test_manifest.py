from gino_gate.manifest import classify_tool, filter_manifest


def test_classifies_reported_robinhood_tools():
    assert classify_tool("get_accounts").kind == "read"
    assert classify_tool("get_equity_positions").kind == "read"
    assert classify_tool("get_equity_historicals").kind == "read"
    assert classify_tool("get_option_quotes").kind == "read"
    assert classify_tool("run_scan").kind == "read"
    assert classify_tool("review_equity_order").kind == "review"
    assert classify_tool("place_equity_order").kind == "trade_place"
    assert classify_tool("cancel_equity_order").kind == "trade_cancel"
    assert classify_tool("create_scan").kind == "write"
    assert classify_tool("update_scan_config").kind == "write"
    assert classify_tool("add_to_watchlist").kind == "write"
    assert classify_tool("remove_option_from_watchlist").kind == "write"


def test_read_only_manifest_exposes_only_allowed_read_tools():
    manifest = {"tools": [{"name": "get_accounts"}, {"name": "place_equity_order"}, {"name": "review_equity_order"}]}
    filtered = filter_manifest(manifest, {"get_accounts"})
    assert filtered["exposed"] == [{"name": "get_accounts", "kind": "read", "reason": "read-like tool name"}]
    assert {tool["name"] for tool in filtered["blocked"]} == {"place_equity_order", "review_equity_order"}


def test_confirmed_market_data_reads_can_be_exposed_without_order_tools():
    manifest = {
        "tools": [
            {"name": "get_equity_historicals"},
            {"name": "get_equity_fundamentals"},
            {"name": "get_option_quotes"},
            {"name": "run_scan"},
            {"name": "place_option_order"},
            {"name": "create_watchlist"},
        ]
    }

    filtered = filter_manifest(
        manifest,
        {"get_equity_historicals", "get_equity_fundamentals", "get_option_quotes", "run_scan"},
    )

    assert {tool["name"] for tool in filtered["exposed"]} == {
        "get_equity_historicals",
        "get_equity_fundamentals",
        "get_option_quotes",
        "run_scan",
    }
    assert {tool["name"] for tool in filtered["blocked"]} == {
        "place_option_order",
        "create_watchlist",
    }
