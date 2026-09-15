# Medicine Doser — agent instructions

## Purpose

This is a personal-use interoperability research project for an owner-controlled **DoseControl WiFi** pill dispenser (target: `MC21-WF-MT`). The long-term aim is a local-first controller, but this repository is currently in reconnaissance.

## Read first

1. `README.md`
2. `notes/initial-recon.md`
3. `notes/apk-2.08-findings.md`

## Current verified facts

- Official Android package: `lb.android.dosecontrol`, version `2.08` / code `87`.
- Its APK has been pulled from the owner's Play Store installation into `apk/`.
- The app bundles the Tuya/ThingClips SDK and supports `SmartLife-XXXX` AP-mode Wi-Fi provisioning.
- DoseControl's custom backend is `dcapi.lost-bytes.com` (Strapi-based; full action/endpoint list in `notes/apk-2.08-findings.md`); device interaction uses Tuya schemas/data points and MQTT.
- Upstream JADX `1.5.6` is installed project-locally in `tools/jadx/`; readable output is in `decoded/jadx-2.08/`.
- The key configuration DPs, exact 32-byte alarm encode/decode, and Tuya account/pairing flow are documented in `notes/apk-2.08-findings.md`.
- **Vendor vulnerability found:** the app logs into Tuya's cloud using hardcoded, shared/pooled Tuya account credentials (plaintext, embedded in the public APK) instead of per-customer accounts — meaning anyone who decompiles the app gets working access to cloud accounts that plausibly control other customers' dispensers too. Full detail + actual credential values are local-only in gitignored `notes/local-only-tuya-pool-credentials.md` — never publish or use them; see that file's "Recommended handling."
- Static analysis of the client app (custom API surface, Tuya account/home flow, DP schema, alarm format) is essentially complete. Remaining unknowns (Tuya product ID, live DP schema, any local LAN protocol) need a live pairing capture with the physical dispenser.

## Safety and authorization

- Work only with the user's own phone, dispenser, network, accounts, and extracted app artifacts. This explicitly rules out logging into the shared Tuya pool accounts found via static analysis, even for "research" — those accounts belong to other real customers too.
- Do not scan unrelated hosts, use other accounts, bypass access controls, or publish credentials/tokens/captures.
- Redact device IDs, Wi-Fi credentials, account details, and auth tokens before storing captures or notes — including third-party/vendor credentials discovered via static analysis (route those to a gitignored `notes/local-only-*` file, never a committed one).
- Dispensing is safety-critical: never send experimental dispense commands to a loaded dispenser. Prefer unpowered, empty, or explicitly user-approved test conditions.
- Preserve evidence: record APK version, SHA-256, tool version, timestamp, and action performed.

## Working conventions

- Git is initialized and pushed to the public repo `SusieeTheLinuxUser/dosecontrol-re` on GitHub.
- Keep raw APKs, decompiled output, downloaded tooling, full captures, and `notes/local-only-*` files out of Git history (enforced via `.gitignore`). Commit only hashes, sanitized excerpts, scripts, and notes.
- The repo is public — never commit credentials, tokens, device/account identifiers, or unredacted captures, including ones belonging to the vendor rather than the user.
- Make one controlled change at a time during dynamic testing (for example, change one alarm by one minute), then label the capture with the action and expected result.
- Mark conclusions as **confirmed**, **likely**, or **unknown**. Do not present SDK string evidence as proof of a local protocol.
- Update `notes/`, and **this file and `CLAUDE.md` themselves**, whenever a meaningful discovery, completed step, or plan change happens — the user hops between Claude, ChatGPT/Codex, Qwen, Kimi, and Z.ai across sessions, and these two files are the only continuity mechanism between them.

## Next technical steps

1. ~~Inspect the existing JADX output for the remaining custom API behavior and Tuya account/home flow.~~ Done — see `notes/apk-2.08-findings.md`.
2. Pair the owned dispenser in a controlled network and identify its Tuya product ID and live data-point schema.
3. Capture owner-controlled pairing/configuration operations and compare one change at a time.
4. Design a minimal local prototype only after command semantics and failure modes are understood.
5. Decide how to handle the pooled-Tuya-credential vendor vulnerability (avoid use; consider responsible disclosure to the vendor).
