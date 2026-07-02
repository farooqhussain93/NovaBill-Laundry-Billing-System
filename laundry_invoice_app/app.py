from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import unquote, urlparse

from .api import AppAPI
from .config import APP_NAME, ASSETS_DIR, WEB_DIR
from .database import init_db
from .logger import get_logger


class QuietStaticHandler(SimpleHTTPRequestHandler):
    """Small local static server for the HTML/CSS/JS frontend.

    Security note: only the web frontend and the assets folder are exposed.
    Runtime data such as data/, backups/, invoices/ and logs/ is deliberately
    not served over the local HTTP server.
    """

    def translate_path(self, path: str) -> str:
        parsed_path = unquote(urlparse(path).path)
        if parsed_path.startswith("/assets/"):
            base = ASSETS_DIR.resolve()
            relative = parsed_path[len("/assets/"):].lstrip("/")
        else:
            base = WEB_DIR.resolve()
            relative = parsed_path.lstrip("/") or "index.html"

        destination = (base / relative).resolve()
        try:
            destination.relative_to(base)
        except ValueError:
            return str(base / "__blocked__")
        return str(destination)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _start_static_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietStaticHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/index.html"
    return server, url


def run() -> None:
    logger = get_logger()
    logger.info("Starting NovaBill Laundry")
    init_db()
    import webview  # imported here so backend services are testable without pywebview installed

    api = AppAPI()
    server, url = _start_static_server()

    webview.create_window(
        APP_NAME,
        url=url,
        js_api=api,
        width=1280,
        height=820,
        min_size=(1100, 720),
        text_select=True,
    )

    try:
        webview.start(debug=False)
    finally:
        logger.info("Shutting down NovaBill Laundry")
        server.shutdown()
        server.server_close()
