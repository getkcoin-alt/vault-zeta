import json
import pytest

from vault_zeta.mcp_server import create_server


@pytest.fixture
def mcp_server(tmp_path):
    return create_server(str(tmp_path / "test_mcp.db"))


@pytest.mark.asyncio
async def test_mcp_tools_flow(mcp_server):
    tools = await mcp_server.list_tools()
    tool_names = {t.name for t in tools}
    assert "memory_save" in tool_names
    assert "memory_search" in tool_names
    assert "context_pack" in tool_names
    assert "vault_status" in tool_names
    assert "event_append" in tool_names
    assert "mission_save" in tool_names

    # 1. Save memory
    res = await mcp_server.call_tool(
        "memory_save",
        {
            "content": "Operator prefers concise terminal outputs.",
            "kind": "preference",
            "scope": "operator",
            "confidence": 0.95,
        },
    )
    data = json.loads(res.content[0].text)
    assert data["saved"] is True
    assert data["content"] == "Operator prefers concise terminal outputs."
    mem_id = data["id"]

    # 2. Search memory
    res = await mcp_server.call_tool(
        "memory_search",
        {"query": "terminal outputs"},
    )
    search_data = json.loads(res.content[0].text)
    assert search_data["count"] == 1
    assert search_data["memories"][0]["id"] == mem_id

    # 3. Context pack
    res = await mcp_server.call_tool(
        "context_pack",
        {"query": "terminal"},
    )
    pack_data = json.loads(res.content[0].text)
    assert "<vault_memories>" in pack_data["context"]

    # 4. Status
    res = await mcp_server.call_tool("vault_status", {})
    status_data = json.loads(res.content[0].text)
    assert status_data["vault"] == "Vault Zeta"
    assert status_data["memories"] == 1

    # 5. Secret rejection
    res = await mcp_server.call_tool(
        "memory_save",
        {"content": "API key is sk-1234567890abcdef12345678"},
    )
    secret_data = json.loads(res.content[0].text)
    assert secret_data["saved"] is False
    assert secret_data["error"] == "secret_rejected"
