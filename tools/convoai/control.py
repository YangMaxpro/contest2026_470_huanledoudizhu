#!/usr/bin/env python3
"""ConvoAI control-plane client. No RTC media, implicit retries or embedded keys."""

import argparse
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.request


class ControlError(Exception):
    pass


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ControlError("Cannot read JSON configuration/state") from exc


def validate(config):
    if not isinstance(config, dict):
        raise ControlError("Configuration must be an object")
    if config.get("api_origin") not in ("https://api.sd-rtn.com", "https://api.agora.io"):
        raise ControlError("Unsupported API origin; HTTPS official hosts only")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", str(config.get("app_id", ""))):
        raise ControlError("app_id must have 32 hexadecimal characters")
    props = config.get("properties")
    if not isinstance(props, dict):
        raise ControlError("properties must be an object")
    for section in ("asr", "llm", "tts"):
        if not isinstance(props.get(section), dict):
            raise ControlError("Missing ASR, LLM or TTS configuration")
    # These are supplied at runtime, never copied from a Studio preview session.
    if any(key in props for key in ("token", "channel", "agent_rtc_uid", "remote_rtc_uids")):
        raise ControlError("Remove preview tokens/channel/UIDs from the template")

    def check_secrets(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in ("api_key", "key", "token", "authorization", "app_certificate", "secret") and child:
                    raise ControlError("Credentials must not be stored in the template")
                check_secrets(child)
        elif isinstance(value, list):
            for child in value:
                check_secrets(child)

    check_secrets(config)
    return config


def build_payload(config, channel, device_uid, agent_uid, agent_token):
    validate(config)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", channel):
        raise ControlError("Use a 1..64 character alphanumeric channel with '-' or '_'")
    for uid in (device_uid, agent_uid):
        if not re.fullmatch(r"[1-9][0-9]{0,9}", str(uid)) or int(uid) > 4294967295:
            raise ControlError("UIDs must be integers from 1 to 4294967295")
    if str(device_uid) == str(agent_uid):
        raise ControlError("Device and agent must have different UIDs")
    if not agent_token or any(ch.isspace() for ch in agent_token):
        raise ControlError("A nonempty agent RTC token is required")
    props = copy.deepcopy(config["properties"])
    props.update(channel=channel, agent_rtc_uid=str(agent_uid),
                 remote_rtc_uids=[str(device_uid)], token=agent_token)
    return {"name": channel, "properties": props}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, config, auth_token, opener=None):
        validate(config)
        if not auth_token or not re.fullmatch(r"[A-Za-z0-9+/=_-]+", auth_token):
            raise ControlError("Invalid REST authentication token")
        self.base = config["api_origin"] + "/cn/api/conversational-ai-agent/v2/projects/" + config["app_id"]
        self.auth_token = auth_token
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def post(self, suffix, payload):
        req = urllib.request.Request(self.base + suffix,
                                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Authorization": 'agora token="' + self.auth_token + '"',
                                              "Content-Type": "application/json"}, method="POST")
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read(1024 * 1024 + 1)
                if not 200 <= response.status < 300 or len(raw) > 1024 * 1024:
                    raise ControlError("Unexpected HTTP status or oversized response")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ControlError("Expected a JSON object response")
                return result
        except urllib.error.HTTPError as exc:
            # Provider bodies can echo request secrets. Do not log them.
            code = exc.code
            exc.close()
            raise ControlError("ConvoAI HTTP error " + str(code) + "; not retried") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ControlError("ConvoAI transport/JSON error; outcome may be unknown; not retried") from None

    def start(self, payload):
        result = self.post("/join", payload)
        agent_id = result.get("agent_id")
        if not isinstance(agent_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", agent_id):
            raise ControlError("Missing/invalid agent_id; creation outcome is unknown")
        return {"agent_id": agent_id, "status": "created"}

    def stop(self, agent_id):
        if not isinstance(agent_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", agent_id):
            raise ControlError("Invalid agent_id")
        self.post("/agents/" + agent_id + "/leave", {})


def write_state(path, state, exclusive=False):
    path = Path(path)
    data = json.dumps(state, indent=2) + "\n"
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return
    fd, tmp = tempfile.mkstemp(prefix=".convoai-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "start", "stop"))
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("studio.json"))
    parser.add_argument("--state", type=Path, default=Path("convoai-session.local.json"))
    parser.add_argument("--channel")
    parser.add_argument("--device-uid", default="1001")
    parser.add_argument("--agent-uid", default="2001")
    parser.add_argument("--live", action="store_true", help="Explicitly allow cloud call; start can incur charges")
    args = parser.parse_args(argv)
    try:
        config = validate(read_json(args.config))
        if args.command == "validate":
            print("Template valid; no cloud request. RTC device integration is still required.")
            return 0
        if not args.live:
            raise ControlError("No request sent: --live is required")
        client = Client(config, os.environ.get("CONVOAI_AUTH_TOKEN", ""))
        if args.command == "start":
            payload = build_payload(config, args.channel or "", args.device_uid, args.agent_uid,
                                    os.environ.get("CONVOAI_AGENT_TOKEN", ""))
            state = {"app_id": config["app_id"], "api_origin": config["api_origin"],
                     "channel": args.channel, "device_uid": args.device_uid,
                     "agent_uid": args.agent_uid, "status": "creation_unknown"}
            # Reserve before POST. A timeout must never cause an automatic duplicate join.
            try:
                write_state(args.state, state, exclusive=True)
            except FileExistsError:
                raise ControlError("Session state already exists; stop/reconcile it before another start") from None
            result = client.start(payload)
            state.update(result)
            try:
                write_state(args.state, state)
            except OSError:
                print("Created agent_id=" + result["agent_id"] + "; state save failed. Preserve this ID to stop it.")
                return 1
            print("Agent created; session recorded. This does not confirm RTC audio is connected.")
        else:
            state = read_json(args.state)
            if not isinstance(state, dict) or any(state.get(k) != config[k] for k in ("app_id", "api_origin")):
                raise ControlError("State belongs to another project/origin")
            if state.get("status") == "stopped":
                print("Already stopped; no request sent.")
                return 0
            if not state.get("agent_id"):
                raise ControlError("Creation outcome unknown; reconcile in console before retrying")
            client.stop(state["agent_id"])
            state["status"] = "stopped"
            write_state(args.state, state)
            print("Agent stopped; state retained for audit. Use a new state filename for another session.")
        return 0
    except (ControlError, OSError) as exc:
        print("Error: " + (str(exc) if isinstance(exc, ControlError) else "Local file operation failed"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
