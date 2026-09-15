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
- DoseControl's custom backend is `dcapi.lost-bytes.com`; device interaction appears to use Tuya schemas/data points and MQTT.
- Upstream JADX `1.5.6` is installed project-locally in `tools/jadx/`; readable output is in `decoded/jadx-2.08/`.
- The key configuration DPs and alarm format are documented in `notes/apk-2.08-findings.md`.

## Safety and authorization

- Work only with the user's own phone, dispenser, network, accounts, and extracted app artifacts.
- Do not scan unrelated hosts, use other accounts, bypass access controls, or publish credentials/tokens/captures.
- Redact device IDs, Wi-Fi credentials, account details, and auth tokens before storing captures or notes.
- Dispensing is safety-critical: never send experimental dispense commands to a loaded dispenser. Prefer unpowered, empty, or explicitly user-approved test conditions.
- Preserve evidence: record APK version, SHA-256, tool version, timestamp, and action performed.

## Working conventions

- Git is initialized and pushed to the public repo `SusieeTheLinuxUser/dosecontrol-re` on GitHub.
- Keep raw APKs, decompiled output, downloaded tooling, and full captures out of Git history (enforced via `.gitignore`). Commit only hashes, sanitized excerpts, scripts, and notes.
- The repo is public — never commit credentials, tokens, device/account identifiers, or unredacted captures.
- Make one controlled change at a time during dynamic testing (for example, change one alarm by one minute), then label the capture with the action and expected result.
- Mark conclusions as **confirmed**, **likely**, or **unknown**. Do not present SDK string evidence as proof of a local protocol.
- Update the relevant `notes/` file whenever a meaningful discovery is made.

## Next technical steps

1. Inspect the existing JADX output for the remaining custom API behavior and Tuya account/home flow.
2. Pair the owned dispenser in a controlled network and identify its Tuya product ID and live data-point schema.
3. Capture owner-controlled pairing/configuration operations and compare one change at a time.
4. Design a minimal local prototype only after command semantics and failure modes are understood.
