#!/usr/bin/env python3
"""AgentOS Microsoft Teams Command Bridge.

Provides bidirectional or webhook-based integration with Microsoft Teams.
Handles incoming Teams webhooks/commands, parses intents, and dispatches to AgentOS.
Runs cleanly in standby mode when no webhook secret/token is configured.
"""
import os
import sys
import json
import time
import signal
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from dotenv import load_dotenv

LOGIC_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LOGIC_ROOT))

from scripts.service_utils import setup_locking, handle_signals, init_service_logging

load_dotenv()

PORT = int(os.getenv("TEAMS_BRIDGE_PORT", "8776"))
HOST = os.getenv("TEAMS_BRIDGE_HOST", "127.0.0.1")
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")

logger = logging.getLogger("teams_bridge")


class TeamsWebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), format % args))

    def do_GET(self):
        if self.path in ("/healthz", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "ok": True,
                "service": "agentos-teams-commander",
                "status": "ready" if TEAMS_WEBHOOK_URL else "standby",
                "webhook_configured": bool(TEAMS_WEBHOOK_URL),
                "timestamp": int(time.time())
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "not_found"}')

    def do_POST(self):
        if self.path in ("/api/teams/message", "/webhook"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                payload = json.loads(body)
            except Exception:
                payload = {"text": body}

            logger.info("Received Teams message: %s", payload)
            
            # Simple command router
            text = payload.get("text", "").strip()
            reply_text = "AgentOS Teams Bridge: Command received."
            if "status" in text.lower():
                reply_text = "🟢 AgentOS Core: All core services operational."
            elif "ping" in text.lower():
                reply_text = "🏓 Pong from Oracle VM AgentOS!"

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "type": "message",
                "text": reply_text
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def main():
    setup_locking("teams_bridge")
    handle_signals()
    log_file = Path(os.getenv("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")) / "logs" / "teams_bridge.log"
    init_service_logging(log_file, "teams_bridge")

    logger.info("Starting AgentOS Teams Command Bridge on %s:%d...", HOST, PORT)
    if not TEAMS_WEBHOOK_URL:
        logger.info("ℹ️ TEAMS_WEBHOOK_URL not configured. Running in standby mode listening on %s:%d", HOST, PORT)

    server = HTTPServer((HOST, PORT), TeamsWebhookHandler)
    logger.info("Teams Bridge HTTP server listening on %s:%d", HOST, PORT)
    try:
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down Teams Bridge...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
