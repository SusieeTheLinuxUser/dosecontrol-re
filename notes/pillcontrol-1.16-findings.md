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

### Live capture (2026-09-18, direct adb+nRF Connect control)

Confirmed device MAC: `[REDACTED-DEVICE-MAC]` (matches the `...56:74` fragment
seen earlier in the OEM Bluetooth log). Connects fine unbonded.

`FF01` notify value captured (present as soon as notifications were
enabled, no explicit write needed — likely pushed automatically on
connect/subscribe as part of the base-params handshake):

```
BB-11-10-0D-00-00-01-01-01-01-02-01-01-03-01-15-04-01-00-0F
```

20 bytes total. Working structure hypothesis (unconfirmed, needs more
samples to verify): `BB` = start/magic byte, `11` = message type/opcode,
`10` = sub-type or count, `0D` (=13) = payload length — and 13 bytes
follow exactly (indices 4-16), leaving a plausible 3-byte
trailer/checksum (`01-00-0F`). Payload bytes not yet mapped to specific
`ParamBean` fields (time_format, alarm_voice, alarm_ring, etc.) — need a
second sample with a known, deliberately-changed setting to diff against.

`FF21` (the second notify channel) stayed empty after subscribing — no
spontaneous push. Likely needs an explicit write on its paired write
channel (`FF22`) to trigger a response, unlike `FF01`/`FF02` which seem to
auto-announce on connect.

### Full wire protocol — decoded from the obfuscated `a.*` package (2026-09-18)

The packet-encoding layer flagged as "obfuscated, not worth hand-reversing"
earlier turned out to be small (27 tiny classes, ~230 lines total for the
core ones) and trivial to read once you know what to grep for (the `0xBB`
magic byte led straight to it). Full frame format, confirmed against the
real captured packet:

```
byte 0      0xBB (-69)         magic/start byte, constant
byte 1      0x11 (17)          constant (from a.a(byte[], boolean, byte))
byte 2      len(body)+1        body = bytes[4..N-2] (i.e. response-type+status+opcode+payload, excludes header and checksum)
byte 3      sequence number    rolling counter 0-255 for app-initiated requests (a.f4a, static, auto-increments); echoed back unchanged when acking a device-initiated packet
byte 4      response-type      0 = request, 2 = ack/response (set explicitly when building an ack)
byte 5      status             0 = success (checked via x.b(bArr) == 0)
byte 6      opcode             dispatch key (see table below); acks reply with (0x80 | opcode)
bytes 7..N-2  payload          opcode-specific, appears TLV-encoded (tag,len,value) in the one sample decoded so far
byte N-1    checksum           sum(bytes[0..N-2]) mod 256 (a/b.java) — confirmed exact match against the real captured packet
```

Checksum verified by hand against the real `FF01` packet
(`BB-11-10-0D-00-00-01-01-01-01-02-01-01-03-01-15-04-01-00-0F`): sum of
bytes 0-18 = 271, `271 mod 256 = 0x0F` = the actual trailing byte. Confirmed.

Known opcodes (from `a/k.java`'s dispatch, the notify-callback handler):

| Opcode | Meaning | Ack sent back |
| --- | --- | --- |
| `1` | Device login/handshake request | `0x81` |
| `3` | (unconfirmed, only acked if `x.b(bArr)==0`) | `0x83` |
| `4` | "Device Notify" (logged distinctly) | `0x84` |
| `-126` (0x82) | no-op / skips dispatch entirely | — |
| `-123..-120`, `-118..-115` | logged only, no explicit handling shown | — |

Special case: if byte 7 == `0xD1` and byte 5 == `0x10`, the app tears down
the whole BLE connection (`BleManager.getInstance().destroy()`) — avoid
accidentally constructing a packet matching that shape.

Our one real captured packet is the device's **login request** (opcode
`1`). Its payload (bytes 7-18, 12 bytes) cleanly parses as four 3-byte TLV
triplets (`tag, len=1, value`): `(1,1)`, `(2,1)`, `(3,0x15=21)`, `(4,0)`.
Tag 3's value of 21 is a strong candidate for **battery percentage**. This
matches the TLV-builder helpers also found in `a/a.java`:
`c(b)`→`{0x50,1,b}`, `a(b)`→`{0x51,1,b}`, `d(b)`→`{0x52,1,b}`,
`b(b)`→`{0x53,1,b}` — tags 0x50-0x53, not 1-4, so these specific helpers
aren't what built this particular login payload, but confirm the general
TLV convention used elsewhere in the protocol.

Computed ACK for the captured login packet (per `k.java`: copy the packet,
set byte 4 = `2`, byte 6 = `0x81`, recompute the checksum):

```
BB-11-10-0D-02-00-81-01-01-01-02-01-01-03-01-15-04-01-00-91
```

**Not yet sent to the device** — this is a computed-from-source value,
ready to test. Sending it via `FF02` is the next concrete experiment: if
the protocol understanding is right, it should advance the connection's
internal login state and likely provoke a follow-up packet (opcode `3` or
`4`) on `FF01`.

The alarm-clock-set command builder (`a/a.java`,
`a(int i, int i2, int i3, boolean z, boolean z2, int[] iArr)`) is also now
readable — 6-byte structure: `[0]=i+83` (slot-based opcode, so alarm slot 0
maps to opcode `0x53`=83, matching the `b(byte)` TLV tag above — worth
re-checking whether slot opcodes and the 0x50-0x53 TLV tags are the same
namespace), `[1]=4` (fixed), `[2]=i2`, `[3]=i3`, `[4]`=flag byte (`z`→bit0,
`z2`→bit1 via XOR), `[5]`=day-of-week bitmask (one bit per day, built from
the `int[7]` array via `1 << index`).

Second custom service (`00010203-...`) still not investigated — lower
priority than finishing the FF00 login/settings/alarm flow.

## Open questions

- Exact GATT characteristic UUIDs (read/write/notify) under service `0000FF00-...`.
- Full packet header/CRC format (only bytes 9-12 of the alarm-ack packet are known).
- Purpose of `kang_device_id`, `uid`, `access_token` fields on `ClockBean` — whether these are BLE pairing/bonding-level auth or just app bookkeeping.
- Battery and pill-record (`TakeDrugBean`) byte layouts — not yet read in detail.
