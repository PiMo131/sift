"""Browsertests (Playwright + Chromium) voor de P0-fouten in de editor: automatisch opslaan met de cursor in de tekst,
vertraagde en mislukte opslag, projectwissel tijdens opslaan, versie bewaren met niet-vastgelegde invoer, ongedaan maken,
toetsenbordgedrag en schermgrootte. Draait tegen een echte Sift-server op een vrije poort met fictieve projecten
(zonder audio: de speler geeft dan 404, dat is voor deze tests niet relevant).

Overslaan als Playwright/Chromium ontbreekt:  pip install playwright && playwright install chromium
"""
from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import pytest

from tests.conftest import make_project

pw = pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def server(projects_dir_module):
    import uvicorn
    from sift.server import app
    port = _free_port()
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    srv = uvicorn.Server(cfg)
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True


@pytest.fixture(scope="module")
def projects_dir_module():
    import os
    d = Path(os.environ["SIFT_PROJECTS"])
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser, server):
    ctx = browser.new_context(viewport={"width": 1366, "height": 768})
    pg = ctx.new_page()
    pg.base = server
    yield pg
    ctx.close()


def _open(pg, pid):
    pg.goto(f"{pg.base}/#p={pid}&v=editor")
    pg.wait_for_selector("#seg0 .txt")


def _txt(loc):
    return " ".join(loc.inner_text().split())


def _disk(projects_dir, pid):
    return json.loads((projects_dir / pid / "transcript.json").read_text(encoding="utf-8"))


def test_typing_with_focus_kept_is_saved_and_survives_reload(page, projects_dir_module):
    make_project(projects_dir_module, "ui_a")
    _open(page, "ui_a")
    txt = page.locator("#seg0 .txt")
    txt.click()
    page.keyboard.press("End")
    page.keyboard.type(" TOEGEVOEGD")
    assert "Wijzigingen aanwezig" in page.locator("#saveState").inner_text()
    page.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=8000)
    assert page.evaluate("document.activeElement.closest('.txt') !== null"), "cursor staat nog in de tekst"
    assert _disk(projects_dir_module, "ui_a")["segments"][0]["text"].endswith("TOEGEVOEGD")
    page.reload()
    page.wait_for_selector("#seg0 .txt")
    assert "TOEGEVOEGD" in _txt(page.locator("#seg0 .txt"))


def test_typing_during_delayed_save_keeps_everything(page, projects_dir_module):
    make_project(projects_dir_module, "ui_b")
    _open(page, "ui_b")

    def slow(route):
        time.sleep(2.5)
        route.continue_()
    page.route("**/api/projects/ui_b/transcript", slow)
    page.locator("#seg1 .txt").click()
    page.keyboard.press("End")
    page.keyboard.type(" EEN")
    page.wait_for_function("document.querySelector('#saveState').classList.contains('saving')", timeout=6000)
    page.keyboard.type(" TWEE")  # tijdens de lopende opslag
    assert page.locator("#saveState").inner_text().startswith("●")
    page.wait_for_function("document.querySelector('#saveState').classList.contains('saved') && !document.querySelector('#saveState').classList.contains('dirty')", timeout=15000)
    page.wait_for_timeout(300)
    page.unroute("**/api/projects/ui_b/transcript")
    page.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=15000)
    assert _disk(projects_dir_module, "ui_b")["segments"][1]["text"].endswith("EEN TWEE")
    page.reload()
    page.wait_for_selector("#seg1 .txt")
    assert _txt(page.locator("#seg1 .txt")).endswith("EEN TWEE")


def test_failed_save_is_honest_and_recovers_without_loss(page, projects_dir_module):
    make_project(projects_dir_module, "ui_c")
    _open(page, "ui_c")
    fail = {"on": True}

    def maybe_fail(route):
        if fail["on"]:
            route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": "schijf geblokkeerd (test)"}))
        else:
            route.continue_()
    page.route("**/api/projects/ui_c/transcript", maybe_fail)
    page.locator("#seg2 .txt").click()
    page.keyboard.press("End")
    page.keyboard.type(" NA FOUT")
    page.wait_for_function("document.querySelector('#saveState').classList.contains('failed')", timeout=8000)
    assert "mislukt" in page.locator("#saveState").inner_text() and "schijf geblokkeerd" in page.locator("#saveState").inner_text()
    assert "NA FOUT" not in _disk(projects_dir_module, "ui_c")["segments"][2]["text"]
    fail["on"] = False
    page.click("#saveRetry")
    page.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=8000)
    assert _disk(projects_dir_module, "ui_c")["segments"][2]["text"].endswith("NA FOUT")


def test_switching_interview_during_save_keeps_data_with_the_right_one(page, projects_dir_module):
    make_project(projects_dir_module, "ui_d1")
    make_project(projects_dir_module, "ui_d2")
    _open(page, "ui_d1")

    def slow(route):
        time.sleep(2.0)
        route.continue_()
    page.route("**/api/projects/ui_d1/transcript", slow)
    page.locator("#seg0 .txt").click()
    page.keyboard.press("End")
    page.keyboard.type(" VAN D1")
    page.wait_for_function("document.querySelector('#saveState').classList.contains('saving')", timeout=6000)
    page.evaluate("openProject('ui_d2')")  # wisselen terwijl de opslag van D1 nog loopt
    page.wait_for_function("S.pid === 'ui_d2' && S.tr !== null", timeout=15000)
    page.wait_for_timeout(2500)
    assert page.evaluate("S.tr.segments[0].text") == "Goedemiddag Anna, fijn dat u meedoet.", "D2 ongewijzigd"
    assert _disk(projects_dir_module, "ui_d1")["segments"][0]["text"].endswith("VAN D1")
    assert _disk(projects_dir_module, "ui_d2")["segments"][0]["text"] == "Goedemiddag Anna, fijn dat u meedoet."
    st = page.locator("#saveState").inner_text()
    assert "Opgeslagen" not in st or "versie" not in st, "late respons van D1 mag D2 niet als opgeslagen tonen"


def test_save_version_includes_uncommitted_input_and_restore_makes_pre_restore_copy(page, projects_dir_module):
    make_project(projects_dir_module, "ui_e")
    _open(page, "ui_e")
    page.locator("#seg0 .txt").click()
    page.keyboard.press("End")
    page.keyboard.type(" IN VERSIE")
    page.click("#btnSnap")
    page.fill("#pIn", "mijn label")
    page.click("#pOk")
    page.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=8000)
    vs = json.loads(page.evaluate("JSON.stringify(await (await fetch('/api/projects/ui_e/versions')).json())") if False else page.evaluate("fetch('/api/projects/ui_e/versions').then(r=>r.json()).then(j=>JSON.stringify(j))"))
    assert vs[0]["label"] == "mijn label" and "IN VERSIE" in vs[0]["preview"]
    # tekst wijzigen, dan herstellen via Exporteren → Versies
    page.locator("#seg0 .txt").click()
    page.keyboard.press("End")
    page.keyboard.type(" DAARNA")
    page.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=8000)
    page.click(".tab[data-view='export']")
    page.wait_for_selector("#vlist [data-vr]")
    page.locator("#vlist [data-vr]").first.click()
    page.click("#cOk")
    page.wait_for_function("document.querySelectorAll('#vlist .v').length >= 2", timeout=8000)
    labels = page.locator("#vlist .v b").all_inner_texts()
    assert "voor herstel" in labels
    assert _disk(projects_dir_module, "ui_e")["segments"][0]["text"].endswith("IN VERSIE")


def test_undo_redo_and_shortcuts(page, projects_dir_module):
    make_project(projects_dir_module, "ui_f")
    _open(page, "ui_f")
    # alternatief kiezen via het aandachtspuntpaneel, dan ongedaan maken
    page.click("#attNext")
    page.wait_for_selector("#ptOk")
    first = page.evaluate("S.tr.segments[S.curWord[0]].words[S.curWord[1]].word")
    page.click("#altCustom")
    page.fill("#pIn", "VERVANGEN")
    page.click("#pOk")
    assert page.evaluate("S.tr.segments[1].words.map(w=>w.word).includes('VERVANGEN')")
    page.keyboard.press("Control+z")
    assert not page.evaluate("S.tr.segments[1].words.map(w=>w.word).includes('VERVANGEN')")
    page.keyboard.press("Control+y")
    assert page.evaluate("S.tr.segments[1].words.map(w=>w.word).includes('VERVANGEN')")
    # 'Klopt zo' bevestigt zonder de modelscore te veranderen
    page.click("#attNext")
    page.wait_for_selector("#ptOk")
    si, wi = page.evaluate("S.curWord")
    p_before = page.evaluate(f"S.tr.segments[{si}].words[{wi}].p")
    page.click("#ptOk")
    assert page.evaluate(f"S.tr.segments[{si}].words[{wi}].checked") is True
    assert page.evaluate(f"S.tr.segments[{si}].words[{wi}].p") == p_before
    # Tab is gewone focusnavigatie, Ctrl+S slaat op, Alt+S wisselt spreker
    page.locator("#seg0 .txt").click()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.classList.contains('txt') === false"), "Tab verlaat het tekstvak (geen woordsprong)"
    page.locator("#seg0 .txt").click()
    page.keyboard.press("End")
    page.keyboard.type(" X")
    page.keyboard.press("Control+s")
    page.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=8000)
    spk = page.evaluate("S.tr.segments[0].speaker")
    page.locator("#seg0 .txt").click()
    page.keyboard.press("Alt+s")
    assert page.evaluate("S.tr.segments[0].speaker") != spk
    # sneltoetsen grijpen niet in bij een dialoogveld
    page.click("#btnFind")
    page.fill("#fFind", "j")
    page.keyboard.press("Control+s")
    assert page.locator("#fFind").input_value() == "j"
    page.keyboard.press("Escape")


def test_layout_at_small_zoomed_screen(page, projects_dir_module):
    make_project(projects_dir_module, "ui_g")
    for w, h in ((1366, 768), (911, 512), (1280, 600)):  # 911×512 ≈ 1366×768 bij 150 % zoom
        page.set_viewport_size({"width": w, "height": h})
        page.goto("about:blank")
        _open(page, "ui_g")
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), f"horizontale scroll bij {w}×{h}"
        for sel in ("#btnPlay", "#attNext", "#btnListen", "#saveState", "#tbQuote", ".tab[data-view='export']"):
            box = page.locator(sel).bounding_box()
            assert box and 0 <= box["x"] and box["x"] + box["width"] <= w + 1, f"{sel} buiten beeld bij {w}×{h}"
        page.click("#btnListen")
        assert page.locator("#listenPop").is_visible()
        page.keyboard.press("Escape")


def test_export_quotes_only_and_pseudonym_table(page, projects_dir_module):
    make_project(projects_dir_module, "ui_h")
    _open(page, "ui_h")
    page.click(".tab[data-view='export']")
    page.click("[data-p='quotes']")
    page.wait_for_function("document.querySelector('#ePreview').textContent.includes('Zwolle')", timeout=8000)
    pv = page.locator("#ePreview").inner_text()
    assert "Goedemiddag" not in pv and "Dank u wel" not in pv
    page.click("[data-p='word']")
    page.wait_for_selector("#ePsOn")
    page.check("#ePsOn")
    page.fill("#psTable input[data-ps='find'][data-i='0']", "Anna")
    page.fill("#psTable input[data-ps='replace'][data-i='0']", "[persoon1]")
    page.wait_for_function("document.querySelector('#ePreview').textContent.includes('[persoon1]')", timeout=8000)
    assert "Anna" not in page.locator("#ePreview").inner_text()
    assert "Anna → " in page.locator("#eHits").inner_text()
    # wisselen van stijl rendert het formulier opnieuw; de tabel blijft staan
    page.select_option("#eStyle", "clean")
    page.click("[data-p='maxqda']")
    page.click("[data-p='word']")
    assert page.locator("#psTable input[data-ps='find'][data-i='0']").input_value() == "Anna"
    assert page.locator("#eStyle").input_value() == "clean"
