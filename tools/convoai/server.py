#!/usr/bin/env python3
"""Single-device R1 control service; RTC media does not pass through this server."""

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import ssl
import threading

from control import Client, ControlError, build_payload, read_json, validate, write_state
from tokens import TokenIssuer, load_official_builder


class Service:
    def __init__(self, config, issuer, state_path, client_factory=Client, allow_live=False):
        self.config = validate(config)
        self.issuer = issuer
        self.state_path = Path(state_path)
        self.client_factory = client_factory
        self.allow_live = allow_live
        self.lock = threading.Lock()

    def state(self):
        state = read_json(self.state_path)
        if not isinstance(state, dict) or any(state.get(k) != self.config[k] for k in ("app_id", "api_origin")):
            raise ControlError("State project/origin mismatch")
        return state

    def pair(self, state):
        return self.issuer.issue(state["channel"], state["device_uid"], state["agent_uid"])

    def dispatch(self, route, body):
        if not isinstance(body, dict):
            raise ControlError("Expected a JSON object")
        with self.lock:
            if route == "/device":
                if body:
                    raise ControlError("POST /device takes {}; this service allocates channel and UIDs")
                state = self.state() if self.state_path.exists() else None
                if state and state.get("status") not in ("prepared", "created", "stopped"):
                    raise ControlError("Reconcile the unknown cloud session in console first")
                if state is None or state["status"] == "stopped":
                    state = {"app_id": self.config["app_id"], "api_origin": self.config["api_origin"],
                             "channel": "r1-" + secrets.token_hex(12),
                             "device_uid": "1001", "agent_uid": "2001", "status": "prepared"}
                    pair = self.pair(state)
                    write_state(self.state_path, state, exclusive=not self.state_path.exists())
                else:
                    pair = self.pair(state)
                return {"app_id": state["app_id"], "channel_name": state["channel"],
                        "uid": state["device_uid"], "agent_uid": state["agent_uid"],
                        "token": pair["device_token"], "expires_at": pair["expires_at"]}
            if route not in ("/agent/start", "/agent/stop"):
                raise ControlError("Unknown route")
            if not self.allow_live:
                raise ControlError("Cloud lifecycle disabled; server needs explicit --live")
            state = self.state()
            if route == "/agent/start":
                expected = {"channel_name": state["channel"], "uid": state["device_uid"],
                            "agent_uid": state["agent_uid"]}
                if body != expected:
                    raise ControlError("Start must use exactly the provisioned channel and UIDs")
                if state.get("status") == "created":
                    return {"agent_id": state["agent_id"], "status": "created"}
                if state.get("status") != "prepared":
                    raise ControlError("Session not prepared or creation outcome unknown; no retry")
                pair = self.pair(state)
                payload = build_payload(self.config, state["channel"], state["device_uid"],
                                        state["agent_uid"], pair["agent_token"])
                client = self.client_factory(self.config, pair["agent_token"])
                state["status"] = "creation_unknown"
                write_state(self.state_path, state)
                result = client.start(payload)
                state.update(result)
                try:
                    write_state(self.state_path, state)
                except OSError:
                    # Returning the non-secret ID keeps manual cleanup possible.
                    return {"agent_id": result["agent_id"], "status": "created_state_save_failed"}
                return result
            if not state.get("agent_id") or body != {"agent_id": state["agent_id"]}:
                raise ControlError("Stop must identify this device's recorded agent")
            if state["status"] == "stopped":
                return {"status": "stopped"}
            pair = self.pair(state)
            self.client_factory(self.config, pair["agent_token"]).stop(state["agent_id"])
            state["status"] = "stopped"
            write_state(self.state_path, state)
            return {"status": "stopped"}


def make_handler(service, device_secret):
    if not isinstance(device_secret, str) or not device_secret.isascii() or len(device_secret) < 32 or any(c.isspace() for c in device_secret):
        raise ControlError("DEVICE_CONTROL_SECRET requires at least 32 non-whitespace ASCII characters")
    expected = ("Bearer " + device_secret).encode("ascii")

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass

        def reply(self, status, body):
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"service": "convoai-control", "rtc_media": False})
            else:
                self.reply(404, {"error": "Not found"})

        def do_POST(self):
            raw = None
            try:
                length = int(self.headers.get("Content-Length", ""))
                if len(self.headers.get_all("Content-Length", [])) == 1 and not self.headers.get("Transfer-Encoding") and 0 <= length <= 8193:
                    # Drain bounded bodies before rejection so closing the TCP
                    # connection does not discard the HTTP error via an RST.
                    raw = self.rfile.read(length)
            except (ValueError, OSError):
                self.reply(400, {"error": "Invalid or incomplete request"})
                return
            if not hmac.compare_digest(self.headers.get("Authorization", "").encode("utf-8"), expected):
                self.reply(401, {"error": "Unauthorized"})
                return
            if self.path not in ("/device", "/agent/start", "/agent/stop"):
                self.reply(404, {"error": "Not found"})
                return
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                self.reply(400, {"error": "One Content-Length required; no chunked requests"})
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                self.reply(415, {"error": "Use application/json"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
                if not 0 < length <= 8192:
                    self.reply(413, {"error": "Request size must be 1..8192 bytes"})
                    return
                if raw is None or len(raw) != length:
                    self.reply(400, {"error": "Incomplete request"})
                    return
                body = json.loads(raw)
                result = service.dispatch(self.path, body)
                self.reply(200, result)
            except (ValueError, UnicodeError):
                self.reply(400, {"error": "Invalid JSON/length"})
            except ControlError as exc:
                self.reply(409, {"error": str(exc)})
            except Exception:
                # Never expose token builder/HTTP exceptions or request contents.
                self.reply(500, {"error": "Control operation failed; inspect session state before retry"})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("studio.json"))
    parser.add_argument("--state", type=Path, default=Path("convoai-session.local.json"))
    parser.add_argument("--token-builder-dir", type=Path, required=True)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if bool(args.tls_cert) != bool(args.tls_key):
        parser.error("Supply both TLS certificate and key")
    if args.listen not in ("127.0.0.1", "localhost") and not args.tls_cert:
        parser.error("Non-loopback binding requires TLS; do not transmit device tokens over LAN HTTP")
    try:
        config = validate(read_json(args.config))
        issuer = TokenIssuer(config, os.environ.get("AGORA_APP_CERTIFICATE", ""),
                             load_official_builder(args.token_builder_dir))
        service = Service(config, issuer, args.state, allow_live=args.live)
        handler = make_handler(service, os.environ.get("DEVICE_CONTROL_SECRET", ""))
        with HTTPServer((args.listen, args.port), handler) as server:
            if args.tls_cert:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.load_cert_chain(args.tls_cert, args.tls_key)
                server.socket = context.wrap_socket(server.socket, server_side=True)
            print("Control server ready; cloud lifecycle " + ("enabled" if args.live else "disabled"))
            server.serve_forever()
    except ControlError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
