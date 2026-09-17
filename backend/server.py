"""Portable SCUT backend: Control Center, REST API, and authenticated WebSocket."""
from __future__ import annotations
import argparse
import base64
import hashlib
import ipaddress
import json
import logging
import os
import queue
import select
import socket
import struct
import threading
import time
import sys
from uuid import UUID
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.constants import DEFAULT_PORT, LOGS, MAX_BODY_BYTES, MAX_TRANSCRIPT_CHARS, ROOT
from backend.services import ScutService


def configure_logging() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOGS / "runtime.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class Handler(SimpleHTTPRequestHandler):
    service: ScutService
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=str(ROOT / "frontend"), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if (path.startswith("/api/") or path in {"/health", "/ws"}) and not self.safe_request_host():
            return self.error_json(400, "HOST_DENIED", "Request host is not local")
        if (path.startswith("/api/") or path == "/health") and not self.is_loopback_request():
            return self.error_json(403, "LOCAL_ONLY", "REST API access is limited to this computer")
        if path == "/api/status":
            return self.respond(200, self.service.status())
        if path == "/health":
            return self.respond(200, {"ok": True, "protocolVersion": 1})
        if path in {"/api/history", "/api/alerts"}:
            query = parse_qs(parsed.query)
            try:
                limit = max(1, min(int(query.get("limit", ["25"])[0]), 50))
            except ValueError:
                return self.error_json(422, "VALIDATION_ERROR", "limit must be an integer")
            cursor = query.get("cursor", [None])[0]
            result = self.service.control_plane.list_history(cursor, limit) if path == "/api/history" else self.service.control_plane.list_alerts(cursor, limit)
            return self.respond(200, result)
        if path.startswith("/api/history/"):
            conversation_id = path.rsplit("/", 1)[1]
            if not self.valid_uuid(conversation_id):
                return self.error_json(422, "VALIDATION_ERROR", "conversation id must be a UUID")
            result = self.service.control_plane.conversation_detail(conversation_id)
            if result is None:
                return self.error_json(404, "CONVERSATION_NOT_FOUND", "Conversation is unavailable")
            return self.respond(200, result)
        if path == "/api/diagnostics/recording":
            recording = ROOT / "diagnostics" / "test_call.wav"
            if not recording.is_file() or not self.service.audio_status.get("selected"):
                return self.error_json(404, "NO_RECORDING", "No verified Phone Link recording is available")
            content = recording.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if path == "/ws":
            return self.websocket()
        if path == "/":
            self.path = "/index.html"
        if path.startswith("/api/"):
            return self.error_json(404, "NOT_FOUND", "Unknown API endpoint")
        return super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if not self.safe_request_host():
                return self.error_json(400, "HOST_DENIED", "Request host is not local")
            if not self.is_loopback_request():
                return self.error_json(403, "LOCAL_ONLY", "REST API access is limited to this computer")
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                return self.error_json(415, "JSON_REQUIRED", "Content-Type must be application/json")
            if not self.same_origin_request():
                return self.error_json(403, "ORIGIN_DENIED", "Cross-origin requests are not accepted")
            body = self.json_body()
            if path == "/api/mode":
                mode = body.get("mode")
                if mode not in {"OFF", "TEST", "PROTECT"}:
                    return self.error_json(422, "VALIDATION_ERROR", "mode must be OFF, TEST, or PROTECT")
                return self.respond(200, self.service.set_mode(mode))
            if path == "/api/pair":
                host = self.headers.get("Host", "127.0.0.1").split(":")[0]
                return self.respond(201, self.service.pairing_payload(host))
            if path == "/api/transcripts":
                text = body.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > MAX_TRANSCRIPT_CHARS:
                    return self.error_json(422, "VALIDATION_ERROR", "text must be a non-empty stable transcript under 4000 characters")
                return self.respond(200, self.service.transcript(text.strip()))
            if path == "/api/alerts/test":
                from backend.classifier import Decision, Risk
                alert = self.service.send_alert(Decision(Risk.CRITICAL, "Explicit test alert", "TEST"), "SMS code", synthetic=True)
                return self.respond(200, {"ok": True, "alert": alert})
            if path == "/api/history/delete":
                conversation_id = body.get("conversationId")
                if not isinstance(conversation_id, str) or not self.valid_uuid(conversation_id):
                    return self.error_json(422, "VALIDATION_ERROR", "conversationId must be a UUID")
                if not self.service.control_plane.delete_conversation(conversation_id):
                    return self.error_json(404, "CONVERSATION_NOT_FOUND", "Conversation is unavailable")
                return self.respond(200, {"deleted": True})
            if path.startswith("/api/diagnostics/"):
                name = path.rsplit("/", 1)[1]
                if name not in {"capture", "earbuds", "network", "predemo", "guarded-transcription"}:
                    return self.error_json(404, "NOT_FOUND", "Unknown diagnostic")
                source = body.get("source", "EXPLICIT_TEST_BUTTON")
                if source != "EXPLICIT_TEST_BUTTON":
                    return self.error_json(422, "VALIDATION_ERROR", "capture is explicit-only")
                return self.respond(200, self.service.diagnostic(name, source))
            return self.error_json(404, "NOT_FOUND", "Unknown API endpoint")
        except ValueError as error:
            return self.error_json(400, "INVALID_JSON", str(error))
        except Exception:
            logging.exception("request failure")
            return self.error_json(500, "INTERNAL_ERROR", "Request could not be completed; see runtime log")

    def json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > MAX_BODY_BYTES:
            raise ValueError("Request body must be between 1 and 65536 bytes")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise ValueError("Body must be valid UTF-8 JSON") from err
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    @staticmethod
    def valid_uuid(value: str) -> bool:
        try:
            return str(UUID(value)) == value.lower()
        except (ValueError, AttributeError):
            return False

    def safe_request_host(self) -> bool:
        hostname = urlparse("//" + self.headers.get("Host", "")).hostname
        if not hostname:
            return False
        normalized = hostname.rstrip(".").lower()
        if normalized == "localhost" or normalized.endswith(".local"):
            return True
        try:
            address = ipaddress.ip_address(normalized)
            return address.is_private or address.is_loopback or address.is_link_local
        except ValueError:
            return "." not in normalized and normalized.replace("-", "").isalnum()

    def same_origin_request(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return origin.rstrip("/").lower() == ("http://" + self.headers.get("Host", "")).lower()

    def same_origin_websocket_request(self) -> bool:
        """Allow the packaged Electron renderer while retaining the loopback boundary.

        Electron loads the installed UI from ``file://``. Its WebSocket handshake
        therefore has a ``file://`` Origin even though the socket itself is local.
        """
        if self.same_origin_request():
            return True
        origin = self.headers.get("Origin", "").rstrip("/").lower()
        return self.is_loopback_request() and origin == "file:"

    @staticmethod
    def is_loopback_address(value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
            if address.is_loopback:
                return True
            return address.version == 6 and address.ipv4_mapped is not None and address.ipv4_mapped.is_loopback
        except ValueError:
            return False

    def is_loopback_request(self) -> bool:
        return self.is_loopback_address(self.client_address[0])

    def respond(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def error_json(self, status: int, code: str, message: str) -> None:
        self.respond(status, {"error": {"code": code, "message": message}})

    def websocket(self) -> None:
        if not self.same_origin_websocket_request():
            return self.error_json(403, "ORIGIN_DENIED", "Cross-origin WebSocket requests are not accepted")
        if self.headers.get("Upgrade", "").lower() != "websocket":
            return self.error_json(400, "WEBSOCKET_REQUIRED", "Use a WebSocket upgrade request")
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            return self.error_json(400, "WEBSOCKET_KEY_REQUIRED", "Missing Sec-WebSocket-Key")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        # Do not put BufferedReader into timeout state: once that occurs, later
        # reads can raise "cannot read from timed out object" and drop a valid WS.
        self.connection.settimeout(None)
        session_id, outbound = self.service.register_session()
        device_id = None
        trusted_local = self.is_loopback_request()
        try:
            self.ws_send({"type": "hello", "protocolVersion": 1})
            while True:
                readable, _, _ = select.select([self.connection], [], [], 0.2)
                if readable:
                    try:
                        message = self.ws_read()
                        if message is None:
                            break
                        data = json.loads(message)
                        if not isinstance(data, dict):
                            raise ValueError("message must be object")
                        kind = data.get("type")
                        if kind == "pair":
                            paired = self.service.pair(str(data.get("token", "")), str(data.get("device", "")), str(data.get("appVersion", "")), data.get("permissions", {}))
                            self.ws_send(paired or {"type": "error", "code": "PAIRING_DENIED"})
                            if paired:
                                device_id = paired["deviceId"]
                        elif kind == "auth":
                            auth = self.service.authenticate(str(data.get("credential", "")))
                            if not auth:
                                self.ws_send({"type": "error", "code": "AUTH_DENIED"})
                                break
                            device_id = auth[0]
                            self.ws_send({"type": "authenticated", "status": self.service.status()})
                        elif kind == "heartbeat" and device_id:
                            self.service.heartbeat(device_id, data)
                            self.ws_send({"type": "heartbeat", "ok": True})
                        elif kind == "ack" and device_id:
                            self.service.acknowledge(str(data.get("alertId", "")), data.get("sentMonotonic"))
                        elif kind == "ping":
                            self.ws_send({"type": "pong", "clientTimestamp": data.get("clientTimestamp")})
                        elif kind == "subscribe" and (trusted_local or device_id):
                            self.ws_send({"type": "status", "status": self.service.status()})
                        else:
                            self.ws_send({"type": "error", "code": "AUTH_REQUIRED" if kind == "subscribe" else "INVALID_MESSAGE"})
                    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                        self.ws_send({"type": "error", "code": "INVALID_MESSAGE"})
                if trusted_local or device_id:
                    try:
                        while True:
                            self.ws_send(outbound.get_nowait())
                    except queue.Empty:
                        pass
        except (ConnectionError, BrokenPipeError, OSError):
            pass
        finally:
            self.service.unregister_session(session_id)

    def ws_read(self) -> str | None:
        first = self.rfile.read(2)
        if len(first) < 2:
            return None
        opcode = first[0] & 15
        masked, size = bool(first[1] & 128), first[1] & 127
        if opcode == 8:
            return None
        if opcode != 1 or not masked:
            raise ValueError("expected masked text frame")
        if size == 126:
            size = struct.unpack("!H", self.rfile.read(2))[0]
        elif size == 127:
            size = struct.unpack("!Q", self.rfile.read(8))[0]
        if size > MAX_BODY_BYTES:
            raise ValueError("message too large")
        mask = self.rfile.read(4)
        payload = bytearray(self.rfile.read(size))
        if len(payload) != size:
            return None
        for index in range(size):
            payload[index] ^= mask[index % 4]
        return payload.decode("utf-8")

    def ws_send(self, value: dict) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        size = len(payload)
        if size < 126:
            header = bytes([129, size])
        elif size < 65536:
            header = bytes([129, 126]) + struct.pack("!H", size)
        else:
            header = bytes([129, 127]) + struct.pack("!Q", size)
        self.connection.sendall(header + payload)


def find_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free SCUT port in safe range")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    configure_logging()
    port = find_port(args.port)
    service = ScutService(port)
    Handler.service = service
    service.start_control_plane_worker()
    server = ThreadingHTTPServer((args.host, port), Handler)
    print(f"SCUT Control Center: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        service.stop_control_plane_worker()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
