"""YouTube through home: a tiny proxy on the home PC for the server (docs/VPS.md, 3e).

YouTube asks the server's IP (a data centre's) to sign in; your home connection it lets through. This proxy lets the
server's yt-dlp reach YouTube from your PC: only YouTube/Google video addresses (anything else is refused), only
through Tailscale (it listens on the Tailscale address, never on the internet), and it barely uses the PC: it only
passes bytes along. Standard library only.

    python scripts/casa/proxy_youtube.py            (or double-click proxy-youtube.bat)
"""

from __future__ import annotations

import select
import socket
import subprocess
import sys
import threading
import time

PORT = 8899
ALLOWED = (".youtube.com", ".googlevideo.com", ".ytimg.com", ".ggpht.com", ".youtube-nocookie.com",
           ".googleapis.com", ".google.com", ".gstatic.com", ".youtu.be")
STATS = {"open": 0, "bytes": 0}
LOCK = threading.Lock()


def allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d[1:] or host.endswith(d) for d in ALLOWED)


def tailscale_ip() -> str | None:
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=10).stdout.split()
        return out[0] if out else None
    except (OSError, subprocess.SubprocessError):
        return None


def pipe(a: socket.socket, b: socket.socket) -> None:
    sockets = [a, b]
    try:
        while True:
            ready, _, broken = select.select(sockets, [], sockets, 120)
            if broken or not ready:
                return
            for s in ready:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
                with LOCK:
                    STATS["bytes"] += len(data)
    except OSError:
        return


def handle(client: socket.socket) -> None:
    upstream = None
    try:
        client.settimeout(30)
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 16384:
            chunk = client.recv(4096)
            if not chunk:
                return
            head += chunk
        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        method, target, _ = (line.split(" ") + ["", ""])[:3]
        if method.upper() != "CONNECT":                  # yt-dlp and ffmpeg use HTTPS: CONNECT only
            client.sendall(b"HTTP/1.1 405 Only CONNECT\r\n\r\n")
            return
        host, _, port = target.rpartition(":")
        if not allowed(host) or port != "443":
            client.sendall(b"HTTP/1.1 403 Only YouTube\r\n\r\n")
            return
        upstream = socket.create_connection((host, 443), timeout=30)
        client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        client.settimeout(None)
        upstream.settimeout(None)
        with LOCK:
            STATS["open"] += 1
        pipe(client, upstream)
    except OSError:
        pass
    finally:
        with LOCK:
            STATS["open"] = max(0, STATS["open"] - (1 if upstream else 0))
        for s in (client, upstream):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass


def report() -> None:
    last = 0
    while True:
        time.sleep(60)
        with LOCK:
            total, open_now = STATS["bytes"], STATS["open"]
        if total != last:
            print(f"{time.strftime('%H:%M')} · {total / 1e9:.2f} GB pasados al servidor · {open_now} conexiones abiertas",
                  flush=True)
            last = total


def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else tailscale_ip()
    if not host:
        sys.exit("No encuentro Tailscale: instálalo (tailscale.com/download), inicia sesión y vuelve a abrir esto.")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, PORT))
    server.listen(64)
    print(f"Proxy de YouTube para el servidor en http://{host}:{PORT} (solo YouTube, solo por Tailscale).")
    print(f"En el servidor, en config.local.yaml:  sourcing: {{youtube: {{proxy: http://{host}:{PORT}}}}}")
    print("Deja esta ventana abierta (puedes minimizarla). Ctrl+C para cerrar.", flush=True)
    threading.Thread(target=report, daemon=True).start()
    while True:
        client, _ = server.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
