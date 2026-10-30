"""Maakt de screenshots voor de README met Playwright, tegen een draaiende Sift met het fictieve demo-interview.

Gebruik:  python docs/screenshots.py [--url http://127.0.0.1:8770] [--pid Demo-interview_R01] [--only home,process,editor,export]
De schermafbeeldingen komen in docs/. Alleen fictieve demodata gebruiken (zie demo/).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8770")
    ap.add_argument("--pid", default="Demo-interview_R01")
    ap.add_argument("--only", default="home,process,editor,export,compare,study,small")
    a = ap.parse_args()
    only = set(a.only.split(","))
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        pg = ctx.new_page()
        _goto = pg.goto

        def goto(u):  # een hash-navigatie binnen hetzelfde document herlaadt de app niet; daarom eerst weg
            _goto("about:blank")
            return _goto(u)
        pg.goto = goto
        if "home" in only:
            pg.goto(a.url + "/")
            pg.wait_for_selector("#home .study, #home .sub")
            pg.wait_for_timeout(500)
            pg.screenshot(path=str(OUT / "screenshot_home.png"))
        if "process" in only:
            pg.goto(f"{a.url}/#p={a.pid}&v=process")
            pg.wait_for_selector("#pipe .step")
            pg.wait_for_timeout(800)
            pg.screenshot(path=str(OUT / "screenshot_process.png"))
        if "editor" in only:
            pg.goto(f"{a.url}/#p={a.pid}&v=editor")
            pg.wait_for_selector("#seg0 .txt")
            pg.click("#attNext")
            pg.wait_for_timeout(600)
            pg.screenshot(path=str(OUT / "screenshot_editor.png"))
        if "export" in only:
            pg.goto(f"{a.url}/#p={a.pid}&v=export")
            pg.wait_for_selector("#ePreview")
            pg.check("#ePsOn")
            pg.wait_for_timeout(1200)
            pg.screenshot(path=str(OUT / "screenshot_export.png"))
        if "compare" in only:
            pg.goto(f"{a.url}/#p={a.pid}&v=compare")
            pg.wait_for_selector("#cmpList .grid, #cmpList .sub")
            pg.wait_for_timeout(500)
            pg.screenshot(path=str(OUT / "screenshot_compare.png"))
        if "study" in only:
            pg.goto(a.url + "/")
            pg.wait_for_selector("#home [data-study]")
            pg.locator("#home [data-study]").first.click()
            pg.wait_for_selector("#stSave")
            pg.wait_for_timeout(400)
            pg.screenshot(path=str(OUT / "screenshot_study.png"))
        if "small" in only:
            pg2 = b.new_context(viewport={"width": 911, "height": 512}).new_page()  # 1366×768 bij 150 % zoom
            pg2.goto(f"{a.url}/#p={a.pid}&v=editor")
            pg2.wait_for_selector("#seg0 .txt")
            pg2.wait_for_timeout(600)
            pg2.screenshot(path=str(OUT / "screenshot_editor_1366x768_150pct.png"))
        b.close()
    print("screenshots in", OUT)


if __name__ == "__main__":
    main()
