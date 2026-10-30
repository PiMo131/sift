"""Neemt de demovideo op (docs/demo.mp4 en docs/demo.gif) met Playwright en ffmpeg, tegen een draaiende Sift.

Gebruik:
    # 1. eigen server op een lege projectmap, nooit tegen de eigen interviews:
    #    $env:SIFT_PROJECTS="<tijdelijke map>"; python -m sift --no-browser --port 8773 --lan
    # 2. eenmalig het demo-interview verwerken (echte transcriptie, ongeveer een minuut):
    python demo/record_demo.py --url http://127.0.0.1:8773 --prepare
    # 3. opnemen en omzetten:
    python demo/record_demo.py --url http://127.0.0.1:8773 [--ffmpeg <pad naar ffmpeg.exe>]

Alleen het fictieve demo-interview (demo/demo_interview.m4a) wordt gebruikt. De opname laat achtereenvolgens zien:
startpagina en nieuw onderzoek/interview, de verwerking (kort, op een tweede interview), de nakijkmodus (woord
afspelen, aandachtspunten, correctie met autosave, "Klopt zo", citaat, spreker), modellen vergelijken, de
Word-export met vervangingstabel en het Telefoon/QR-venster. Korte Nederlandse onderschriften worden in de pagina
gezet. De webm van Playwright wordt met ffmpeg naar H.264 omgezet; het hoogtepunt wordt een gif voor de README.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "demo" / "demo_interview.m4a"
DOCS = ROOT / "docs"
W, H = 1440, 900

# Zichtbare muisaanwijzer: Playwright neemt de cursor niet op, dus tekenen we er zelf een die de muis volgt.
CURSOR_JS = """
(() => {
  const mk = () => {
    if (document.getElementById('demoCursor')) return;
    const c = document.createElement('div'); c.id = 'demoCursor';
    c.innerHTML = '<svg width="26" height="34" viewBox="0 0 26 34"><path d="M2 2 L2 26 L8 20 L12 31 L16 29 L12 19 L20 19 Z" fill="#fff" stroke="#111" stroke-width="2" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: 'fixed', left: '-40px', top: '-40px', zIndex: 2147483647, pointerEvents: 'none', transition: 'transform .08s' });
    document.documentElement.appendChild(c);
    document.addEventListener('mousemove', e => { c.style.left = e.clientX - 2 + 'px'; c.style.top = e.clientY - 2 + 'px'; }, true);
    document.addEventListener('mousedown', () => { c.style.transform = 'scale(.8)'; }, true);
    document.addEventListener('mouseup', () => { c.style.transform = ''; }, true);
  };
  if (document.documentElement) mk(); else document.addEventListener('DOMContentLoaded', mk);
})();
"""


class Demo:
    def __init__(self, page, t0: float):
        self.pg = page
        self.t0 = t0
        self.marks: list[tuple[str, float]] = []
        self.mx, self.my = W // 2, H // 2

    # ---------- hulpmiddelen ----------
    def mark(self, label: str) -> None:
        self.marks.append((label, time.time() - self.t0))
        print(f"{time.time() - self.t0:6.1f}s  {label}", flush=True)

    def pause(self, s: float) -> None:
        self.pg.wait_for_timeout(int(s * 1000))

    def caption(self, text: str | None) -> None:
        self.pg.evaluate(
            """t => { let d = document.getElementById('demoCap');
                 if (!t) { if (d) d.remove(); return; }
                 if (!d) { d = document.createElement('div'); d.id = 'demoCap';
                   Object.assign(d.style, { position: 'fixed', left: '50%', bottom: '86px', transform: 'translateX(-50%)',
                     background: 'rgba(17,24,39,.88)', color: '#fff', font: '600 19px/1.35 system-ui, Segoe UI, sans-serif',
                     padding: '10px 18px', borderRadius: '10px', zIndex: 2147483646, pointerEvents: 'none', maxWidth: '72%',
                     boxShadow: '0 6px 24px rgba(0,0,0,.25)', textAlign: 'center' });
                   document.documentElement.appendChild(d); }
                 d.textContent = t; }""",
            text,
        )

    def glide(self, x: float, y: float, steps: int = 24) -> None:
        self.pg.mouse.move(x, y, steps=steps)
        self.mx, self.my = x, y

    def click(self, selector: str, pause_after: float = 1.2, nth: int = 0) -> None:
        loc = self.pg.locator(selector).nth(nth)
        loc.scroll_into_view_if_needed()
        box = loc.bounding_box()
        if not box:
            raise RuntimeError(f"niet zichtbaar: {selector}")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.glide(x, y)
        self.pause(0.35)
        self.pg.mouse.down(); self.pause(0.08); self.pg.mouse.up()
        self.pause(pause_after)

    def type(self, text: str, delay: int = 45) -> None:
        self.pg.keyboard.type(text, delay=delay)

    def slow_scroll(self, px: int, step: int = 60, every: float = 0.08) -> None:
        for _ in range(abs(px) // step):
            self.pg.mouse.wheel(0, step if px > 0 else -step)
            self.pause(every)

    # ---------- het verhaal ----------
    def run(self, base: str) -> None:
        pg = self.pg
        pg.goto(base + "/")
        pg.wait_for_selector("#btnCreate")
        self.glide(W * 0.55, H * 0.4, steps=5)
        self.mark("start")
        self.caption("Sift: van interviewopname naar een gecontroleerd transcript, op je eigen computer.")
        self.pause(4.5)
        self.glide(W * 0.3, H * 0.4)
        self.pause(1.5)

        # 1. nieuw onderzoek + nieuw interview
        self.caption("Een onderzoek bundelt interviews met een gedeelde woordenlijst en afspraken.")
        self.click("#newStudy")
        self.type("Leven met reuma (pilot)")
        self.pause(0.8)
        self.click("#pOk", 2.2)
        pg.wait_for_function("document.querySelectorAll('#newStudySel option').length >= 2")
        self.caption("Nieuw interview: opname kiezen, taal en aantal sprekers opgeven, namen en vaktermen meegeven.")
        self.pause(1.5)
        self.glide(*self._center("#drop"))
        self.pause(0.8)
        pg.set_input_files("#fileInput", str(AUDIO))
        self.pause(1.8)
        self.click("#newName")
        pg.keyboard.press("Control+a")
        self.type("Demo R02")
        self.pause(0.6)
        self.click("#newStudySel", 0.4)
        pg.select_option("#newStudySel", label="Leven met reuma (pilot)")
        self.pause(0.6)
        self.click("#newLang", 0.4)
        pg.select_option("#newLang", "nl")
        self.pause(0.6)
        self.click("#newSpk", 0.4)
        pg.select_option("#newSpk", "2")
        self.pause(0.6)
        self.click("#newTerms")
        self.type("methotrexaat, reumaverpleegkundige, Zwolle")
        self.pause(2.0)
        self.mark("transcript maken")
        self.caption("Sift kiest zelf passende modellen voor deze computer; klik op Transcript maken.")
        self.pause(1.5)
        self.click("#btnCreate", 1.0)

        # 2. verwerking (kort)
        pg.wait_for_selector("#pipe .step", timeout=60000)
        self.mark("verwerking")
        self.caption("De verwerking laat in gewone taal zien wat er gebeurt; de opname verlaat de computer niet.")
        self.glide(W * 0.5, H * 0.55)
        self.pause(8.0)
        self.caption("Na een halve tot enkele minuten staat het transcript klaar, afhankelijk van je computer.")
        self.pause(5.0)
        self.caption("Intussen kijken we een interview na dat al klaar is.")
        self.pause(3.0)
        self.caption(None)

        # 3. nakijken op het eerder verwerkte interview
        self.click(".tab[data-view='home']", 1.0)
        pg.wait_for_selector("#home .item")
        self.click("#home .item[data-id='Demo_R01']", 1.5)
        pg.wait_for_selector("#seg0 .txt")
        self.mark("editor")
        self.caption("Nakijken: het transcript met de audio ernaast. Aandachtspunten zijn gemarkeerd.")
        self.glide(W * 0.45, H * 0.45)
        self.pause(4.0)
        self.caption("Klik op een woord: je hoort het fragment en ziet wat elk model hoorde.")
        self.click("w[data-s='1'][data-w='4']", 4.5)
        self.caption("Volgend aandachtspunt brengt je langs de passages die aandacht nodig hebben.")
        self.click("#attNext", 3.0)
        self.click("#attNext", 3.0)
        self.caption("Klopt het? Dan bevestig je met Klopt zo; de score van het model blijft bewaard.")
        self.mark("klopt zo")
        self.click("#ptOk", 3.0)
        self.caption("Tekst corrigeer je gewoon in het transcript; Sift slaat automatisch op.")
        self.click("#seg2 .txt", 0.5)
        pg.keyboard.press("Control+End")
        self.type(" (gecontroleerd)")
        pg.wait_for_function("document.querySelector('#saveState').classList.contains('saved')", timeout=10000)
        self.glide(*self._center("#saveState"))
        self.pause(3.0)
        self.caption("Een mooi citaat markeer je met een ster; het komt later apart in de citatenlijst.")
        self.mark("citaat")
        self.click("#seg4 .txt", 0.5)
        self.click("#tbQuote", 2.5)
        self.caption("Verkeerde spreker? Klik op de naam en kies de juiste.")
        self.click("#seg5 .sp", 1.2)
        cur = pg.evaluate("S.tr.segments[5].speaker")
        self.click(".dropdown button[data-id='S2']" if cur == "S1" else ".dropdown button[data-id='S1']", 1.5)
        self.caption("Sprekers krijgen hun naam in het overzicht links.")
        self.click("#side input[data-sp='S1']", 0.3)
        pg.keyboard.press("Control+a")
        self.type("Interviewer")
        pg.keyboard.press("Enter")
        self.pause(0.6)
        self.click("#side input[data-sp='S2']", 0.3)
        pg.keyboard.press("Control+a")
        self.type("Anna de Vries")
        pg.keyboard.press("Enter")
        self.pause(2.5)
        self.caption(None)

        # 4. modellen vergelijken
        self.mark("vergelijken")
        self.click(".tab[data-view='compare']", 1.0)
        pg.wait_for_selector("#cmpList .grid, #cmpList .sub")
        self.caption("Modellen vergelijken: waar de spraakmodellen het oneens zijn, zie je alle lezingen naast elkaar.")
        self.glide(W * 0.5, H * 0.6)
        self.pause(2.5)
        self.slow_scroll(900, every=0.1)
        self.pause(2.5)
        self.caption(None)

        # 5. exporteren (Word) met vervangingstabel
        self.mark("export")
        self.click(".tab[data-view='export']", 1.0)
        pg.wait_for_selector("#ePreview")
        self.caption("Exporteren naar Word, MAXQDA, NVivo of een citatenlijst, met een voorbeeld.")
        self.click("[data-p='word']", 2.5)
        self.caption("Namen en herkenbare gegevens vervang je met een tabel; het origineel blijft ongewijzigd.")
        self.click("#ePsOn", 1.5)
        rows = pg.locator("#psTable input[data-ps='find']").count()  # sprekernamen staan er al in
        self.click("#psAdd", 0.6)
        self.click(f"#psTable input[data-ps='find'][data-i='{rows}']", 0.3)
        self.type("Zwolle")
        self.click(f"#psTable input[data-ps='replace'][data-i='{rows}']", 0.3)
        pg.keyboard.press("Control+a")
        self.type("[plaats1]")
        pg.keyboard.press("Tab")
        pg.wait_for_function("document.querySelector('#ePreview').textContent.includes('[plaats1]')", timeout=10000)
        self.glide(*self._center("#ePreview"))
        self.pause(3.0)
        self.caption("Downloaden maakt het Word-bestand, met controleoverzicht en regelnummers als je dat wilt.")
        with pg.expect_download():
            self.click("#eGo", 2.0)
        self.pause(2.0)
        self.caption(None)

        # 6. telefoon / QR
        self.mark("telefoon")
        self.caption("Vanaf je telefoon: scan de QR, stuur een opname naar de pc of kijk daar het transcript na.")
        self.click("#btnPhone", 1.0)
        pg.wait_for_selector(".modal .qr")
        self._mask_phone()
        self.pause(5.0)
        self.click("#phClose", 1.0)
        self.caption("Sift: github.com/PiMo131/sift")
        self.glide(W * 0.5, H * 0.45)
        self.pause(3.5)
        self.caption(None)
        self.mark("einde")

    def _mask_phone(self) -> None:
        """Toont in de video een voorbeeldadres en -code in plaats van het echte netwerkadres van deze computer."""
        import base64, io
        import qrcode, qrcode.image.svg
        url, code = "http://192.168.1.23:8765/", "4821"
        img = qrcode.make(f"{url}?code={code}", image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
        buf = io.BytesIO(); img.save(buf)
        src = "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()
        self.pg.evaluate("""([src, url, code]) => { const m = document.querySelector('.modal'); if (!m) return;
            m.querySelector('.qr').src = src; m.querySelector('.url').textContent = url; m.querySelector('.code').textContent = code;
            m.querySelectorAll('.sub').forEach(d => { if (d.textContent.includes('Dit adres is')) d.innerHTML = 'Zelfde wifi vereist (geen gasten-netwerk). Dit adres is 192.168.1.23. Start Sift met <span class="kbd">--lan</span> om netwerktoegang meteen aan te zetten.'; }); }""",
            [src, url, code])

    def _center(self, selector: str) -> tuple[float, float]:
        b = self.pg.locator(selector).bounding_box()
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def prepare(base: str) -> None:
    """Maakt onderzoek + interview Demo R01 aan en wacht tot de echte transcriptie klaar is."""
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(viewport={"width": W, "height": H}).new_page()
        pg.goto(base + "/")
        pg.wait_for_selector("#btnCreate")
        pg.click("#newStudy"); pg.fill("#pIn", "Leven met reuma"); pg.click("#pOk")
        pg.wait_for_selector("#home [data-study]")
        pg.locator("#home [data-study]").first.click()
        pg.fill("#stTerms", "methotrexaat, reumaverpleegkundige, dokter Pieters"); pg.click("#stSave")
        pg.wait_for_function("document.querySelectorAll('#newStudySel option').length >= 2", timeout=10000)
        pg.fill("#newName", "Demo R01")
        pg.set_input_files("#fileInput", str(AUDIO))
        pg.select_option("#newStudySel", index=1); pg.select_option("#newLang", "nl"); pg.select_option("#newSpk", "2")
        pg.fill("#newTerms", "Zwolle, Kampen")
        pg.click("#btnCreate")
        pg.wait_for_selector("#pipe .step", timeout=60000)
        pg.wait_for_function("S.meta && S.meta.status === 'klaar'", timeout=1200000)
        print("klaar:", pg.evaluate("S.pid"))
        b.close()


def record(base: str, workdir: Path) -> tuple[Path, list[tuple[str, float]]]:
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": W, "height": H}, device_scale_factor=1, accept_downloads=True,
                            record_video_dir=str(workdir), record_video_size={"width": W, "height": H})
        ctx.add_init_script(CURSOR_JS)
        pg = ctx.new_page()
        t0 = time.time()
        d = Demo(pg, t0)
        d.run(base)
        video = pg.video
        ctx.close()
        path = Path(video.path())
        b.close()
    return path, d.marks


def convert(ffmpeg: str, webm: Path, marks: list[tuple[str, float]], workdir: Path) -> None:
    DOCS.mkdir(exist_ok=True)
    mp4 = DOCS / "demo.mp4"
    subprocess.run([ffmpeg, "-y", "-i", str(webm), "-an", "-c:v", "libx264", "-crf", "28", "-preset", "slow", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-r", "25", str(mp4)], check=True)
    # gif: hoogtepunt uit de nakijkmodus (woord aanklikken, aandachtspunt, Klopt zo, correctie met autosave)
    t = dict(marks)
    start, end = t.get("editor", 0) + 2.5, t.get("citaat", t.get("editor", 0) + 28)
    if end - start > 28:
        end = start + 28
    palette = workdir / "palette.png"
    filt = "fps=10,scale=960:-1:flags=lanczos"
    subprocess.run([ffmpeg, "-y", "-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", str(mp4), "-vf", f"{filt},palettegen=max_colors=128:stats_mode=diff", str(palette)], check=True)
    subprocess.run([ffmpeg, "-y", "-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", str(mp4), "-i", str(palette), "-lavfi",
                    f"{filt}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle", "-loop", "0", str(DOCS / "demo.gif")], check=True)
    print("mp4:", mp4, f"{mp4.stat().st_size / 1048576:.1f} MB")
    print("gif:", DOCS / "demo.gif", f"{(DOCS / 'demo.gif').stat().st_size / 1048576:.1f} MB", f"({start:.0f}-{end:.0f} s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8773")
    ap.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    ap.add_argument("--prepare", action="store_true", help="alleen het demo-interview verwerken (eenmalig vooraf)")
    ap.add_argument("--workdir", default=None, help="map voor webm en palet (standaard tijdelijk)")
    a = ap.parse_args()
    if a.prepare:
        prepare(a.url)
        return
    workdir = Path(a.workdir) if a.workdir else Path(tempfile.mkdtemp(prefix="sift_demo_"))
    workdir.mkdir(parents=True, exist_ok=True)
    webm, marks = record(a.url, workdir)
    (workdir / "marks.json").write_text(json.dumps(marks, indent=1), encoding="utf-8")
    print("webm:", webm)
    convert(a.ffmpeg, webm, marks, workdir)


if __name__ == "__main__":
    main()
