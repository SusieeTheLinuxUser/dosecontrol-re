# Medicine Doser — agent instructions

## Purpose

This is a personal-use interoperability research project for an owner-controlled pill dispenser. The long-term aim is a local-first controller, but this repository is currently in reconnaissance.

**Correction (2026-09-18):** the user's actual physical device is Bluetooth-based (`lb.android.pillcontrol` app), not the Tuya/WiFi `MC21-WF-MT`/`lb.android.dosecontrol` device analyzed first — the vendor makes two device lines and the wrong one was initially assumed. `notes/apk-2.08-findings.md` is still-valid research for that other (unowned) product; `notes/pillcontrol-1.16-findings.md` is the active line of work.

## Read first

1. `README.md`
2. `notes/initial-recon.md`
3. `notes/pillcontrol-1.16-findings.md` — **the actual device**
4. `notes/apk-2.08-findings.md` — a different, unowned Tuya-based device; kept for reference only

## Current verified facts

- **Actual device (`pillcontrol`, confirmed 2026-09-18):** Bluetooth-only, no cloud dependency for control. App `lb.android.pillcontrol` v1.16, BLE service UUID `0000FF00-0000-1000-8000-00805F9B34FB`, device advertises with `"LN"` in its BLE name. Uses FastBLE (`com.clj.fastble`) + a vendor protocol lib (`com.xm.xjh.blelibrary`) whose app-facing classes are readable but whose packet-encoding layer is ProGuard-obfuscated. Data model (alarms/settings/battery/records) documented in `notes/pillcontrol-1.16-findings.md`. Next step is a Bluetooth HCI snoop log capture (no root needed) — see that file.
- Everything below this point is about the *other*, unowned Tuya device (`lb.android.dosecontrol`) — kept for reference, not active work.
- Official Android package: `lb.android.dosecontrol`, version `2.08` / code `87`.
- Its APK has been pulled from the owner's Play Store installation into `apk/`.
- The app bundles the Tuya/ThingClips SDK and supports `SmartLife-XXXX` AP-mode Wi-Fi provisioning.
- DoseControl's custom backend is `dcapi.lost-bytes.com` (Strapi-based; full action/endpoint list in `notes/apk-2.08-findings.md`); device interaction uses Tuya schemas/data points and MQTT.
- Upstream JADX `1.5.6` is installed project-locally in `tools/jadx/`; readable output is in `decoded/jadx-2.08/`.
- The key configuration DPs, exact 32-byte alarm encode/decode, and Tuya account/pairing flow are documented in `notes/apk-2.08-findings.md`.
- **Vendor vulnerability found:** the app logs into Tuya's cloud using hardcoded, shared/pooled Tuya account credentials (plaintext, embedded in the public APK) instead of per-customer accounts — meaning anyone who decompiles the app gets working access to cloud accounts that plausibly control other customers' dispensers too. Full detail + actual credential values are local-only in gitignored `notes/local-only-tuya-pool-credentials.md` — never publish or use them; see that file's "Recommended handling."
- Static analysis of the client app (custom API surface, Tuya account/home flow, every settings DP write flow, alarm format) is essentially complete. Confirmed negative finding: no app-side "dispense now" command exists anywhere — dispensing is driven entirely by the device's own alarm schedule.
- **Blocked on hardware as of 2026-09-15: the user does not have the physical dispenser yet.** Remaining unknowns (Tuya product ID, live DP schema, any local LAN protocol) all need a live pairing capture. Don't keep re-reading app source hunting for protocol findings — remaining unread files are UI/analytics/billing plumbing, unlikely to add anything.
- No `networkSecurityConfig` in the manifest; default Android 24+ (`targetSdkVersion=35`) behavior means a future capture session needs root (system CA install) or a Frida-based approach — a plain user-installed proxy CA won't be trusted by the app. Detail in `notes/apk-2.08-findings.md` "Network/traffic-capture planning notes".

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

## Next technical steps (active device: `pillcontrol`, Bluetooth)

1. ~~Decompile and statically analyze `pillcontrol` 1.16.~~ Done — see `notes/pillcontrol-1.16-findings.md`.
2. Capture a Bluetooth HCI snoop log while using the real app (Developer options toggle, no root) to get exact GATT characteristic UUIDs and full packet formats — the obfuscated packet-encoding layer isn't worth hand-reversing when a live capture gives ground truth directly.
3. Once the GATT format is known: write a new BLE client (a fresh module — `src/dosecontrol.py` is Tuya-flavored and stale for this device), one capability at a time (read alarms/settings first, writes only after read is solid).
4. Change one thing at a time during any live capture (e.g. one alarm by one minute), labeling each capture with the action taken.
5. Design a minimal local prototype only after command semantics and failure modes are understood from real captures.

## Parked (unowned Tuya device — `dosecontrol`, not this project's active hardware)

1. Decide how to handle the pooled-Tuya-credential vendor vulnerability found during that research (avoid use; consider responsible disclosure to the vendor) — still worth doing regardless of which device is active, since it's a live vendor security issue.
2. Everything else about the Tuya device (product ID, DP capture, cert-trust setup) stays parked unless the user acquires that device too.
