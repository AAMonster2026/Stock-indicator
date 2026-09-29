"""Local static server with Yahoo Finance proxy for the investment watch app."""

from __future__ import annotations

import http.server
import json
import signal
import socket
import socketserver
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PORT = 8080
ROOT = Path(__file__).resolve().parent
DATA_FILES = {
    "watchlist_v1.json",
    "portfolio_v1.json",
    "custom_sectors_v1.json",
    "cash_deposits_v1.json",
    "realized_trades_v1.json",
}
YAHOO_HOSTS = (
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        if self.path.startswith("/api/yahoo/"):
            self.proxy_yahoo()
            return
        if self.path.startswith("/api/data/"):
            self.read_data_file()
            return
        super().do_GET()

    def do_PUT(self) -> None:
        if self.path.startswith("/api/data/"):
            self.write_data_file()
            return
        self.send_error(405, "Method Not Allowed")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def read_data_file(self) -> None:
        filename = self._data_filename()
        if not filename:
            return

        file_path = ROOT / filename
        if not file_path.exists():
            self._json_response(404, {"error": f"{filename} not found"})
            return

        try:
            payload = file_path.read_text(encoding="utf-8")
            json.loads(payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))
        except json.JSONDecodeError:
            self._json_response(500, {"error": f"{filename} is not valid JSON"})
        except OSError as error:
            self._json_response(500, {"error": str(error)})

    def write_data_file(self) -> None:
        filename = self._data_filename()
        if not filename:
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b""
        try:
            parsed = json.loads(raw_body.decode("utf-8") or "[]")
        except json.JSONDecodeError:
            self._json_response(400, {"error": "Request body must be valid JSON"})
            return

        if not isinstance(parsed, list):
            self._json_response(400, {"error": "JSON root must be an array"})
            return

        file_path = ROOT / filename
        try:
            file_path.write_text(
                json.dumps(parsed, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._json_response(200, {"ok": True, "file": filename, "count": len(parsed)})
        except OSError as error:
            self._json_response(500, {"error": str(error)})

    def _data_filename(self) -> str | None:
        filename = self.path.removeprefix("/api/data/").split("?", 1)[0]
        if filename not in DATA_FILES:
            self._json_response(403, {"error": "File not allowed"})
            return None
        return filename

    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def proxy_yahoo(self) -> None:
        yahoo_path = self.path.removeprefix("/api/yahoo")
        last_error = "Yahoo Finance proxy failed"

        for host in YAHOO_HOSTS:
            url = f"{host}{yahoo_path}"
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = response.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "public, max-age=60")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
            except urllib.error.HTTPError as error:
                last_error = f"Yahoo HTTP {error.code}"
            except Exception as error:  # noqa: BLE001 - surface proxy failures to client
                last_error = str(error)

        body = f'{{"error":"{last_error}"}}'.encode("utf-8")
        self.send_response(502)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        if str(args[0]).startswith("GET /api/yahoo"):
            return
        super().log_message(format, *args)


class ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def parse_port() -> int:
    if len(sys.argv) > 1:
        try:
            return int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)
    return DEFAULT_PORT


def port_is_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def print_port_help(port: int) -> None:
    print(f"\nPort {port} is already in use.")
    print("Another server is still running (often an old CMD window).")
    print("\nQuick fix:")
    print("  1. Double-click stop.bat")
    print("  2. Then double-click start.bat")
    print("\nManual fix:")
    print(f"  netstat -ano | findstr :{port}")
    print("  taskkill /F /PID <PID>")


def main() -> None:
    port = parse_port()

    if port_is_busy(port):
        print_port_help(port)
        sys.exit(1)

    httpd = ThreadingServer(("127.0.0.1", port), Handler)

    def shutdown(_signum=None, _frame=None) -> None:
        print("\nStopping server...")
        httpd.shutdown()
        httpd.server_close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, shutdown)

    print(f"Serving at http://127.0.0.1:{port}")
    print(f"Open http://127.0.0.1:{port}/index.html in your browser")
    print("Press Ctrl+C to stop")
    print("Tip: use start.bat / stop.bat to avoid port conflicts")

    try:
        httpd.serve_forever()
    except OSError as error:
        if getattr(error, "winerror", None) == 10048 or "already in use" in str(error).lower():
            print_port_help(port)
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
