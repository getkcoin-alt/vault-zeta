import json
import pytest

from vault_zeta.mcp_server import create_server


@pytest.mark.asyncio
async def test_mcp_phase2_task_tools(tmp_path):
    server = create_server(str(tmp_path / "mcp_phase2.db"))

    # 1. Create task A
    res_a = await server.call_tool(
        "task_create",
        {
            "mission_id": "m_web",
            "task_id": "scrape_docs",
            "title": "Scrape documentation",
        },
    )
    data_a = json.loads(res_a.content[0].text)
    assert data_a["created"] is True
    assert data_a["status"] == "pending"

    # 2. Create task B depending on A
    res_b = await server.call_tool(
        "task_create",
        {
            "mission_id": "m_web",
            "task_id": "parse_html",
            "title": "Parse HTML structure",
            "dependencies": ["scrape_docs"],
        },
    )
    data_b = json.loads(res_b.content[0].text)
    assert data_b["created"] is True
    assert data_b["status"] == "blocked"

    # 3. List tasks
    res_list = await server.call_tool("task_list", {"mission_id": "m_web"})
    data_list = json.loads(res_list.content[0].text)
    assert data_list["count"] == 2

    # 4. Update task A to completed -> cascades unblocking to task B
    res_up = await server.call_tool(
        "task_update",
        {
            "mission_id": "m_web",
            "task_id": "scrape_docs",
            "status": "completed",
            "result": {"pages": 12},
        },
    )
    data_up = json.loads(res_up.content[0].text)
    assert data_up["updated"] is True
    assert data_up["status"] == "completed"

    # 5. Check resumption plan
    res_plan = await server.call_tool("mission_resumption_plan", {"mission_id": "m_web"})
    data_plan = json.loads(res_plan.content[0].text)
    assert "scrape_docs" in data_plan["completed_tasks"]
    assert "parse_html" in data_plan["ready_tasks"]

    # 6. Replay events
    res_rep = await server.call_tool("mission_replay_events", {"mission_id": "m_web"})
    data_rep = json.loads(res_rep.content[0].text)
    assert data_rep["is_consistent"] is True

    # 7. Compact mission
    res_comp = await server.call_tool("mission_compact", {"mission_id": "m_web"})
    data_comp = json.loads(res_comp.content[0].text)
    assert data_comp["compacted"] is True
