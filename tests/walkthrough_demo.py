"""De 'Minimale verificatie' uit de opdracht, uitgevoerd met het fictieve demo-interview en ÉCHTE transcriptie.

Geen pytest-test (duurt enkele minuten en gebruikt de GPU/CPU): draai met
    python tests/walkthrough_demo.py [--port 8771]
Start zelf een Sift-server op een lege, tijdelijke projectmap, loopt de twaalf stappen door in Chromium (Playwright) en
schrijft een logboek naar docs/verificatie_log.txt. Alle gegevens zijn fictief (demo/).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="sift_walk_"))
os.environ["SIFT_PROJECTS"] = str(TMP / "projects")
sys.path.insert(0, str(ROOT))

LOG: list[str] = []


def log(step: str, ok: bool, detail: str = "") -> None:
    line = f"{'OK ' if ok else 'NOK'} {step}{(' — ' + detail) if detail else ''}"
    LOG.append(line)
    print(line, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8771)
    a = ap.parse_args()
    import uvicorn
    from playwright.sync_api import sync_playwright
    from sift.server import app
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=a.port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", a.port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    base = f"http://127.0.0.1:{a.port}"
    pdir = TMP / "projects"
    t0 = time.time()
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1366, "height": 768}, accept_downloads=True)
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        # 1. nieuwe gebruiker
        pg.goto(base + "/")
        pg.wait_for_selector("#btnCreate")
        log("1 Open Sift als nieuwe gebruiker", "Nog niets" in pg.locator("#home").inner_text(), "lege projectmap, startpagina met 'Nieuw interview'")

        # 2. onderzoek + interview; 3. taal, sprekers, vaktermen zonder modelkeuze; 4. eerst een fragment
        pg.click("#newStudy")
        pg.fill("#pIn", "Leven met reuma (verificatie)")
        pg.click("#pOk")
        pg.wait_for_selector("#home [data-study]")
        pg.locator("#home [data-study]").first.click()
        pg.fill("#stTerms", "methotrexaat, reumaverpleegkundige, dokter Pieters")
        pg.check("input[name='cv_fillers'][value='remove']")
        pg.click("#stSave")
        pg.wait_for_function("document.querySelectorAll('#newStudySel option').length >= 2", timeout=10000)  # startpagina is opnieuw opgebouwd
        log("2 Onderzoek aangemaakt met woordenlijst en afspraken", True, "stopwoorden: weglaten bij export (clean verbatim)")
        pg.fill("#newName", "Demo R01")
        pg.set_input_files("#fileInput", str(ROOT / "demo" / "demo_interview.m4a"))
        pg.select_option("#newStudySel", index=1)
        pg.select_option("#newLang", "nl")
        pg.select_option("#newSpk", "2")
        pg.fill("#newTerms", "Zwolle, Kampen")
        pg.check("#tryFirst")
        pg.fill("#tryStart", "0:00")
        pg.fill("#tryLen", "1:00")
        adv_open = pg.evaluate("document.querySelector('#advBox').open")
        log("3 Taal, sprekers en vaktermen opgegeven zonder modelkeuze", not adv_open, "Geavanceerd bleef dicht; modellen volgens aanbeveling voor deze computer")
        pg.click("#btnCreate")
        pg.wait_for_selector("#pipe .step", timeout=60000)
        pg.wait_for_function("S.meta && S.meta.status === 'klaar'", timeout=600000)
        pid = pg.evaluate("S.pid")
        meta = json.loads((pdir / pid / "project.json").read_text(encoding="utf-8"))
        log("4a Fragment van 1 minuut verwerkt (echte transcriptie)", meta["status"] == "klaar" and meta["settings"]["end"] == 60, f"modellen {list(meta['runs'])}, duur {meta['audio']['duration']:.0f} s, {time.time() - t0:.0f} s na start")
        full_note = "fragment" in pg.locator("#pipe").inner_text().lower()
        pg.click("#pFull")
        pg.click("#cOk")
        pg.wait_for_function("S.meta && S.meta.status === 'bezig'", timeout=30000)
        pg.wait_for_function("S.meta && S.meta.status === 'klaar' && S.meta.settings.end == null", timeout=600000)
        meta = json.loads((pdir / pid / "project.json").read_text(encoding="utf-8"))
        tr = json.loads((pdir / pid / "transcript.json").read_text(encoding="utf-8"))
        log("4b Daarna de hele opname verwerkt", meta["status"] == "klaar" and meta["audio"]["duration"] > 150, f"{len(tr['segments'])} segmenten, {len(tr['gaps'])} interval(len) mogelijk ontbrekende tekst {[(g['start'], g['end']) for g in tr['gaps']]}, uitleg tijdcodes fragment getoond: {full_note}")

        # 5. corrigeren, aandachtspunt bevestigen, later luisteren
        pg.click("#pOpen")
        pg.wait_for_selector("#seg0 .txt")
        pg.locator("#seg0 .txt").click()
        pg.keyboard.press("Control+End")
        pg.keyboard.type(" (correctie)")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=10000)
        pg.click("#attNext")
        pg.wait_for_selector("#ptOk", timeout=5000)
        si, wi = pg.evaluate("S.curWord")
        p_before = pg.evaluate(f"S.tr.segments[{si}].words[{wi}].p")
        pg.click("#ptOk")
        pg.wait_for_timeout(300)
        checked = pg.evaluate(f"S.tr.segments[{si}].words[{wi}].checked") and pg.evaluate(f"S.tr.segments[{si}].words[{wi}].p") == p_before
        pg.locator("#seg3 .txt").click()
        pg.keyboard.press("Alt+l")
        later = pg.evaluate("S.tr.segments[3].later")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=10000)
        disk = json.loads((pdir / pid / "transcript.json").read_text(encoding="utf-8"))
        log("5 Tekst gecorrigeerd, aandachtspunt 'Klopt zo', passage op 'Later luisteren'", "(correctie)" in disk["segments"][0]["text"] and checked and later and disk["segments"][3]["later"], "modelscore ongewijzigd na bevestigen")

        # 6. citaat + spreker corrigeren
        pg.locator("#seg1 .txt").click()
        pg.keyboard.press("Alt+c")
        pg.locator("#seg2 .sp").click()
        pg.wait_for_selector(".dropdown button")
        before_spk = pg.evaluate("S.tr.segments[2].speaker")
        pg.locator(".dropdown button").nth(1 if before_spk == "S1" else 0).click()
        pg.wait_for_timeout(300)
        after_spk = pg.evaluate("S.tr.segments[2].speaker")
        pg.locator("#side input[data-sp='S1']").fill("Interviewer")
        pg.locator("#side input[data-sp='S1']").press("Enter")
        pg.locator("#side input[data-sp='S2']").fill("Anna de Vries")
        pg.locator("#side input[data-sp='S2']").press("Enter")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=10000)
        pg.wait_for_timeout(500)
        disk = json.loads((pdir / pid / "transcript.json").read_text(encoding="utf-8"))
        log("6 Citaat gemarkeerd en spreker gecorrigeerd", disk["segments"][1]["quote"] and before_spk != after_spk and disk["speakers"]["S2"]["name"] == "Anna de Vries", "sprekers hernoemd naar Interviewer / Anna de Vries (fictief)")

        # 7. opslaan: focus in tekst, vertraagde respons, fout
        def slow(route):
            time.sleep(2.0)
            route.continue_()
        pg.route(f"**/api/projects/{pid}/transcript", slow)
        pg.locator("#seg4 .txt").click()
        pg.keyboard.press("Control+End")
        pg.keyboard.type(" EEN")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('saving')", timeout=8000)
        pg.keyboard.type(" TWEE")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('saved') && !document.querySelector('#saveState').classList.contains('dirty')", timeout=20000)
        pg.wait_for_timeout(500)
        pg.unroute(f"**/api/projects/{pid}/transcript")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=20000)
        ok7a = json.loads((pdir / pid / "transcript.json").read_text(encoding="utf-8"))["segments"][4]["text"].endswith("EEN TWEE")
        fail = {"on": True}
        pg.route(f"**/api/projects/{pid}/transcript", lambda r: r.fulfill(status=503, content_type="application/json", body='{"detail":"testfout"}') if fail["on"] else r.continue_())
        pg.keyboard.type(" DRIE")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('failed')", timeout=8000)
        fail["on"] = False
        pg.click("#saveRetry")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=8000)
        pg.unroute(f"**/api/projects/{pid}/transcript")
        ok7b = json.loads((pdir / pid / "transcript.json").read_text(encoding="utf-8"))["segments"][4]["text"].endswith("EEN TWEE DRIE")
        log("7 Opslaan met focus in de tekst, vertraagde respons en een fout", ok7a and ok7b, "status toonde achtereenvolgens: wijzigingen aanwezig → bezig → opgeslagen; mislukt → opnieuw → opgeslagen; niets verloren")

        # 8. versie bewaren, wijzigen, herstellen
        pg.click("#btnSnap")
        pg.fill("#pIn", "verificatie")
        pg.click("#pOk")
        pg.wait_for_timeout(800)
        pg.locator("#seg0 .txt").click()
        pg.keyboard.press("Control+End")
        pg.keyboard.type(" NA VERSIE")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=10000)
        pg.click(".tab[data-view='export']")
        pg.wait_for_selector("#vlist [data-vr]")
        pg.locator("#vlist [data-vr]").first.click()
        pg.click("#cOk")
        pg.wait_for_function("[...document.querySelectorAll('#vlist .v b')].some(b => b.textContent === 'voor herstel')", timeout=15000)  # herstel is pas klaar als de automatische versie in de lijst staat
        pg.wait_for_timeout(500)
        disk = json.loads((pdir / pid / "transcript.json").read_text(encoding="utf-8"))
        labels = pg.locator("#vlist .v b").all_inner_texts()
        log("8 Versie bewaard, tekst gewijzigd, versie hersteld", "NA VERSIE" not in disk["segments"][0]["text"] and "(correctie)" in disk["segments"][0]["text"] and "voor herstel" in labels, "automatische versie 'voor herstel' aanwezig")

        # 9. naam vervangen: Word + gegevensexport
        pg.goto("about:blank")
        pg.goto(f"{base}/#p={pid}&v=export")
        pg.wait_for_selector("#ePsOn")
        pg.click("[data-p='word']")
        pg.check("#ePsOn")
        pg.fill("#psTable input[data-ps='find'][data-i='0']", "Anna de Vries")
        pg.fill("#psTable input[data-ps='replace'][data-i='0']", "[persoon1]")
        pg.click("#psAdd")
        pg.fill("#psTable input[data-ps='find'][data-i='1']", "Zwolle")
        pg.fill("#psTable input[data-ps='replace'][data-i='1']", "[plaats1]")
        pg.check("#eCtl")
        pg.check("#eNotes")
        pg.wait_for_function("document.querySelector('#ePreview').textContent.includes('[persoon1]')", timeout=10000)
        with pg.expect_download() as dl:
            pg.click("#eGo")
        f = dl.value
        docx = Path(f.path()).read_bytes()
        xml = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode("utf-8")
        ok_docx = "Anna" not in xml and "Zwolle" not in xml and "[persoon1]" in xml and "Controleoverzicht" in xml and "lnNumType" in xml
        pg.click("[data-p='advanced']")
        pg.click("[data-f='csv']")
        pg.wait_for_function("document.querySelector('#ePreview').textContent.includes('[persoon1]')", timeout=10000)
        with pg.expect_download() as dl2:
            pg.click("#eGo")
        csv = Path(dl2.value.path()).read_text(encoding="utf-8-sig")
        ok_csv = "Anna" not in csv and "Zwolle" not in csv and "[persoon1]" in csv
        orig = json.loads((pdir / pid / "transcript.json").read_text(encoding="utf-8"))
        log("9 Fictieve naam vervangen; Word- en gegevensexport gecontroleerd", ok_docx and ok_csv and orig["speakers"]["S2"]["name"] == "Anna de Vries", f"bestanden {f.suggested_filename} en {dl2.value.suggested_filename}; origineel ongewijzigd; vervangingen ook in sprekerlabel, titel en bestandsnaam")

        # 10. alleen citaten
        pg.click("[data-p='quotes']")
        pg.wait_for_function("document.querySelector('#ePreview').textContent.length > 10", timeout=10000)
        with pg.expect_download() as dl3:
            pg.click("#eGo")
        q = Path(dl3.value.path()).read_text(encoding="utf-8")
        seg1 = orig["segments"][1]["text"].split()[0]
        others = [s["text"][:25] for i, s in enumerate(orig["segments"]) if i != 1 and len(s["text"]) > 25][:5]
        log("10 Alleen citaten geëxporteerd", seg1 in q and not any(o in q for o in others), f"citaatbestand bevat alleen segment 2 ({len(q.splitlines())} regels)")

        # 11. back-up → herstel in lege omgeving
        with pg.expect_download() as dl4:
            pg.click("#bkDown")
        zipdata = Path(dl4.value.path()).read_bytes()
        names = zipfile.ZipFile(io.BytesIO(zipdata)).namelist()
        import httpx
        httpx.delete(f"{base}/api/projects/{pid}", timeout=30)
        from sift import studies
        sid = meta["study_id"]
        studies.delete(sid)
        empty = not (pdir / pid).exists() and studies.get(sid) is None
        pg.goto("about:blank")
        pg.goto(base + "/")
        pg.wait_for_selector("#restoreBackup")
        pg.click("#restoreBackup")
        pg.set_input_files("#bkFile", {"name": "backup.zip", "mimeType": "application/zip", "buffer": zipdata})
        pg.wait_for_function("!document.querySelector('#bkGo').disabled", timeout=10000)
        pg.click("#bkGo")
        pg.wait_for_selector("#home .item", timeout=10000)
        r = json.loads((pdir / pid / "transcript.json").read_text(encoding="utf-8"))
        rm = json.loads((pdir / pid / "project.json").read_text(encoding="utf-8"))
        st = studies.get(sid)
        ok11 = empty and r["speakers"]["S2"]["name"] == "Anna de Vries" and r["segments"][1]["quote"] and (pdir / pid / "source.m4a").exists() and rm["settings"]["language"] == "nl" and st and st["terms"].startswith("methotrexaat")
        log("11 Back-up gemaakt en hersteld in een lege omgeving", ok11, f"zip met {len(names)} bestanden incl. opname, versies, runs en study.json; tekst, audio, labels, opmerkingen, instellingen en onderzoek terug")

        # 12. toetsenbord, schermgrootte, zoom
        res = []
        for w, h, label in ((1366, 768, "1366×768 100%"), (1920, 1080, "1920×1080 100%"), (1093, 614, "1366×768 125%"), (911, 512, "1366×768 150%"), (1536, 864, "1920×1080 125%"), (1280, 720, "1920×1080 150%")):
            pg.set_viewport_size({"width": w, "height": h})
            pg.goto("about:blank")
            pg.goto(f"{base}/#p={pid}&v=editor")
            pg.wait_for_selector("#seg0 .txt")
            no_hscroll = pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
            vis = all((bx := pg.locator(sel).bounding_box()) and bx["x"] >= 0 and bx["x"] + bx["width"] <= w + 1 and bx["y"] + bx["height"] <= h + 1 for sel in ("#btnPlay", "#attNext", "#btnListen", "#tbQuote", "#saveState", ".tab[data-view='export']"))
            res.append(f"{label}: {'ok' if no_hscroll and vis else 'PROBLEEM'}")
        pg.set_viewport_size({"width": 1366, "height": 768})
        pg.locator("#seg0 .txt").click()
        pg.keyboard.press("Tab")
        tab_ok = pg.evaluate("!document.activeElement.classList.contains('txt')")
        pg.keyboard.press("Shift+Tab")
        shift_ok = pg.evaluate("document.activeElement.classList.contains('txt')")
        pg.keyboard.press("Control+End")
        pg.keyboard.type(" K")
        pg.keyboard.press("Control+s")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=10000)
        pg.keyboard.press("Alt+ArrowDown")
        pg.wait_for_timeout(300)
        nav_ok = pg.evaluate("S.curPoint !== null")
        log("12 Toetsenbord, schermgrootte en zoom", tab_ok and shift_ok and nav_ok and all("ok" in r for r in res), "Tab/Shift+Tab = focusnavigatie, Ctrl+S = opslaan, Alt+↓ = volgend aandachtspunt; " + "; ".join(res))
        log("Geen JavaScript-fouten tijdens de doorloop", not errors, "; ".join(errors[:3]))
        b.close()
    srv.should_exit = True
    out = ROOT / "docs" / "verificatie_log.txt"
    out.write_text(f"Minimale verificatie met demo/demo_interview.m4a (fictief), echte transcriptie, {time.strftime('%Y-%m-%d %H:%M')}\n\n" + "\n".join(LOG) + "\n", encoding="utf-8")
    print("logboek:", out)


if __name__ == "__main__":
    main()
