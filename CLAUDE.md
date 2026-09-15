# Medicine Doser — continuation brief

Read `AGENTS.md`, `README.md`, and the files in `notes/` before acting. This project is early-stage personal-use research for an owner-controlled DoseControl WiFi pill dispenser; it is not yet a working controller.

## State as of 2026-09-15

- Android app extracted from the owner-controlled device:
  - package `lb.android.dosecontrol`
  - version `2.08` / code `87`
  - base SHA-256 `831b34cc386eddddb186cf316ad4a3a44a484303347877e853b037e80cefe44f`
- Static evidence shows Tuya/ThingClips SDK, Tuya-style data points and MQTT.
- Pairing instructions in the APK use `SmartLife-XXXX` AP mode.
- DoseControl's additional backend is `https://dcapi.lost-bytes.com/api`.
- Upstream JADX `1.5.6` is already available in `tools/jadx/`, and output is in `decoded/jadx-2.08/`.
- The official app's setting DP map and 32-byte alarm encoding are documented in `notes/apk-2.08-findings.md`.
- See `notes/apk-2.08-findings.md` for endpoints and exact evidence.

## Guardrails

- Stay within the user's own device, account, phone, and network.
- Never store or expose credentials, tokens, raw personal captures, or identifiers.
- Never test dispensing against medication. Explicit user approval and safe empty-device conditions are required before any dispense-related experiment.
- Git is initialized and pushed to the public repo `SusieeTheLinuxUser/dosecontrol-re` on GitHub. Keep `apk/*.apk`, `decoded/`, `tools/`, and `captures/*` out of history (see `.gitignore`) — only hashes, sanitized excerpts, scripts, and notes get committed. Ask before force-pushing or rewriting history.

## Best next move

Inspect the existing JADX output for the remaining DoseControl API behavior, Tuya account/home flow, product ID handling, and data-point read/write calls. Write evidence-backed findings to `notes/`; label assumptions clearly.
