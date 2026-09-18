# PillControl app 1.16 — findings (this is the actual device)

Date: 2026-09-18

## Correction to earlier research

The physical dispenser the user owns pairs with a **different app** than the
one analyzed in `apk-2.08-findings.md`. The vendor (lost-bytes) makes two
apps for two different device lines:

- `lb.android.dosecontrol` — Tuya/WiFi-based (previously analyzed, not this device).
- `lb.android.pillcontrol` — **Bluetooth-based, this is the actual device.**

## Provenance

- Package: `lb.android.pillcontrol`
- Version: `1.16` (`versionCode` 17)
- Pulled directly from the paired phone (adb), not the Play Store, since it was already installed there:
  - `apk/pillcontrol-1.16-base.apk` — SHA-256 `2be423362d9ea97ae31db130b2ced5172e190f6e38dcc3350ed72cbd3107297f`
  - `apk/pillcontrol-1.16-config-en.apk` — SHA-256 `24469f8b040685fe33c98f92b59a68d2cdcca7af21b3b0afc5a25094e70ae584`
- Decompiled with the same JADX 1.5.6 into `decoded/jadx-pillcontrol-1.16/`.

## Confirmed architecture — good news for local-first

**No Tuya, no cloud device-control dependency at all.** The device is
controlled entirely over local Bluetooth Low Energy:

- BLE library: `com.clj.fastble` (FastBLE — a well-known open-source Android BLE library) for connection management.
- Protocol library: `com.xm.xjh.blelibrary` (vendor-specific, bundled in the APK, app-facing classes are **not obfuscated** — only the deepest packet-encoding layer is).
- BLE service UUID: `0000FF00-0000-1000-8000-00805F9B34FB`.
- The app scans for BLE devices whose advertised name contains `"LN"` (`PillBox.kt initPillBoxScan`) — that's the identifying substring for this dispenser over BLE.
- App-level flow: `lb.android.pillcontrol.BtConnectionService` (a foreground `Service`) owns a `lb.android.pillboxlib.Pillbox` object, which wraps `com.xm.xjh.blelibrary.opera.PillBox` (connect/scan) and `PillBoxControlManager` (settings writes).

There's a small legacy backend used **only for email/SMS notifications**
(pill taken/missed/low battery), not for device control:
`https://dev.lost-bytes.com/sandbox/dosecontrol_api/api.php` and
`https://dcapi2.lost-bytes.com/bt/mynotify`. Irrelevant to controlling the dispenser itself.

## Confirmed data model (`lb.android.pillboxlib.data.*`, wraps `com.xm.xjh.blelibrary.bean.*`)

Alarms (`AlarmData` / `ClockBean`):
- `row` — alarm slot number.
- `status` — `1` = active, `2` = disabled.
- `alarm_time` — plain `"HH:MM"` string (not a byte blob).
- `effect_time` — comma-separated day codes, **Sunday=0** through **Saturday=6** (different from the Tuya app's Monday=0 — don't reuse that mapping here).
- `repeat` — int flag.
- Also carries `bluetoothMac`, `kang_device_id`, `uid`, `access_token` fields (purpose not yet confirmed — possibly per-device pairing/auth values transmitted over BLE).

Settings (`ParamData` / `ParamBean`): time format, alarm volume (`0`=mute,`1`=low,`2`=high — only 3 levels here, not 4 like the Tuya device), ring/beep kind. Battery (`BatteryData` / `Battery`), and pill-take records (`PillRecordBean` / `TakeDrugBean`) also exist as separate beans, not yet read in detail.

One partial byte-level packet fragment recovered from `PillBoxControlManager.addAlarmClock`'s response parsing (the ack packet for a "set alarm" write):
- byte `9` = hour, byte `10` = minute (`255` in both means "unset")
- byte `11`: bit `0` = active/disabled status, bit `1` = repeat flag
- byte `12` = effect_time (day mask, single byte)

This is only bytes 9-12 of an unknown-length packet — header/CRC bytes before byte 9 are not yet known.

## What's still obfuscated

The actual BLE packet construction (turning `setClock(...)`, `setVolume(...)` etc. into raw bytes written to a GATT characteristic) lives in a ProGuard-obfuscated package (single-letter classes `a.f`, `a.i`, `a.j`, `a.v`, `a.w`, `a.y`, `a.a0`). Not worth hand-deobfuscating byte-by-byte when a live BLE sniff will show the same thing far faster and with ground truth (see next steps).

## Live GATT exploration (2026-09-18, via nRF Connect for Mobile)

**HCI snoop log is a dead end on this device's ColorOS build** — enabling the
Developer options toggle produces no `btsnoop_hci.log` anywhere (checked a
full `adb bugreport`, only OnePlus/Oppo's own text diagnostic log exists,
which confirms connections/service-discovery but carries no raw ATT payload
bytes). Don't retry that path on this phone.

Direct GATT browsing (nRF Connect for Mobile, connected — not bonded —
directly to the device, official app force-stopped first so only one client
holds the connection) confirmed the exact characteristic map under service
`0000ff00-0000-1000-8000-00805f9b34fb` (handles `0x0017`-`0x0021`, matching
the OEM log's service-discovery record):

| Characteristic | Properties | Role |
| --- | --- | --- |
| `0xFF01` | Notify | responses/events for the FF02 write channel |
| `0xFF02` | Write, Write No Response | primary command channel |
| `0xFF21` | Notify | responses/events for the FF22 write channel |
| `0xFF22` | Write, Write No Response | second command channel (possibly alarms vs. settings/battery — unconfirmed which is which) |

Two independent write/notify pairs, not one multiplexed channel. This lines
up with the source having two listener interfaces
(`PillBoxParamsCallbackListener`: base params/battery/clock/drug records;
`PillBoxNotifyCallbackListener`: clock/drug/ringtone/time-format/volume
push notifications) — plausibly one pair per interface, but not yet confirmed
which UUID pair maps to which.

Also present: a **standard Bluetooth SIG Battery Service (`0x180F`)** —
battery level is likely readable the standard way (characteristic `0x2A19`),
no custom protocol needed for that one value.

There's also a second custom service, UUID `00010203-0405-0607-0809-0a0b0c0d1912`
(sequential-byte pattern, looks like an SDK template/example UUID) —
purpose not yet investigated.

### Next: correlate writes/notifies with real behavior

With FF01/FF21 notifications enabled and the official app disconnected, the
plan is to trigger known operations (e.g. `PillBoxControlManager.setPillBoxVoiceMaxAndMin`
for volume, `setPillBoxTimeFormat`, `addAlarmClock`) — but since we can't
observe the *official app's* raw bytes (no snoop), the practical approach is
either (a) do one write at a time ourselves via nRF Connect and see what
changes on the device/in the notify payload, informed by the known response
byte layout (bytes 9=hour, 10=minute, 11=status/repeat flags, 12=effect_time,
from `PillBoxControlManager.addAlarmClock`'s ack parsing), or (b) revisit a
Frida/root-based capture later if manual probing stalls. Device is unloaded
(still not out of retail plastic as of first pairing), so settings-level
experiments are within the project's safety guardrails; avoid anything that
looks like it could be a dispense-adjacent command until the protocol is
better understood.

## Open questions

- Exact GATT characteristic UUIDs (read/write/notify) under service `0000FF00-...`.
- Full packet header/CRC format (only bytes 9-12 of the alarm-ack packet are known).
- Purpose of `kang_device_id`, `uid`, `access_token` fields on `ClockBean` — whether these are BLE pairing/bonding-level auth or just app bookkeeping.
- Battery and pill-record (`TakeDrugBean`) byte layouts — not yet read in detail.
