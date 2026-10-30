"""Telefoon-toegang (sift.lan + /api/drop): loopback mag alles, andere adressen alleen met LAN aan en de juiste code."""
from __future__ import annotations

import io

import pytest

from sift import lan


@pytest.fixture
def remote():
    from fastapi.testclient import TestClient
    from sift.server import app
    return TestClient(app, client=("192.168.1.50", 40000))


@pytest.fixture(autouse=True)
def _reset_lan():
    lan.state.enabled = False
    lan.state.regenerate()
    yield
    lan.state.enabled = False


def test_loopback_gets_lan_info_and_qr(client):
    r = client.get("/api/lan")
    assert r.status_code == 200
    d = r.json()
    assert d["code"] == lan.state.code and len(d["code"]) == 4 and d["url"].endswith("?code=" + d["code"])
    assert set(d) >= {"ip", "port", "code", "url", "enabled", "ips", "firewall"}
    r = client.get("/api/lan/qr.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and b"<svg" in r.content
    assert client.get("/drop").status_code == 200
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert client.get("/api/ping").json()["app"] == "sift"


def test_remote_needs_lan_and_code(remote):
    assert remote.get("/api/projects").status_code == 403          # LAN uit
    assert remote.get("/drop").status_code == 200                  # de droppagina zelf is open
    lan.state.enabled = True
    assert remote.get("/api/projects").status_code == 401          # geen code
    assert remote.get("/api/projects", headers={"X-Sift-Code": "0000" if lan.state.code != "0000" else "0001"}).status_code == 401
    assert remote.get("/api/projects", headers={"X-Sift-Code": lan.state.code}).status_code == 200
    r = remote.get("/?code=" + lan.state.code)
    assert r.status_code == 200 and "sift_code" in r.headers.get("set-cookie", "")
    assert remote.get("/api/lan", headers={"X-Sift-Code": lan.state.code}).status_code == 403  # alleen vanaf de computer zelf


def test_drop_creates_interview(client, projects_dir, monkeypatch):
    from sift import studies
    sid = studies.create("Dropstudie", language="en", num_speakers=3)["id"]
    files = {"file": ("opname.wav", io.BytesIO(b"RIFF" + b"\x00" * 2000), "audio/wav")}
    r = client.post("/api/drop", files=files, data={"name": "Van de telefoon", "autostart": "0"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["study_id"] is None and d["autostart"] is False and d["bytes"] == 2004
    m = client.get(f"/api/projects/{d['id']}").json()
    assert m["name"] == "Van de telefoon" and m["study"] is None and m["status"] != "klaar"
    files = {"file": ("opname2.wav", io.BytesIO(b"RIFF" + b"\x00" * 100), "audio/wav")}
    r = client.post("/api/drop", files=files, data={"study_id": sid})
    assert r.status_code == 200
    m = client.get(f"/api/projects/{r.json()['id']}").json()
    assert m["study"]["id"] == sid and m["settings"]["language"] == "en" and m["settings"]["num_speakers"] == 3
    assert client.post("/api/drop", files={"file": ("x.wav", io.BytesIO(b""), "audio/wav")}).status_code == 400
    assert client.post("/api/drop", files={"file": ("x.wav", io.BytesIO(b"abc"), "audio/wav")}, data={"study_id": "bestaat_niet"}).status_code == 400
