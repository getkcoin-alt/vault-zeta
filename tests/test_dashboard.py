import json
import sqlite3

import pytest
from starlette.testclient import TestClient

from vault_zeta import VaultZetaStore
from vault_zeta.dashboard import create_dashboard


LOGIN = ("owner", "synthetic-dashboard-test-password")


def test_dashboard_requires_its_own_login_and_uses_a_read_only_connection(tmp_path):
    database = tmp_path / "vault.db"
    with VaultZetaStore(database):
        app = create_dashboard(database, username=LOGIN[0], password=LOGIN[1])
        with TestClient(app) as client:
            assert client.get("/dashboard/").status_code == 401
            assert client.get("/dashboard/", headers={"Authorization": "Bearer agent-token"}).status_code == 401
            assert client.get("/dashboard/", auth=("guest", LOGIN[1])).status_code == 401
            response = client.get("/dashboard/", auth=LOGIN)
            assert response.status_code == 200 and "No memories saved yet." in response.text
            assert response.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
            assert client.post("/dashboard/memories", auth=LOGIN).status_code == 405
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                app.state.store.db.execute("DELETE FROM memories")


def test_dashboard_shows_live_memories_corrections_and_mission_state(tmp_path):
    database = tmp_path / "vault.db"
    with VaultZetaStore(database) as writer:
        app = create_dashboard(database, username=LOGIN[0], password=LOGIN[1])
        with TestClient(app) as client:
            client.auth = LOGIN
            original = writer.add_memory(
                kind="semantic", content="Previous calibration rule", scope="lab", source="calibration.md",
            )
            replacement = writer.supersede_memory(original.id, "Calibration now uses a <script> marker.")
            writer.create_task(mission_id="calibration/check", task_id="verify", title="Verify calibration")
            writer.create_task(mission_id="calibration/check", task_id="confirm", title="Confirm results",
                               dependencies=["verify"])
            writer.save_mission("calibration/check", status="running", snapshot={"checkpoint": "test"})
            writer.append_event(mission_id="activity-only", event_type="observation")

            results = client.get("/dashboard/memories", params={"q": "calibration", "scope": "lab"})
            assert "Previous calibration rule" not in results.text
            assert "&lt;script&gt;" in results.text and "<script>" not in results.text
            history = client.get("/dashboard/memories", params={"q": "calibration", "history": "1"})
            assert "Previous calibration rule" in history.text
            detail = client.get("/dashboard/memory", params={"id": replacement.id})
            assert all(label in detail.text for label in ("calibration.md", "Correction history", "Previous calibration"))

            missions = client.get("/dashboard/missions")
            assert "calibration/check" in missions.text and "activity-only" in missions.text
            filtered = client.get("/dashboard/missions", params={"q": "activity"})
            assert "activity-only" in filtered.text and "calibration/check" not in filtered.text
            mission = client.get("/dashboard/mission", params={"id": "calibration/check"})
            assert all(label in mission.text for label in ("Revision 1", "Ready", "blocked", "task created"))
            assert client.get("/dashboard/mission", params={"id": "missing"}).status_code == 404


def test_connect_only_returns_credentials_to_the_owner_on_an_explicit_same_origin_request(tmp_path):
    database = tmp_path / "vault.db"
    token_file = tmp_path / "mcp-token"
    token = "synthetic-token-for-dashboard-test"
    token_file.write_text(token + "\n")
    origin = "https://vault.example.test"
    mcp_url = f"{origin}/mcp"
    copy_route = "/dashboard/connect/copy"
    with VaultZetaStore(database):
        app = create_dashboard(
            database, username=LOGIN[0], password=LOGIN[1], mcp_url=mcp_url, mcp_token_file=token_file,
        )
        with TestClient(app, base_url=origin) as client:
            assert client.get("/dashboard/connect").status_code == 401
            assert client.post(copy_route, json={"client": "token"}, headers={"Origin": origin}).status_code == 401
            client.auth = LOGIN
            page = client.get("/dashboard/connect")
            assert page.status_code == 200
            assert all(label in page.text for label in (mcp_url, "Claude Code", "OpenCode", "Antigravity", "ChatGPT"))
            assert token not in page.text
            assert client.get(copy_route).status_code == 405
            assert "javascript" in client.get("/dashboard/connect.js").headers["content-type"]
            assert client.post(copy_route, json={"client": "token"}).status_code == 403
            assert client.post(copy_route, json={"client": "token"},
                               headers={"Origin": "https://other.example.test"}).status_code == 403
            headers = {"Origin": origin}
            assert client.post(copy_route, data={"client": "token"}, headers=headers).status_code == 415
            assert client.post(copy_route, content="{", headers={**headers, "Content-Type": "application/json"}
                               ).status_code == 400
            assert client.post(copy_route, json={"client": "chatgpt"}, headers=headers).status_code == 400

            auth_headers = {"Authorization": f"Bearer {token}"}
            configs = {
                "claude": {"mcpServers": {"vault-zeta": {"type": "http", "url": mcp_url, "headers": auth_headers}}},
                "opencode": {"mcp": {"servers": {"vault-zeta": {
                    "type": "remote", "url": mcp_url, "oauth": False, "headers": auth_headers,
                }}}},
                "antigravity": {"mcpServers": {"vault-zeta": {"serverUrl": mcp_url, "headers": auth_headers}}},
            }
            for name, expected in configs.items():
                response = client.post(copy_route, json={"client": name}, headers=headers)
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-store"
                assert json.loads(response.json()["text"]) == expected
            assert client.post(copy_route, json={"client": "token"}, headers=headers).json() == {"text": token}
            token_file.unlink()
            assert client.post(copy_route, json={"client": "token"}, headers=headers).status_code == 503
