import http.client
import json
import os
import re
import secrets
import subprocess
import sys
import time
from contextlib import contextmanager

import pytest


def server_command(transport):
    return [
        sys.executable,
        "-m",
        "vault_zeta.mcp_server",
        "--transport",
        transport,
        "--host",
        "127.0.0.1",
        "--port",
        "0",
    ]


@contextmanager
def running_server(tmp_path, transport, token):
    env = {**os.environ, "VAULT_ZETA_DB": str(tmp_path / "vault.db"), "VAULT_ZETA_HTTP_TOKEN": token}
    log_path = tmp_path / "server.log"
    with (
        log_path.open("wb") as log,
        subprocess.Popen(
            server_command(transport),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        ) as process,
    ):
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and process.poll() is None:
                running = re.search(rb"Uvicorn running on http://127\.0\.0\.1:(\d+)", log_path.read_bytes())
                if running:
                    yield int(running[1])
                    return
                time.sleep(0.05)
            pytest.fail(f"MCP server did not start:\n{log_path.read_text()}")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def request(port, method, path, *, headers=None, body=None, read_body=True):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.headers, response.read() if read_body else b""
    finally:
        connection.close()


def rpc(port, message, headers=None):
    return request(
        port,
        "POST",
        "/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **(headers or {}),
        },
        body=json.dumps({"jsonrpc": "2.0", **message}),
    )


def rpc_result(response):
    status, headers, body = response
    assert status == 200, body
    if headers.get_content_type() == "text/event-stream":
        body = next(line[6:] for line in body.splitlines() if line.startswith(b"data: "))
    return json.loads(body)["result"]


def assert_auth_required(response):
    status, headers, _ = response
    assert status == 401
    assert headers["WWW-Authenticate"].startswith("Bearer ")


def test_streamable_http_authenticates_each_request(tmp_path):
    token = secrets.token_urlsafe(32)
    authorization = {"Authorization": f"Bearer {token}"}
    initialize = {
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "auth-acceptance-test", "version": "1"},
        },
    }
    with running_server(tmp_path, "streamable-http", token) as port:
        assert_auth_required(rpc(port, initialize))
        assert_auth_required(rpc(port, initialize, {"Authorization": f"Basic {token}"}))
        assert_auth_required(rpc(port, initialize, {"Authorization": f"Bearer {secrets.token_urlsafe(32)}"}))

        initialized = rpc(port, initialize, authorization)
        protocol_version = rpc_result(initialized)["protocolVersion"]
        session = {
            "Mcp-Session-Id": initialized[1]["Mcp-Session-Id"],
            "Mcp-Protocol-Version": protocol_version,
        }
        authenticated_session = {**session, **authorization}
        notified = rpc(port, {"method": "notifications/initialized"}, authenticated_session)
        assert notified[0] == 202

        save = {
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "memory_save",
                "arguments": {"content": "Synthetic vault continuity record."},
            },
        }
        assert_auth_required(rpc(port, save, session))

        status_call = {"id": 3, "method": "tools/call", "params": {"name": "vault_status", "arguments": {}}}
        result = rpc_result(rpc(port, status_call, authenticated_session))
        assert json.loads(result["content"][0]["text"])["memories"] == 0

        result = rpc_result(rpc(port, save, authenticated_session))
        assert json.loads(result["content"][0]["text"])["saved"] is True
        result = rpc_result(rpc(port, status_call, authenticated_session))
        assert json.loads(result["content"][0]["text"])["memories"] == 1


def test_sse_protects_the_stream_and_message_endpoint(tmp_path):
    token = secrets.token_urlsafe(32)
    with running_server(tmp_path, "sse", token) as port:
        assert_auth_required(request(port, "GET", "/sse"))
        assert_auth_required(request(port, "POST", "/messages/"))
        response = request(port, "GET", "/sse", headers={"Authorization": f"Bearer {token}"}, read_body=False)
        assert response[0] == 200
        assert response[1].get_content_type() == "text/event-stream"


@pytest.mark.parametrize("transport", ["streamable-http", "sse"])
@pytest.mark.parametrize("token", [None, "too-short"])
def test_network_transport_refuses_missing_or_invalid_config(tmp_path, transport, token):
    db_path = tmp_path / "vault.db"
    env = {**os.environ, "VAULT_ZETA_DB": str(db_path)}
    env.pop("VAULT_ZETA_HTTP_TOKEN", None)
    if token is not None:
        env["VAULT_ZETA_HTTP_TOKEN"] = token

    process = subprocess.run(server_command(transport), env=env, capture_output=True, timeout=10)
    assert process.returncode == 2
    assert b"VAULT_ZETA_HTTP_TOKEN" in process.stderr
    assert not db_path.exists()
