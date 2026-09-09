# R1 ConvoAI control plane

This is a standard-library Python control client and single-device control
service, not an RTC audio implementation. It does not enable RTSA in the OpenVela firmware.
No cloud request has been performed by the automated tests.

`studio.json` preserves the user's Studio ASR/LLM/TTS resource references and
turn detection settings. Public App ID/resource IDs are project-specific, not
credentials. Preview channel names, UIDs and tokens were deliberately removed.
`enable_dump` is changed to false to avoid opting into diagnostic dumps by
default. Transcript/RTM settings are otherwise retained; this does not imply
the board currently consumes RTM transcripts. Studio resource authorization
outside the browser still needs a live integration check.

## Offline checks (no account or network required)

From this directory:

```sh
python3 control.py validate
python3 -m unittest -v test_control.py test_tokens.py test_server.py
```

## Live lifecycle (not needed until RTC device integration is ready)

The project must have ConvoAI enabled. Generate fresh tokens server-side using
the official token builder; do not use the disclosed certificate/preview tokens.
Keep the App certificate and provider credentials off the board and out of git.
`tokens.py` wraps the official R1 `RtcTokenBuilder2.py`, `AccessToken2.py` and
`Packer.py` modules without modifying them or reading the demo's config.json.
Use `AGORA_TOKEN_BUILDER_DIR` when testing to include the real builder test;
that test uses fake credentials, decodes RTC/RTM privileges and makes no calls.

Supply `CONVOAI_AUTH_TOKEN` and `CONVOAI_AGENT_TOKEN` through the process
environment/secret manager. They are distinct inputs even if a permitted Studio
workflow uses one token for both. The latter must authorize the configured
channel/agent UID and the required RTC/RTM privileges for the retained settings.
The board needs its own RTC token for the same channel and a different UID.
This client validates input syntax, not token signature, scope or expiry.

Explicit user-initiated commands (start may incur charges):

```sh
python3 control.py start --live --channel r1-test-001 --device-uid 1001 --agent-uid 2001 --state session-001.local.json
python3 control.py stop --live --state session-001.local.json
```

No implicit retry or redirect is allowed. API responses are not printed because
they may echo secrets. A state file is reserved *before* creation; failures leave
`creation_unknown` to prevent duplicate billable agents. Reconcile ambiguous
creation in the console using the recorded channel/name, and stop any created
agent before trying a fresh session. State stores IDs only, never tokens.
Successfully stopped state is retained; use a new filename for the next session.
The 120-second idle timeout is not a hard billing limit; explicitly stop sessions.

## Single-device service

`server.py` provides POST `/device` (empty JSON object), `/agent/start`
(`channel_name`, `uid`, `agent_uid`, all strings returned by `/device`), and
`/agent/stop` (`agent_id` returned by start). `/device` allocates the channel and
UIDs instead of trusting arbitrary caller-selected identities. It returns only
the device token, never the certificate or the agent token. These are explicit
adapter contracts, not a claim of drop-in binary compatibility with the old demo.

All POSTs require `Authorization: Bearer <DEVICE_CONTROL_SECRET>`. Keep this
provisioning secret separate from the App certificate and give it to the trusted
device through local provisioning. The certificate is supplied only through
`AGORA_APP_CERTIFICATE` on the server. Rotate the disclosed certificate first.
Do not paste either value into chat or command-line arguments.

After supplying those environment variables securely, an offline-only listener:

```sh
python3 server.py --token-builder-dir /home/yang/agora/server/aiot_server_demo_example --port 5001
```

By default it listens only on localhost and rejects start/stop cloud operations.
Explicit `--live` enables those operations. A non-loopback `--listen` also
requires `--tls-cert` and `--tls-key`. Board trust of that TLS certificate is a
separate provisioning step; do not disable verification. Tokens last 15 minutes;
device renewal/session lifetime handling is still required before long calls.
Run only one service process per state file. There is no cross-process lock,
multi-device management or production HTTP hardening; do not expose it publicly.
GET `/health` is local service health, not RTC or cloud-agent health.

Remaining: board HTTP provisioning client/TLS trust, RTSA lifecycle/native tests,
full-duplex vendor audio/AEC adaptation, then end-to-end on-board verification.
