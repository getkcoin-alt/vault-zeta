import json
import pytest

from vault_zeta.mcp_server import create_server


@pytest.mark.asyncio
async def test_mcp_phase1_tools(tmp_path):
    server = create_server(str(tmp_path / "mcp_phase1.db"))

    # 1. Save initial memory
    res_save = await server.call_tool(
        "memory_save",
        {
            "content": "Deployment target is AWS us-east-1",
            "scope": "infra",
            "confidence": 0.85,
        },
    )
    data_save = json.loads(res_save.content[0].text)
    assert data_save["saved"] is True
    m1_id = data_save["id"]

    # 2. Link entity
    res_link = await server.call_tool(
        "entity_link",
        {
            "memory_id": m1_id,
            "entity_name": "AWS us-east-1",
            "entity_type": "region",
            "relationship": "targets",
        },
    )
    data_link = json.loads(res_link.content[0].text)
    assert data_link["linked"] is True
    assert data_link["entity_name"] == "AWS us-east-1"

    # 3. Retrieve memories by entity
    res_ent = await server.call_tool(
        "entity_get_memories",
        {"entity_name": "AWS us-east-1"},
    )
    data_ent = json.loads(res_ent.content[0].text)
    assert data_ent["count"] == 1
    assert data_ent["memories"][0]["id"] == m1_id

    # 4. Supersede memory
    res_super = await server.call_tool(
        "memory_supersede",
        {
            "old_memory_id": m1_id,
            "new_content": "Deployment target is GCP us-central1",
            "reason": "Multi-region migration",
            "confidence": 0.95,
        },
    )
    data_super = json.loads(res_super.content[0].text)
    assert data_super["superseded"] is True
    m2_id = data_super["new_memory"]["id"]
    assert data_super["new_memory"]["supersedes_id"] == m1_id

    # 5. Check memory lineage
    res_lin = await server.call_tool(
        "memory_lineage",
        {"memory_id": m2_id},
    )
    data_lin = json.loads(res_lin.content[0].text)
    assert data_lin["chain_length"] == 2
    assert [m["id"] for m in data_lin["lineage"]] == [m1_id, m2_id]

    # 6. Check search explain
    res_exp = await server.call_tool(
        "memory_search_explain",
        {"query": "Deployment target GCP", "scope": "infra"},
    )
    data_exp = json.loads(res_exp.content[0].text)
    assert data_exp["count"] == 1
    top = data_exp["results"][0]
    assert top["memory"]["id"] == m2_id
    assert "explanation" in top
    assert top["final_score"] > 0
