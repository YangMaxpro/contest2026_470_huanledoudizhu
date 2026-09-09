"""Server-side token adapter for the official R1 Python token builder.

No network, certificate persistence or token logging. This is not an HTTP API.
"""

import importlib
from pathlib import Path
import re
import sys
import threading
import time

from control import ControlError, build_payload


class TokenIssuer:
    def __init__(self, config, certificate, builder, ttl=900):
        if not isinstance(certificate, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", certificate):
            raise ControlError("Server App certificate must have 32 hexadecimal characters")
        if not isinstance(ttl, int) or isinstance(ttl, bool) or not 60 <= ttl <= 3600:
            raise ControlError("Token lifetime must be 60..3600 seconds")
        self.config = config
        self.certificate = certificate
        self.builder = builder
        self.ttl = ttl
        self.lock = threading.Lock()

    def issue(self, channel, device_uid, agent_uid):
        build_payload(self.config, channel, device_uid, agent_uid, "syntax-check-only")
        issued_at = int(time.time())
        with self.lock:
            # Use the vendor's combined RTC/RTM builder, not a hand-written signer.
            result = {}
            for name, uid in (("device_token", device_uid), ("agent_token", agent_uid)):
                token = self.builder.build_token_with_rtm(
                    self.config["app_id"], self.certificate, channel, str(uid),
                    1, self.ttl, self.ttl)
                if not isinstance(token, str) or not token.startswith("007"):
                    raise ControlError("Official token builder failed")
                result[name] = token
        result.update(app_id=self.config["app_id"], channel=channel,
                      device_uid=str(device_uid), agent_uid=str(agent_uid),
                      issued_at=issued_at, expires_at=issued_at + self.ttl)
        return result


def load_official_builder(directory):
    """Load explicitly chosen, trusted official source; never load demo config."""
    directory = Path(directory).resolve()
    names = ("Packer", "AccessToken2", "RtcTokenBuilder2")
    for name in names:
        path = directory / (name + ".py")
        if not path.is_file():
            raise ControlError("Official token builder source files are missing")
        loaded = sys.modules.get(name)
        if loaded is not None and Path(getattr(loaded, "__file__", "")).resolve() != path:
            raise ControlError("A different token builder is already imported")
    sys.path.insert(0, str(directory))
    try:
        # Resolve helpers from the same directory even if another path is present.
        for name in names:
            importlib.import_module(name)
        return sys.modules["RtcTokenBuilder2"].RtcTokenBuilder
    except (ImportError, AttributeError) as exc:
        raise ControlError("Cannot load the official R1 token builder") from None
    finally:
        sys.path.remove(str(directory))
