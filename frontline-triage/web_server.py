"""
web_server.py — Built-in local HTTP web server for the FRONTLINE Web UI

Features:
- Serves static files from the 'web/' directory
- Implements REST JSON API endpoints:
  - GET  /api/messages     (get preloaded messages)
  - POST /api/triage       (triage single custom input)
  - GET  /api/triage-all   (triage all preloaded messages)
  - GET  /api/evaluate     (run accuracy scoring and evaluation)
- Zero extra dependencies required
"""

import os
import json
import sys
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse

# Reconfigure terminal encoding to UTF-8 on Windows to prevent UnicodeEncodeError
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-12s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("web_server")

# ── Import pipeline modules ───────────────────────────────────────────────────
# Add current directory to path if not already present
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from guardrails import process_message
from evaluate import run_evaluation

PORT = 8000
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class TriageRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Override default server stderr print and use our logger
        logger.info(f"{self.address_string()} - {format % args}")

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # ── API Endpoint Routing ──────────────────────────────────────────────
        if path == "/api/messages":
            self._send_json_file(os.path.join(DATA_DIR, "dummy_messages.json"))
            return

        elif path == "/api/triage-all":
            self._handle_triage_all()
            return

        elif path == "/api/evaluate":
            self._handle_evaluate()
            return

        # ── Static File Routing ───────────────────────────────────────────────
        if path == "/" or path == "/index.html":
            file_path = os.path.join(WEB_DIR, "index.html")
        else:
            # Clean path to prevent directory traversal
            clean_path = path.lstrip("/")
            file_path = os.path.join(WEB_DIR, clean_path)

        # Security check: Ensure file is inside the WEB_DIR
        real_web_dir = os.path.realpath(WEB_DIR)
        real_file_path = os.path.realpath(file_path)

        if not real_file_path.startswith(real_web_dir):
            self.send_error(403, "Access Denied (Traversal Prevention)")
            return

        if os.path.exists(real_file_path) and os.path.isfile(real_file_path):
            self._serve_file(real_file_path)
        else:
            # Fallback to index.html for SPA router-like behavior if file not found
            fallback_index = os.path.join(WEB_DIR, "index.html")
            if os.path.exists(fallback_index):
                self._serve_file(fallback_index)
            else:
                self.send_error(404, "File Not Found")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/triage":
            self._handle_triage()
            return
        else:
            self.send_error(404, "Endpoint Not Found")

    def do_OPTIONS(self):
        # Handle CORS preflight requests
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_file(self, file_path):
        _, ext = os.path.splitext(file_path)
        content_type = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }.get(ext.lower(), "application/octet-stream")

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error(f"Error serving file {file_path}: {e}")
            self.send_error(500, "Internal Server Error")

    def _send_json(self, data, status=200):
        try:
            content = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error(f"Error writing JSON response: {e}")
            self.send_error(500, "Internal Server Error")

    def _send_json_file(self, file_path, status=200):
        if not os.path.exists(file_path):
            self._send_json({"error": "File not found"}, 404)
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._send_json(data, status)
        except Exception as e:
            logger.error(f"Error reading JSON file {file_path}: {e}")
            self._send_json({"error": "Invalid file structure"}, 500)

    def _handle_triage(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            req_body = json.loads(post_data)

            text = req_body.get("text", "")
            hint_format = req_body.get("format", "text")
            message_id = req_body.get("message_id", "playground_msg")

            logger.info(f"Playground Triage: len={len(text)} format={hint_format}")
            result = process_message(text, message_id=message_id, hint_format=hint_format)
            self._send_json(result)
        except Exception as e:
            logger.error(f"Triage error: {e}")
            self._send_json({"error": str(e)}, 500)

    def _handle_triage_all(self):
        try:
            msg_file = os.path.join(DATA_DIR, "dummy_messages.json")
            if not os.path.exists(msg_file):
                self._send_json({"error": "Messages file not found"}, 404)
                return

            with open(msg_file, "r", encoding="utf-8") as f:
                messages = json.load(f)

            logger.info(f"Batch Triage: processing {len(messages)} messages...")
            results = []
            for msg in messages:
                msg_id = msg.get("id", "unknown")
                raw_input = msg.get("raw_input", "")
                fmt_hint = msg.get("format", None)

                result = process_message(raw_input, message_id=msg_id, hint_format=fmt_hint)
                result["id"] = msg_id
                results.append(result)

            self._send_json(results)
        except Exception as e:
            logger.error(f"Batch triage error: {e}")
            self._send_json({"error": str(e)}, 500)

    def _handle_evaluate(self):
        try:
            logger.info("Evaluation requested. Loading accuracy report...")
            report = run_evaluation()
            self._send_json(report)
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            self._send_json({"error": str(e)}, 500)


def main():
    # Make sure web directory exists before running
    if not os.path.exists(WEB_DIR):
        os.makedirs(WEB_DIR)

    server_address = ("", PORT)
    httpd = HTTPServer(server_address, TriageRequestHandler)
    logger.info(f"FRONTLINE Web Server running at: http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nShutting down web server...")
        httpd.server_close()


if __name__ == "__main__":
    main()
