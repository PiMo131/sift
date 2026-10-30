"""API-gedrag: opslaan met token, versies met automatische snapshot vóór herstel, controlestatus, onderzoeken,
back-up → herstel in een lege omgeving, bestaande projecten blijven ongewijzigd."""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from tests.conftest import make_project


@pytest.fixture
def pid(projects_dir):
    make_project(projects_dir, "iv_server")
    return "iv_server"


def test_old_project_loads_and_is_migrated_in_memory_only(client, projects_dir, pid):
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    m = r.json()
    assert m["schema_version"] == 2 and m["review_status"] == "none" and m["status_label"] == "Nakijken bezig"
    raw = json.loads((projects_dir / pid / "project.json").read_text(encoding="utf-8"))
    assert "schema_version" not in raw, "bestand op schijf pas aanpassen bij de volgende opslag"
    t = client.get(f"/api/projects/{pid}/transcript").json()
    assert t["schema_version"] == 2 and t["segments"][1]["quote"] is True


def test_save_echoes_token_and_project_and_marks_review_in_progress(client, pid):
    t = client.get(f"/api/projects/{pid}/transcript").json()
    t["segments"][0]["text"] = "Goedemiddag Anna, fijn dat u meedoet. Extra."
    t["client_token"] = "tok-42"
    r = client.put(f"/api/projects/{pid}/transcript", json=t)
    assert r.status_code == 200
    assert r.json()["client_token"] == "tok-42" and r.json()["project"] == pid and r.json()["version"] == 4
    assert client.get(f"/api/projects/{pid}/transcript").json()["segments"][0]["text"].endswith("Extra.")
    assert client.get(f"/api/projects/{pid}").json()["review_status"] == "in_progress"


def test_save_rejects_garbage(client, pid):
    assert client.put(f"/api/projects/{pid}/transcript", json={"foo": 1}).status_code == 400


def test_beacon_save(client, pid):
    t = client.get(f"/api/projects/{pid}/transcript").json()
    t["segments"][2]["note"] = "via beacon"
    r = client.post(f"/api/projects/{pid}/transcript/beacon", content=json.dumps(t).encode("utf-8"))
    assert r.status_code == 200
    assert client.get(f"/api/projects/{pid}/transcript").json()["segments"][2]["note"] == "via beacon"


def test_snapshot_with_unsaved_editor_state_and_restore_with_pre_restore_copy(client, pid):
    t = client.get(f"/api/projects/{pid}/transcript").json()
    t["segments"][0]["text"] = "NOG NIET OPGESLAGEN"
    r = client.post(f"/api/projects/{pid}/snapshot", json={"label": "mijn versie", "transcript": t})
    assert r.status_code == 200
    vs = client.get(f"/api/projects/{pid}/versions").json()
    assert vs[0]["label"] == "mijn versie" and vs[0]["preview"].startswith("NOG NIET OPGESLAGEN") and vs[0]["segments"] == 3
    assert client.get(f"/api/projects/{pid}/versions/{vs[0]['file']}").json()["segments"][0]["text"] == "NOG NIET OPGESLAGEN"
    # tekst wijzigen, opslaan, dan herstellen
    t2 = client.get(f"/api/projects/{pid}/transcript").json()
    t2["segments"][0]["text"] = "GEWIJZIGD"
    client.put(f"/api/projects/{pid}/transcript", json=t2)
    r = client.post(f"/api/projects/{pid}/versions/{vs[0]['file']}/restore", json={"transcript": t2})
    assert r.status_code == 200
    assert client.get(f"/api/projects/{pid}/transcript").json()["segments"][0]["text"] == "NOG NIET OPGESLAGEN"
    vs2 = client.get(f"/api/projects/{pid}/versions").json()
    pre = [v for v in vs2 if v["label"] == "voor herstel"]
    assert pre and pre[0]["preview"].startswith("GEWIJZIGD")
    assert client.get(f"/api/projects/{pid}/versions/../../project.json").status_code in (404, 400)


def test_checked_status_is_explicit_and_revocable(client, pid):
    assert client.put(f"/api/projects/{pid}/review_status", json={"status": "checked"}).status_code == 200
    m = client.get(f"/api/projects/{pid}").json()
    assert m["status_label"] == "Gecontroleerd" and m["checked_at"] and m["next_action"] == "Exporteren"
    client.put(f"/api/projects/{pid}/review_status", json={"status": "in_progress"})
    assert client.get(f"/api/projects/{pid}").json()["status_label"] == "Nakijken bezig"
    assert client.put(f"/api/projects/{pid}/review_status", json={"status": "klaar"}).status_code == 400


def test_export_endpoint_contents_and_filename(client, pid):
    opts = {"pseudonymize": [{"find": "Anna de Vries", "replace": "[persoon1]"}, {"find": "Anna", "replace": "[persoon1]"}], "notes": True}
    r = client.post(f"/api/projects/{pid}/export/txt", json=opts)
    assert r.status_code == 200 and "Anna" not in r.text and "[persoon1]" in r.text
    assert 'filename="Interview [persoon1].txt"' in r.headers["content-disposition"]
    r = client.post(f"/api/projects/{pid}/export/docx", json={**opts, "control_overview": True})
    xml = zipfile.ZipFile(io.BytesIO(r.content)).read("word/document.xml").decode("utf-8")
    assert "Anna" not in xml and "Controleoverzicht" in xml
    pv = client.post(f"/api/projects/{pid}/export/docx/preview", json=opts).json()
    assert pv["replacements"]["Anna"] >= 1 and pv["contract"]["label"].startswith("Word")
    assert client.post(f"/api/projects/{pid}/export/quotes", json={}).text.strip().startswith("[00:00:03] Anna de Vries: Eh, ik woon in Zwolle")
    assert client.post(f"/api/projects/{pid}/export/xyz", json={}).status_code == 400


def test_studies_crud_and_inheritance(client, projects_dir, pid):
    r = client.post("/api/studies", json={"name": "Leven met reuma", "terms": "methotrexaat, reumaverpleegkundige"})
    assert r.status_code == 200
    sid = r.json()["id"]
    assert sid == "Leven_met_reuma" and r.json()["conventions"]["fillers"] == "keep"
    client.put(f"/api/projects/{pid}/study", json={"study_id": sid})
    client.put(f"/api/projects/{pid}/settings", json={"initial_prompt": "Zwolle"})
    m = client.get(f"/api/projects/{pid}").json()
    assert m["study"]["name"] == "Leven met reuma" and m["effective_terms"] == "methotrexaat, reumaverpleegkundige, Zwolle"
    ls = client.get("/api/studies").json()
    assert ls[0]["interviews"] == 1
    assert client.delete(f"/api/studies/{sid}").status_code == 409, "met interviews niet verwijderbaar"
    assert client.get(f"/api/studies/{sid}/conventions.txt").text.startswith("Onderzoek: Leven met reuma")
    client.put(f"/api/studies/{sid}", json={"conventions": {"fillers": "remove", "filler_words": "eh, uhm"}})
    assert "Eh," not in client.post(f"/api/projects/{pid}/export/txt", json={"style": "clean"}).text
    client.put(f"/api/projects/{pid}/study", json={"study_id": None})
    assert client.delete(f"/api/studies/{sid}").status_code == 200


# ---------- back-up ----------
def test_backup_restore_in_empty_environment_and_never_overwrites(client, projects_dir, pid):
    from sift import studies
    s = studies.create("Backup-onderzoek", terms="reuma")
    client.put(f"/api/projects/{pid}/study", json={"study_id": s["id"]})
    client.post(f"/api/projects/{pid}/snapshot", json={"label": "v1"})
    r = client.get(f"/api/projects/{pid}/backup")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    man = json.loads(z.read("backup.json"))
    assert {"project.json", "transcript.json", "source.m4a", "study.json", "runs/large-v3.json"} <= set(names)
    assert man["contains_source_audio"] and man["pseudonymized"] is False and man["caches_included"] is False
    assert any(n.startswith("versions/") for n in names)
    before = (projects_dir / pid / "transcript.json").read_bytes()

    # "lege omgeving": verwijder project en onderzoek, herstel
    client.delete(f"/api/projects/{pid}")
    studies.delete(s["id"])
    assert client.get(f"/api/projects/{pid}").status_code == 404
    info = client.post("/api/backups/inspect", files={"file": ("b.zip", r.content, "application/zip")}).json()
    assert info["exists"] is False and info["has_audio"] and info["study"]["name"] == "Backup-onderzoek"
    rr = client.post("/api/backups/restore", files={"file": ("b.zip", r.content, "application/zip")}).json()
    assert rr["id"] == pid and rr["renamed"] is False and rr["study"]["action"] == "onderzoek hersteld"
    t = client.get(f"/api/projects/{pid}/transcript").json()
    assert t["speakers"]["S2"]["name"] == "Anna de Vries" and t["segments"][1]["note"].startswith("Anna aarzelt")
    assert (projects_dir / pid / "source.m4a").read_bytes() == b"RIFFfake"
    m = client.get(f"/api/projects/{pid}").json()
    assert m["study"]["terms"] == "reuma" and m["settings"]["language"] == "nl"
    assert len(client.get(f"/api/projects/{pid}/versions").json()) >= 1

    # tweede keer herstellen: bestaand project blijft ongewijzigd, kopie krijgt achtervoegsel
    (projects_dir / pid / "transcript.json").write_bytes(before)
    client.put(f"/api/projects/{pid}/transcript", json={**t, "segments": [{**t["segments"][0], "text": "LOKAAL GEWIJZIGD"}] + t["segments"][1:]})
    info2 = client.post("/api/backups/inspect", files={"file": ("b.zip", r.content, "application/zip")}).json()
    assert info2["exists"] is True
    rr2 = client.post("/api/backups/restore", files={"file": ("b.zip", r.content, "application/zip")}).json()
    assert rr2["renamed"] is True and rr2["id"] == f"{pid}_2" and rr2["study"]["action"] == "bestaand onderzoek gebruikt"
    assert client.get(f"/api/projects/{pid}/transcript").json()["segments"][0]["text"] == "LOKAAL GEWIJZIGD"
    assert client.get(f"/api/projects/{pid}_2/transcript").json()["segments"][0]["text"].startswith("Goedemiddag")


def test_backup_rejects_unsafe_or_foreign_zip(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("backup.json", json.dumps({"format": "sift-backup", "backup_format": 1, "project_id": "x"}))
        z.writestr("project.json", json.dumps({"name": "x", "source": "source.wav"}))
        z.writestr("../evil.txt", "x")
    r = client.post("/api/backups/inspect", files={"file": ("b.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400 and "Onveilig" in r.json()["detail"]
    r = client.post("/api/backups/inspect", files={"file": ("b.zip", b"not a zip", "application/zip")})
    assert r.status_code == 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("transcript.json", "{}")
    assert client.post("/api/backups/restore", files={"file": ("b.zip", buf.getvalue(), "application/zip")}).status_code == 400
