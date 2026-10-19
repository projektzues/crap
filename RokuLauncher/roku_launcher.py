#!/usr/bin/env python3
"""Simple Roku launcher.

Finds Roku devices on your Wi-Fi (SSDP) and serves a minimal web page with
big tiles for your apps plus a few remote buttons. Uses only the Python
standard library and Roku's External Control Protocol (port 8060).

Usage:
    python3 roku_launcher.py                 # discover the TV, serve on :8080
    python3 roku_launcher.py --ip 192.168.1.50
    python3 roku_launcher.py --list          # just print devices and exit
"""
import argparse
import html
import socket
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ECP_PORT = 8060
KEYS = ["Home", "Back", "Up", "Down", "Left", "Right", "Select",
        "Play", "VolumeDown", "VolumeUp", "VolumeMute", "PowerOff"]


def discover(timeout=3.0):
    """Return a list of Roku base URLs found via SSDP, e.g. http://192.168.1.50:8060/."""
    msg = ("M-SEARCH * HTTP/1.1\r\n"
           "HOST: 239.255.255.250:1900\r\n"
           'MAN: "ssdp:discover"\r\n'
           "ST: roku:ecp\r\n"
           "MX: 2\r\n\r\n").encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)
    found = []
    try:
        for _ in range(2):
            sock.sendto(msg, ("239.255.255.250", 1900))
        while True:
            data, _ = sock.recvfrom(4096)
            for line in data.decode(errors="ignore").splitlines():
                if line.lower().startswith("location:"):
                    url = line.split(":", 1)[1].strip()
                    if url not in found:
                        found.append(url)
    except socket.timeout:
        pass
    finally:
        sock.close()
    return found


def ecp(base, path, method="GET"):
    req = urllib.request.Request(base.rstrip("/") + path, method=method,
                                 data=b"" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


def device_name(base):
    try:
        root = ET.fromstring(ecp(base, "/query/device-info")[0])
        return (root.findtext("user-device-name")
                or root.findtext("friendly-device-name")
                or root.findtext("model-name") or base)
    except Exception:
        return base


def list_apps(base):
    root = ET.fromstring(ecp(base, "/query/apps")[0])
    return [(a.get("id"), a.text or a.get("id")) for a in root.findall("app")]


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title><style>
body{{margin:0;font-family:system-ui,sans-serif;background:#111;color:#eee}}
h1{{font-size:1.2rem;margin:16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;padding:0 16px}}
.app{{background:#222;border:0;border-radius:12px;padding:10px;color:#eee;cursor:pointer;font-size:.9rem}}
.app img{{width:100%;aspect-ratio:16/9;object-fit:contain;display:block;margin-bottom:6px}}
.app:active,.key:active{{background:#444}}
.keys{{display:flex;flex-wrap:wrap;gap:8px;padding:16px}}
.key{{background:#333;border:0;border-radius:8px;color:#eee;padding:12px 14px;font-size:1rem;cursor:pointer}}
</style></head><body>
<h1>{name}</h1>
<div class="grid">{apps}</div>
<div class="keys">{keys}</div>
<script>
function send(p){{fetch(p,{{method:'POST'}});}}
</script></body></html>"""


def make_handler(base, name, favorites):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _reply(self, code, body=b"", ctype="text/plain"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/icon/"):
                app_id = urllib.parse.quote(self.path[6:])
                try:
                    body, ctype = ecp(base, "/query/icon/" + app_id)
                    return self._reply(200, body, ctype or "image/png")
                except Exception:
                    return self._reply(404)
            if self.path != "/":
                return self._reply(404)
            try:
                apps = list_apps(base)
            except Exception as e:
                return self._reply(502, f"Could not reach Roku at {base}: {e}".encode())
            if favorites:
                order = {f.lower(): i for i, f in enumerate(favorites)}
                apps = sorted((a for a in apps if a[1].lower() in order),
                              key=lambda a: order[a[1].lower()])
            tiles = "".join(
                f'<button class="app" onclick="send(\'/launch/{html.escape(i)}\')">'
                f'<img src="/icon/{html.escape(i)}" alt="">{html.escape(n)}</button>'
                for i, n in apps)
            keys = "".join(
                f'<button class="key" onclick="send(\'/key/{k}\')">{k}</button>'
                for k in KEYS)
            page = PAGE.format(name=html.escape(name), apps=tiles, keys=keys)
            self._reply(200, page.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            try:
                if self.path.startswith("/launch/"):
                    ecp(base, "/launch/" + urllib.parse.quote(self.path[8:]), "POST")
                elif self.path.startswith("/key/") and self.path[5:] in KEYS:
                    ecp(base, "/keypress/" + self.path[5:], "POST")
                else:
                    return self._reply(404)
                self._reply(200, b"ok")
            except Exception as e:
                self._reply(502, str(e).encode())

    return Handler


def main():
    p = argparse.ArgumentParser(description="Simple Roku launcher")
    p.add_argument("--ip", help="Roku IP address (skip auto-discovery)")
    p.add_argument("--port", type=int, default=8080, help="web page port (default 8080)")
    p.add_argument("--list", action="store_true", help="list Rokus on the network and exit")
    p.add_argument("--only", help='comma-separated app names to show, in order, e.g. "Netflix,YouTube"')
    args = p.parse_args()

    if args.ip:
        bases = [f"http://{args.ip}:{ECP_PORT}/"]
    else:
        print("Searching your network for Roku devices...")
        bases = discover()
    if not bases:
        sys.exit("No Roku found. Make sure this computer is on the same Wi-Fi, and on the TV\n"
                 "set Settings > System > Advanced system settings > Control by mobile apps\n"
                 "> Network access to 'Default' or 'Permissive'. Or pass --ip <tv-ip>.")

    for i, b in enumerate(bases):
        print(f"  [{i}] {device_name(b)}  ({b})")
    if args.list:
        return

    base = bases[0]
    name = device_name(base)
    favorites = [s.strip() for s in args.only.split(",")] if args.only else None
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(base, name, favorites))
    print(f"\nLauncher for '{name}' running. Open http://localhost:{args.port} "
          f"(or this computer's IP on your phone). Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
