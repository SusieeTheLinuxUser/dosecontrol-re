# Medicine Doser — continuation brief

Read `AGENTS.md`, `README.md`, and the files in `notes/` before acting. This project is early-stage personal-use research for an owner-controlled pill dispenser; it is not yet a working controller.

## CORRECTION (2026-09-18) — read this first

The user's actual physical device is **Bluetooth-based**, pairing with app
`lb.android.pillcontrol`, NOT the Tuya/WiFi `lb.android.dosecontrol` app
analyzed below. The vendor makes two device lines. See
`notes/pillcontrol-1.16-findings.md` for the correct device's findings —
that's now the active line of work. Everything under "State as of
2026-09-15" below is still valid research, just for a different product the
user doesn't have. Don't delete it (may be useful later / for others), but
don't treat it as this device's protocol.

## MAJOR MILESTONE (2026-09-19) — full protocol reversed AND live-confirmed end to end

Reverse-engineered the **entire** `pillcontrol` BLE wire protocol from its
obfuscated packet layer and built a standalone Python client
(`src/pillcontrol_ble.py`) — no phone or official app involved. **Fully
working, confirmed live, reproducibly (2 clean runs, identical data):**

- **Login handshake.** Frame format, checksum, CRC16/MODBUS MAC-derived auth
  keys, date-sync. Reaches "logged in" in ~1.4s.
- **Full read chain.** Capability queries → settings → all 8 alarm slots →
  battery. Real data read off the actual device:
  `settings={'time_format':0,'alarm_ring':1,'alarm_voice':2,'alarm_duration':30}`,
  all 8 alarms empty (`hour=24,minute=60` — that's the real "unconfigured"
  sentinel, not `0xFF` as originally guessed from source alone),
  `battery={'percent':1,'state':0}` (meaning of these two battery values
  still unconfirmed — see notes).
- **All write commands mapped too** (category `6` settings SET, category `8`
  events) but **not yet tested live** — only login/date-sync writes are
  confirmed; a settings/alarm write is the next real unknown.

Full protocol table (categories, tags, offsets, the whole read sequence) is
in `notes/pillcontrol-1.16-findings.md`, under "LIVE CONFIRMED" — that
file is the source of truth, read it before touching the BLE code.

**Hardware quirk, resolved:** the dispenser stops advertising after a
testing stretch and needs external power to keep its BLE radio on (button
presses don't wake it; a `wait_for_device()` retry loop in the client
mimics the official app's reconnect-by-MAC behaviour, but can't help if the
radio is genuinely off). If the device isn't showing up in a scan,
**plug it in first** before troubleshooting anything else.

**A dispatch bug was found and fixed** during the live run: `is_ack_for()`
originally matched on the sub-tag byte alone, which could coincidentally
match unrelated response data and made the client loop the login sequence
forever. Fixed by also checking the category byte. Worth knowing if similar
symmetric-looking bugs show up when adding write support.

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

Reads are fully done and live-confirmed (login, settings, all alarms, battery). The next real unknown is a **settings write** — e.g. toggle time format or set one alarm slot, using the category-`6`/`8` write shapes already mapped from source in `notes/pillcontrol-1.16-findings.md` but never tested against real hardware. Device is still unloaded (no medication) so this is within the safety guardrails, but treat writes as a new category of risk vs. reads: change one thing at a time, verify by reading it back afterward, and stay away from anything alarm-schedule-adjacent until a simple write (like time format) is proven safe and reversible. Remember the device needs **external power** to keep its BLE radio on — plug it in before doing anything. `src/dosecontrol.py` (Tuya-flavored scaffold) remains stale/irrelevant to this device — don't extend it.
