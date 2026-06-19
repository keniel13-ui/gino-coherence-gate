import pytest

from gino_gate.manifest_capture import ManifestCaptureError, normalize_manifest_payload


def test_normalizes_json_rpc_tools_list_response():
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "tools": [
                {"name": "get_accounts", "description": "List accounts"},
                {"name": "place_equity_order", "inputSchema": {"type": "object"}},
            ]
        },
    }

    manifest = normalize_manifest_payload(payload)

    assert manifest["tools"][0]["name"] == "get_accounts"
    assert manifest["tools"][0]["description"] == "List accounts"
    assert manifest["tools"][1]["name"] == "place_equity_order"


def test_normalizes_existing_manifest_shape():
    payload = {"tools": [{"name": "get_portfolio"}, "search"]}

    assert normalize_manifest_payload(payload) == {
        "tools": [{"name": "get_portfolio"}, {"name": "search"}]
    }


def test_normalizes_wrapped_server_export():
    payload = {
        "servers": {
            "robinhood-trading": {
                "tools": [{"name": "get_equity_quotes"}, {"name": "cancel_equity_order"}]
            }
        }
    }

    manifest = normalize_manifest_payload(payload)

    assert [tool["name"] for tool in manifest["tools"]] == [
        "get_equity_quotes",
        "cancel_equity_order",
    ]


def test_rejects_payload_without_tools():
    with pytest.raises(ManifestCaptureError, match="no tools list"):
        normalize_manifest_payload({"result": {"resources": []}})


def test_rejects_tool_without_name():
    with pytest.raises(ManifestCaptureError, match="lacks a name"):
        normalize_manifest_payload({"tools": [{"description": "missing name"}]})
