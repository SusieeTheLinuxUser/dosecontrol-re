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

Confirmed device MAC (redacted here per the device-ID guardrail — kept
locally, matches the `...56:74` fragment seen earlier in the OEM Bluetooth
log). Connects fine unbonded.

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

### Full login handshake — implemented and confirmed working standalone (2026-09-18)

Built a from-scratch Python client (`bleak`, no phone/official app involved)
that completes the entire login handshake against the real device and
reaches the "logged in" state. This is a genuinely independent
implementation, not a replay of captured app traffic.

**Correction to the frame-format table above:** for *app-initiated* request
packets (as opposed to device-initiated pushes like the login announce),
byte 6 is **not** the opcode — it's a length byte for the sub-payload that
follows. The real command tag lives at byte 7. The ack simply OR's `0x80`
into byte 6 (so a request with byte6=2 acks as `0x82`, byte6=8 acks as
`0x88`) and leaves byte 7 (the tag) and the rest of the payload as an echo.
This only became clear by testing live — for device-initiated pushes
(opcode `1`=login, `4`=notify) byte 6 genuinely is the dispatch opcode, per
`a/k.java`.

**Handshake sequence** (`a/f.java`, `a/p.java`, `a/o.java`, `a/q.java`, `a/g.java`):

1. Device pushes login packet on `FF01` (opcode `1`). ACK it on `FF02` (byte4→2, byte6→`0x81`, recompute checksum) — see the ACK format documented above.
2. Immediately send a "device key" request: payload `{0,0,2,0xD0,2,keyLow,keyHigh}`, framed normally. The key is derived from the **device's own BLE MAC address**: strip non-alphanumeric characters, uppercase, take the ASCII bytes, run **CRC16/MODBUS** (init `0xFFFF`, poly `0xA001` reflected) over them, format as a 4-hex-digit uppercase string, decode that back to 2 bytes, send as `[low, high]`. **Confirmed working** — device replies with status `0` (success) on the first real try.
   - This is a weak "authentication" scheme worth flagging as a vendor finding: the device's own MAC is broadcast in cleartext in every BLE advertisement, so anyone in range can compute this "key" trivially. It's obscurity, not security.
3. Immediately send a "phone key" request: same shape, tag `0xD1`, key derived the same way but from the **controlling phone's own network MAC** (the app tries `wlan0`, falls back to `eth0`, then `NetworkInterface` enumeration, then `02:00:00:00:00:00`). Tested with an arbitrary (wrong) MAC — got status `16` (rejected, presumably not the phone this dispenser was originally paired with). **This doesn't matter** — see next point.
4. Per `a/q.java`, the app does **not** gate on D1's real device-side result — it proceeds regardless, based only on the local BLE write completing (a FastBLE callback quirk: `DeviceWriteCallBack.onResponseSuccess` fires with the just-written bytes echoed back, not a genuine device response; real device responses are routed separately through the notify dispatcher in `k.java`). It immediately sends a **date/time sync**: payload `{0,0,8,0xE0,8,yearHi,yearLo,month,day,hour,minute,second,weekdayFrom0}`. **Confirmed working** — device echoed the sent date/time back with the ack pattern (`0x88`), matching the current date exactly.
5. Per `a/g.java`, once the date-sync write locally completes, the app sets its internal connection state to `j=2` — **this is "logged in."** It then fires three more capability-list queries (`{0,0,10}`, `{0,0,11}`, `{0,0,12}`, chained through `a/u.java`→`a/t.java`→`a/s.java`) to populate supported-feature arrays used later — not yet tested live, lower priority than confirming basic alarm/settings read-write now that login works.

**Bonus decode:** the original login packet's payload encodes more than the earlier TLV guess suggested. Per `a/q.java`, byte 15 is the **firmware version** as two nibbles (`(b&0xF0)>>4` + "." + `(b&0x0F)`) — our captured packet's byte 15 was `0x15`, decoding to firmware **"1.5"**. Byte 18 is a **reset flag** (our sample: `0`). The earlier "TLV tags 1-4" reading of bytes 7-18 should be treated as unconfirmed/superseded by this more specific field mapping — worth re-deriving properly rather than trusting the generic TLV guess.

**Also observed:** a recurring unsolicited push on `FF01` every ~4-5 seconds, opcode `4` (`bb110714000004110100fd` pattern, payload tag `0x11`=17, value `0`) — likely a periodic heartbeat/status beacon. Per `a/k.java` this should be ACKed with opcode `0x84`; not yet implemented in the test client, so it just keeps repeating harmlessly.

**Implementation:** `src/pillcontrol_ble.py` (needs `pip install -r src/requirements.txt`) — a clean, from-scratch client implementing the above. Validated twice live against the real device: completes login in ~1.4s (`python3 src/pillcontrol_ble.py --connect <device MAC>` — kept local, not written here, see the device-ID guardrail), and has an offline self-check (`python3 src/pillcontrol_ble.py`, no hardware needed) covering the CRC16 key derivation (against a synthetic MAC, not the real device's), frame format, and ack detection against real captured bytes. Also handles the opcode-4 heartbeat (acks it so the connection doesn't get dropped/retried by the device).

### Complete command set — the "category" byte (2026-09-18)

Byte 6 of an app-initiated request (i.e. `body[2]`, where body is
`[0, 0, category, ...]`) is a **category/handler selector**, not a length.
The device routes on it, then dispatches again on the sub-tag at byte 7.
Confirmed categories:

| Category | Meaning | Source |
| --- | --- | --- |
| `2` | Auth key exchange (sub-tags `0xD0` device key, `0xD1` phone key) | `a/p.java`, `a/o.java` |
| `5` | Batched **GET** — settings and alarm reads | `a/a.java` `a(byte[])`, `a/r.java`, `a/f.java` |
| `6` | Single settings **SET** | `Device.setConfig()` |
| `7` | Battery GET (sub-tags `0x10`, `0x11`) | `a/f.java` `c()` |
| `8` | Events: `0xE0` date/time sync, `0xE2` mute, `0xD3` unbind | `a/q.java`, `Device.mute()`, `Device.unbind()` |
| `10`-`13` | Capability queries (bare — no sub-payload at all) | `a/g.java`→`u`→`t`→`s`→`r` |

**Read vs. write is disambiguated purely by category**, not by packet shape:
a GET and a SET carry the *identical* `[tag, len, value]` sub-block — the
GET just sends a dummy value (usually `0`) under category `5`, while the
SET sends the real value under category `6`.

**Settings tags** (1-byte values, used for both GET and SET):

| Tag | Setting | `ParamBean` field |
| --- | --- | --- |
| `0x50` | Time format (12h/24h) | `time_format` |
| `0x51` | Beep/ring kind | `alarm_ring` |
| `0x52` | Volume | `alarm_voice` |
| `0x53` | Alarm/remind duration | `alarm_clock_duration` |

**Alarm slot blocks** are 6 bytes: `[slot+83, 4, hour, minute, flags, daymask]`
(so slot 1 → tag `0x54`, slot 8 → `0x5B`; tags `0x50`-`0x53` are reserved
for the settings above, which is why slots start at 1 rather than 0).
`flags` bit0 = enabled, bit1 = repeat. `daymask` bits 0-6 = Sunday..Saturday
(`a/y.java` decodes it to a comma-separated day-code string).

### The full post-login read sequence

Traced end to end through `a/g.java` → `u.java` → `t.java` → `s.java` →
`r.java` → `d.java` → `e.java` → `f.c()`:

1. Four bare capability queries: `{0,0,10}`, `{0,0,11}`, `{0,0,12}`, `{0,0,13}`. The responses populate `f.e`/`f.f` — byte arrays listing **which tags the device supports**. `r.java` then checks membership for tags `80`-`83` to decide which settings to ask for.
2. **Settings GET** (category `5`), one batched request containing all supported settings tags with dummy zero values: `{0,0,5, 0x50,1,0, 0x51,1,0, 0x52,1,0, 0x53,1,0}`. Response parsed in `a/d.java` at fixed absolute packet offsets: **byte 9 = time_format, 12 = alarm_ring, 15 = alarm_voice, 18 = alarm_clock_duration** (3-byte stride = one `[tag,len,value]` triplet each).
3. **Alarm GET**, walked two slots at a time (category `5`, two alarm blocks per request, dummy values). Response parsed in `a/e.java`: slot *i* at **bytes 9,10,11,12** (hour, minute, flags, daymask) and slot *i+1* at **bytes 15,16,17,18**. `hour == 0xFF` means the slot is empty (status 0); otherwise flags bit0 gives active (1) vs disabled (2). The chain walks pairs 1→3→5→7→9 (the last one overruns the real 8 slots and returns garbage for slot 10 — the official app does this too, so it's replicated rather than "fixed"; the client discards rows > 8).
4. **Battery GET** (category `7`, tags `0x10`/`0x11`). Response parsed by the inner class `a` in `a/f.java`: **byte 8 = percent, byte 9 = state**.

This means every read the official app performs is now fully mapped, and
all the write commands are mapped too (categories 6 and 8 above) — though
no write beyond the login/date-sync has been attempted.

### LIVE CONFIRMED (2026-09-19) — full read chain works end to end

`src/pillcontrol_ble.py` ran the entire chain (login → capability queries →
settings → all 8 alarm slots → battery) against the real device twice in a
row, both clean exits, both runs producing identical data:

```
settings: {'time_format': 0, 'alarm_ring': 1, 'alarm_voice': 2, 'alarm_duration': 30}
alarms: all 8 slots — status=2, hour=24, minute=60, repeat=False, days=[]
battery: {'percent': 1, 'state': 0}
```

**Correction to the design above:** the "empty slot" sentinel is **not**
`hour == 0xFF`. A genuinely never-configured slot on the real device reads
back `hour=24, minute=60, flags=0` — i.e. the literal `"24:60"` string
`Pillbox.removeAlarm()` writes when clearing a slot (`24` is out-of-range
for a real hour, hence the sentinel). With `flags=0` that decodes to
`status=2` ("disabled") under the source's own logic, not `status=0`
("empty") — the `hour==0xFF` case may be a separate, rarer sentinel never
actually produced by this firmware, or only reachable another way. Since
all 8 slots came back this same way on a factory-fresh, never-configured
unit, this is a confident read, not a guess.

**Battery is unconfirmed in meaning**, not in mechanism: `percent=1` is
suspiciously low for a literal 0-100 percentage on a device that (per the
finding below) needs external power just to keep its radio on — plausibly
it's a coarse level code (e.g. 0-3, like the volume field) rather than a
true percentage, or the battery genuinely is that depleted. Cross-check
against the official app's own battery UI next time it's convenient.

A bug was found and fixed en route: `is_ack_for()` originally checked only
the sub-tag byte (byte 7), not the category byte (byte 6). The capability-12
response's payload happens to start with `0xD0` (it's listing supported
event tags: D0,D1,D2,D3,E0,E1,E2), which falsely matched the "D0 key ack"
check and made the client loop back into the login sequence forever. Fixed
by requiring both bytes to match; the corrected function signature is
`is_ack_for(pkt, category, tag)`.

### Live-testing gotcha: the device stops advertising unless externally powered

After a stretch of testing, the dispenser stopped appearing in BLE scans
entirely (from the Linux box's own adapter, which had successfully
connected to it earlier the same day, so it is not a range or address
problem). Pressing its physical buttons (`+`, `-`, `alarms`, `clock`) did
not bring it back. The phone also showed it as disconnected, so nothing was
holding the link. **A 3-minute continuous retry loop never saw a single
advertisement**, so this is not a "short advertising window we kept
missing" problem — the radio was genuinely off/asleep. **The next session
found it advertising again with no explicit action recorded** — most
plausibly it was plugged into power in between, which would confirm the
"external power keeps the radio on" hypothesis from last session (its Tuya
sibling product exposes an explicit "on external power" data point, so
power-dependent BLE behaviour is plausible for this product line). Treat as
likely-but-not-quite-confirmed until someone explicitly watches
power-plug-in bring it back. Bottom line: **if the device isn't scanning,
plug it in before troubleshooting anything else.**

How the official app reconnects (relevant, from `PillboxScanner.java`): it
**never rescans** for a known device. It stores `{name, mac}` JSON in
SharedPreferences under `LB_PILLBOX_DEVICES`, rebuilds the handle with
`getRemoteDevice(mac)`, and calls `BleManager.connect()` directly — Android
then holds that connection request pending in the controller and latches on
the instant the peripheral advertises. Scanning is only used when adding a
*new* device (filtered on service `0xFF00` plus a name containing `"LN"`).
`PillControlClient.wait_for_device()` approximates this with a retry loop,
which is the right shape — it just can't help when the device is emitting
nothing at all.

Untested hypotheses for next session, in order of cheapness:
1. **External power** — it may only keep the BLE radio awake when plugged in (its Tuya sibling exposes an explicit "on external power" data point, so power-dependent behaviour is plausible for this product line).
2. **Power-

Scanning tip: `BleakClient(address)` alone fails with
`BleakDeviceNotFoundError` if BlueZ has never discovered the device in the
current session — run a `BleakScanner.discover()` first (or use
`BleakScanner.find_device_by_address`) so BlueZ has it cached.

Also: run the client with `python3 -u`. Without unbuffered output, a run
killed by `timeout` loses all its prints (stdout is block-buffered when
piped), which looks exactly like "the script did nothing."

## Open questions

- ~~Live confirmation of the read chain above~~ — **done, see "LIVE CONFIRMED" above.**
- What battery `percent`/`state` actually mean (coarse level code vs. true percentage) — `percent=1` read live is suspiciously low to be a literal 0-100 value.
- Whether external power really is what wakes the BLE radio (plausible from observation, not yet deliberately tested by watching a plug-in event).
- Purpose of `kang_device_id`, `uid`, `access_token` fields on `ClockBean` — whether these are BLE pairing/bonding-level auth or just app bookkeeping.
- Pill-record (`TakeDrugBean`) byte layout — the dose-history records, not yet traced.
- What the capability-query responses (categories 10-13) actually contain beyond the supported-tag list (category 11's response shape, in particular, wasn't decoded).
- Second custom service `00010203-0405-0607-0809-0a0b0c0d1912` — never investigated.
- No settings/alarm **write** has been attempted yet — only login/date-sync writes are live-confirmed. The write command shapes are mapped from source (categories 6 and 8) but unverified against the real device.
