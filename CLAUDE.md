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
- The official app's setting DP map, exact 32-byte alarm encode/decode, full custom API action list, and Tuya account/pairing flow are documented in `notes/apk-2.08-findings.md`.
- **Vendor security finding (2026-09-15):** the app authenticates into Tuya's cloud using hardcoded, shared/pooled Tuya account credentials (plaintext email+password embedded in the APK) rather than per-customer accounts — recoverable by anyone who decompiles the public APK. Actual credential values are kept out of the public repo in gitignored `notes/local-only-tuya-pool-credentials.md`. Do not use these credentials; see that file's "Recommended handling" section.
- JADX-based static analysis of the app is essentially complete: full settings-write flow per DP, taken-status/day-code enums, and a confirmed negative finding (no app-side "dispense now" command exists anywhere — dispensing is driven by the device's own alarm schedule) are also in `notes/apk-2.08-findings.md`.
- **Blocked on hardware as of 2026-09-15: the user does not have the physical dispenser yet.** Remaining unknowns (Tuya product ID, live DP schema, any local LAN protocol) all need a live pairing capture — don't keep re-reading app source for protocol findings, remaining unread files are UI/analytics/billing plumbing.
- Manifest has no `networkSecurityConfig`; default Android 24+ behavior means a future capture session needs root (system CA install) or a Frida-based approach — a plain user-installed proxy CA won't be trusted. See "Network/traffic-capture planning notes" in `notes/apk-2.08-findings.md`.

## Guardrails

- Stay within the user's own device, account, phone, and network — this now explicitly includes never logging into the shared Tuya pool accounts found in static analysis, since those accounts plausibly control other customers' devices too.
- Never store or expose credentials, tokens, raw personal captures, or identifiers. Any live/sensitive credential discovered (vendor's or otherwise) goes only in a gitignored `notes/local-only-*` file, never in a file that gets committed.
- Never test dispensing against medication. Explicit user approval and safe empty-device conditions are required before any dispense-related experiment.
- Git is initialized and pushed to the public repo `SusieeTheLinuxUser/dosecontrol-re` on GitHub. Keep `apk/*.apk`, `decoded/`, `tools/`, `captures/*`, and `notes/local-only-*` out of history (see `.gitignore`) — only hashes, sanitized excerpts, scripts, and notes get committed. Ask before force-pushing or rewriting history.
- Update this file and `AGENTS.md` after any meaningful chunk of work (new findings, completed steps, changed plans) — the user switches between Claude, ChatGPT/Codex, Qwen, Kimi, and Z.ai, and these files are the only handoff mechanism between them.

## Best next move

Static analysis (custom API, Tuya account/home flow, every DP read/write, alarm encoding) is done — see `notes/apk-2.08-findings.md`. **The project is currently blocked on the user acquiring a physical dispenser.** The real next step needs it: pair it in a controlled network to observe its live Tuya product ID and DP schema, capturing one owner-controlled change at a time. Until then, the only useful work is optional (e.g. scaffolding a `src/` client against confirmed findings) — don't invent busywork or re-derive things already documented.
