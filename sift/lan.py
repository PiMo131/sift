"""Bereikbaarheid vanaf de telefoon: LAN-adres, 4-cijferige code, toegangscontrole en QR.

De server luistert altijd op 0.0.0.0; verzoeken die niet van loopback komen worden pas toegelaten
als `enabled` aanstaat én de code klopt (query ?code=, cookie sift_code of header X-Sift-Code).
"""
from __future__ import annotations

import ipaddress
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

COOKIE = "sift_code"
MAX_FAILS = 5
BLOCK_S = 60
# Paden die zonder code bereikbaar zijn (de dropfase zelf, statische bestanden en de PWA-bestanden).
OPEN_PATHS = ("/drop", "/manifest.webmanifest", "/sw.js", "/api/ping")
OPEN_PREFIXES = ("/static/",)
# Adapters die nooit het wifi-adres zijn.
SKIP_ADAPTERS = ("vethernet", "wsl", "virtualbox", "vmware", "hyper-v", "docker", "zerotier", "tailscale",
                 "openvpn", "wireguard", "bluetooth", "loopback", "pseudo", "tap-", "npcap")


class State:
    def __init__(self):
        self.enabled = False
        self.port = 8765
        self.code = self.new_code()
        self._fails: dict[str, list[float]] = {}
        self._blocked: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def new_code() -> str:
        return f"{secrets.randbelow(10000):04d}"

    def regenerate(self) -> str:
        self.code = self.new_code()
        with self._lock:
            self._fails.clear()
            self._blocked.clear()
        return self.code

    # ---- mislukte pogingen per client-IP ----
    def is_blocked(self, ip: str) -> bool:
        with self._lock:
            until = self._blocked.get(ip, 0)
            if until > time.time():
                return True
            self._blocked.pop(ip, None)
            return False

    def fail(self, ip: str) -> None:
        now = time.time()
        with self._lock:
            lst = [t for t in self._fails.get(ip, []) if now - t < BLOCK_S]
            lst.append(now)
            self._fails[ip] = lst
            if len(lst) >= MAX_FAILS:
                self._blocked[ip] = now + BLOCK_S
                self._fails[ip] = []

    def ok(self, ip: str) -> None:
        with self._lock:
            self._fails.pop(ip, None)


state = State()


# ---------- adressen ----------
def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host in ("localhost", "::1", "127.0.0.1"):
        return True
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        return ip.is_loopback
    except ValueError:
        return False


def _rank(name: str, ip: ipaddress.IPv4Address) -> int | None:
    low = name.lower()
    if any(k in low for k in SKIP_ADAPTERS):
        return None
    if ip.is_loopback:
        return None
    r = 2
    if any(k in low for k in ("wi-fi", "wifi", "wlan", "wireless", "draadloos")):
        r = 0
    elif "ethernet" in low:
        r = 1
    if ip.is_link_local:
        r += 10
    elif not ip.is_private:
        r += 5
    return r


def lan_ips() -> list[str]:
    """Beste LAN-IPv4-adressen van deze machine, wifi eerst, RFC1918 vóór de rest."""
    found: list[tuple[int, str]] = []
    try:
        import psutil
        stats = psutil.net_if_stats()
        for name, addrs in psutil.net_if_addrs().items():
            st = stats.get(name)
            if st is not None and not st.isup:
                continue
            for a in addrs:
                if a.family != socket.AF_INET:
                    continue
                try:
                    ip = ipaddress.IPv4Address(a.address)
                except ValueError:
                    continue
                r = _rank(name, ip)
                if r is not None:
                    found.append((r, a.address))
    except Exception:
        pass
    if not found:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            found.append((0, s.getsockname()[0]))
            s.close()
        except Exception:
            pass
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = ipaddress.IPv4Address(info[4][0])
                r = _rank("", ip)
                if r is not None:
                    found.append((r + 1, info[4][0]))
        except Exception:
            pass
    out, seen = [], set()
    for _, ip in sorted(found):
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out


def best_ip() -> str | None:
    ips = lan_ips()
    return ips[0] if ips else None


def url(ip: str | None = None) -> str:
    return f"http://{ip or best_ip() or '127.0.0.1'}:{state.port}/?code={state.code}"


def info() -> dict:
    ip = best_ip()
    return {"ip": ip, "port": state.port, "code": state.code, "url": url(ip), "lan": state.enabled,
            "enabled": state.enabled, "ips": lan_ips(), "firewall": firewall_status()}


# ---------- firewall (Windows, best effort, gecached) ----------
_fw_cache: dict = {}


def firewall_status() -> str:
    """'allowed' | 'blocked' | 'none' (Windows kan dan bij de eerste verbinding een melding tonen) | 'unknown'."""
    if not sys.platform.startswith("win"):
        return "unknown"
    if "v" in _fw_cache and time.time() - _fw_cache["t"] < 30:
        return _fw_cache["v"]
    val = "unknown"
    try:
        out = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule", "name=all", "dir=in", "verbose"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        exe = sys.executable.lower()
        allowed = blocked = False
        block: list[str] = []
        for line in out.splitlines() + [""]:
            if line.strip() == "" and block:
                txt = "\n".join(block).lower()
                if exe in txt and "enabled:" in txt and "yes" in txt.split("enabled:")[1].split("\n")[0]:
                    act = txt.split("action:")[1].split("\n")[0] if "action:" in txt else ""
                    if "allow" in act or "toestaan" in act:
                        allowed = True
                    elif "block" in act or "blokk" in act:
                        blocked = True
                block = []
            else:
                block.append(line)
        val = "blocked" if blocked else "allowed" if allowed else "none"
    except Exception:
        val = "unknown"
    _fw_cache.update(v=val, t=time.time())
    return val


# ---------- QR ----------
def qr_svg(data: str) -> bytes:
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    return img.to_string()


# ---------- ASGI-middleware ----------
CODE_PAGE = """<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sift · code</title><style>body{font:16px system-ui,sans-serif;background:#f6f5f1;color:#1f2328;margin:0;padding:24px;display:flex;justify-content:center}
.box{background:#fff;border:1px solid #e6e3dc;border-radius:14px;padding:22px;max-width:380px;width:100%%;margin-top:40px}h1{font-size:20px;margin:0 0 6px}p{color:#6b7280;margin:0 0 16px}
input{width:100%%;box-sizing:border-box;font-size:28px;letter-spacing:.4em;text-align:center;padding:12px;border:1px solid #d9d6ce;border-radius:10px}
button{margin-top:12px;width:100%%;padding:12px;font-size:16px;font-weight:600;background:#2f855a;color:#fff;border:0;border-radius:10px}.err{color:#b42318;margin-top:8px}</style></head>
<body><form class="box" method="get"><h1>Sift</h1><p>Voer de 4-cijferige code in die op het scherm van de computer staat (knop Telefoon).</p>
<input name="code" inputmode="numeric" pattern="[0-9]*" maxlength="4" autocomplete="one-time-code" autofocus>%s<button>Verder</button></form></body></html>"""


def _hdr(scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == name:
            return v.decode("latin-1")
    return None


def _client_ip(scope) -> str:
    c = scope.get("client")
    return c[0] if c else ""


class CodeMiddleware:
    """Laat loopback altijd door; anders: LAN aan + juiste code, met cookie na ?code=."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        ip = _client_ip(scope)
        path = scope.get("path", "")
        is_api = path.startswith("/api/")
        if is_loopback(ip) or path in OPEN_PATHS or path.startswith(OPEN_PREFIXES):
            return await self.app(scope, receive, send)
        if not state.enabled:
            return await self._deny(send, 403, "LAN uit", is_api, "Deze Sift is niet opengesteld voor het netwerk. Zet op de computer 'Bereikbaar op het netwerk' aan (knop Telefoon).")
        if state.is_blocked(ip):
            return await self._deny(send, 429, "te veel pogingen, wacht een minuut", is_api, "Te veel verkeerde codes. Probeer het over een minuut opnieuw.")
        qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        from_query = (qs.get("code") or [None])[0]
        cookie = SimpleCookie(_hdr(scope, b"cookie") or "")
        from_cookie = cookie[COOKIE].value if COOKIE in cookie else None
        given = from_query or _hdr(scope, b"x-sift-code") or from_cookie
        if given is None or not secrets.compare_digest(given.strip(), state.code):
            if given is not None:
                state.fail(ip)
            return await self._deny(send, 401, "code", is_api, "Verkeerde code." if given is not None else "")
        state.ok(ip)
        set_cookie = from_query is not None and from_cookie != state.code

        async def send_wrapped(message):
            if set_cookie and message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"set-cookie", f"{COOKIE}={state.code}; Path=/; Max-Age={30 * 86400}; SameSite=Lax".encode()))
                message = {**message, "headers": headers}
            await send(message)

        return await self.app(scope, receive, send_wrapped)

    async def _deny(self, send, status: int, detail: str, is_api: bool, html_msg: str):
        if is_api:
            import json
            body = json.dumps({"detail": detail}).encode()
            ctype = b"application/json"
        else:
            err = f'<div class="err">{html_msg}</div>' if html_msg else ""
            body = (CODE_PAGE % err).encode("utf-8")
            ctype = b"text/html; charset=utf-8"
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", ctype), (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})
