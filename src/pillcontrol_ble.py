"""PillControl BLE client (the actual owned device — see notes/pillcontrol-1.16-findings.md).

Confirmed working standalone against the real dispenser (2026-09-19,
reproduced across 2 clean runs): completes the full login handshake, then
reads settings, all 8 alarm slots, and battery — independent of the
official app or phone. No write beyond login/date-sync has been tried live
yet; that's the next real unknown (see notes/).

Device quirk: needs external power to keep its BLE radio advertising.

Requires: pip install -r requirements.txt

Protocol summary (full detail in notes/):
  - Service 0000ff00-..., write char FF02, notify char FF01.
  - Frame: [0xBB, 0x11, len(body)+1, seq, ...body..., checksum]
    checksum = sum(all preceding bytes) mod 256.
  - body for an app-initiated request is [0, 0, category, ...category-specific...].
    Categories seen: 2=auth key exchange, 5=batched settings/alarm GET,
    6=single settings SET, 7=battery GET, 8=event (mute/unbind/date-sync),
    10-13=capability queries (bare, no sub-payload).
  - The device acks a request by echoing it back with byte 6 (the category
    byte) OR'd with 0x80 — the rest of the payload is either echoed as-is
    (for a SET) or filled in with the requested data (for a GET).
  - Device pushes a login packet (tag 1) on connect; ack it, then send a
    "device key" (tag 0xD0, category 2) derived from CRC16/MODBUS of the
    device's own MAC, then a "phone key" (tag 0xD1, category 2, same
    derivation from the phone's MAC — the device may reject an
    unrecognized one, but the app proceeds regardless), then a date/time
    sync (tag 0xE0, category 8). The device then considers the session
    logged in.
  - After login: capability queries (bare categories 10,11,12,13) reveal
    which settings tags (0x50-0x53) are supported, then a batched GET
    (category 5) reads them, then a chained per-pair GET (category 5,
    reusing the alarm-slot-write block shape with dummy values) walks all
    8 alarm slots two at a time, then a battery query (category 7, tags
    0x10/0x11) finishes the sequence.
"""

from __future__ import annotations

import asyncio
import datetime
import re
import time
from dataclasses import dataclass, field

from bleak import BleakClient

FF01 = "0000ff01-0000-1000-8000-00805f9b34fb"
FF02 = "0000ff02-0000-1000-8000-00805f9b34fb"
FF21 = "0000ff21-0000-1000-8000-00805f9b34fb"


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            lsb = crc & 1
            crc >>= 1
            if lsb:
                crc ^= 0xA001
    return crc


def key_bytes_for(identifier: str) -> bytes:
    """Device/phone auth key: CRC16/MODBUS of the cleaned, uppercased MAC's ASCII bytes."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", identifier).upper()
    crc_hex = format(crc16_modbus(cleaned.encode("ascii")), "04X")
    return bytes.fromhex(crc_hex)


def checksum(pkt: bytearray) -> int:
    return sum(pkt[:-1]) % 256


class FrameCounter:
    """Rolling 0-255 sequence counter for app-initiated requests."""

    def __init__(self) -> None:
        self._seq = 0

    def frame(self, body: bytes) -> bytes:
        if self._seq == 255:
            self._seq = 0
        seq, self._seq = self._seq, self._seq + 1
        pkt = bytearray([0xBB, 0x11, (len(body) + 1) & 0xFF, seq]) + body + b"\x00"
        pkt[-1] = checksum(pkt)
        return bytes(pkt)


def build_ack(pkt: bytes) -> bytes:
    """Ack for a device-initiated push (e.g. the login packet, tag/opcode at byte 6)."""
    ack = bytearray(pkt)
    ack[4] = 2
    ack[6] = 0x80 | pkt[6]
    ack[-1] = checksum(ack)
    return bytes(ack)


def is_ack_for(pkt: bytes, category: int, tag: int) -> bool:
    """True if pkt is the device's ack for an app-initiated request under this
    category carrying this sub-tag (D0/D1/E0-style: byte 6 = 0x80|category,
    byte 7 = the real tag). Category must be checked too -- byte 7 alone can
    coincidentally match unrelated data (e.g. a capability-list response
    whose payload happens to start with 0xD0)."""
    return len(pkt) > 7 and pkt[0] == 0xBB and pkt[6] == (0x80 | category) and pkt[7] == tag


def is_category_ack(pkt: bytes, category: int) -> bool:
    """True if pkt acks a request whose category (byte 6, before the 0x80 ack bit) matches."""
    return len(pkt) > 6 and pkt[0] == 0xBB and pkt[6] == (0x80 | category)


def alarm_slot_block(slot: int, hour: int = 0, minute: int = 0, enabled: bool = False,
                      repeat: bool = False, days: range = range(7)) -> bytes:
    """6-byte alarm slot block: [tag, 4, hour, minute, flags, daymask]. Matches a/a.java."""
    b = bytearray(6)
    b[0] = (slot + 83) & 0xFF
    b[1] = 4
    b[2] = hour & 0xFF
    b[3] = minute & 0xFF
    flags = 1 if enabled else 0
    if repeat:
        flags ^= 2
    b[4] = flags
    daymask = 0
    for i in days:
        daymask ^= 1 << i
    b[5] = daymask & 0xFF
    return bytes(b)


def decode_daymask(b: int) -> list[int]:
    return [i for i in range(7) if b & (1 << i)]


@dataclass
class AlarmSlot:
    row: int
    status: int  # 0=empty, 1=active, 2=disabled
    hour: int
    minute: int
    repeat: bool
    days: list[int] = field(default_factory=list)


class PillControlClient:
    def __init__(self, address: str):
        self.address = address
        self.client: BleakClient | None = None
        self.counter = FrameCounter()
        self.logged_in = asyncio.Event()
        self.reads_done = asyncio.Event()
        self.settings: dict[str, int] = {}
        self.alarms: dict[int, AlarmSlot] = {}
        self.battery: dict[str, int] = {}
        self._cap_stage = 0
        self._pending_alarm_base = 0

    async def _send(self, body: bytes) -> None:
        pkt = self.counter.frame(body)
        print(f"[{time.time():.3f}] -> {pkt.hex()}")
        await self.client.write_gatt_char(FF02, pkt, response=True)

    async def _on_ff01(self, _, data: bytearray) -> None:
        pkt = bytes(data)
        print(f"[{time.time():.3f}] FF01 <- {pkt.hex()}")
        if pkt[0] != 0xBB:
            return
        opcode = pkt[6]

        if opcode == 1:  # device login push
            await self.client.write_gatt_char(FF02, build_ack(pkt), response=True)
            device_key = key_bytes_for(self.address)
            await self._send(bytes([0, 0, 2, 0xD0, 2, device_key[1], device_key[0]]))
            return

        if opcode == 4:  # periodic heartbeat/status push
            await self.client.write_gatt_char(FF02, build_ack(pkt), response=True)
            return

        if is_ack_for(pkt, 2, 0xD0):
            phone_key = key_bytes_for(self._phone_identifier())
            await self._send(bytes([0, 0, 2, 0xD1, 2, phone_key[1], phone_key[0]]))
            return

        if is_ack_for(pkt, 2, 0xD1):
            now = datetime.datetime.now()
            await self._send(bytes([
                0, 0, 8, 0xE0, 8,
                (now.year >> 8) & 0xFF, now.year & 0xFF,
                now.month, now.day, now.hour, now.minute, now.second,
                now.isoweekday() % 7,
            ]))
            return

        if is_ack_for(pkt, 8, 0xE0):
            print("*** logged in ***")
            self.logged_in.set()
            self._cap_stage = 10
            await self._send(bytes([0, 0, self._cap_stage]))
            return

        if self._cap_stage and is_category_ack(pkt, self._cap_stage):
            self._cap_stage += 1
            if self._cap_stage <= 13:
                await self._send(bytes([0, 0, self._cap_stage]))
            else:
                self._cap_stage = 0
                await self._read_settings()
            return

        if is_category_ack(pkt, 5) and not self.settings:
            self._parse_settings(pkt)
            await self._read_alarm_pair(1)
            return

        if is_category_ack(pkt, 5) and self.settings:
            self._parse_alarm_pair(pkt)
            base = self._pending_alarm_base
            if base < 8:
                await self._read_alarm_pair(base + 2)
            else:
                await self._read_battery()
            return

        if is_category_ack(pkt, 7):
            self.battery = {"percent": pkt[8], "state": pkt[9]}
            print(f"battery: {self.battery}")
            self.reads_done.set()
            return

    async def _read_settings(self) -> None:
        body = bytes([0, 0, 5, 0x50, 1, 0, 0x51, 1, 0, 0x52, 1, 0, 0x53, 1, 0])
        await self._send(body)

    def _parse_settings(self, pkt: bytes) -> None:
        if len(pkt) < 19:
            return
        self.settings = {
            "time_format": pkt[9],
            "alarm_ring": pkt[12],
            "alarm_voice": pkt[15],
            "alarm_duration": pkt[18],
        }
        print(f"settings: {self.settings}")

    async def _read_alarm_pair(self, slot: int) -> None:
        body = bytes([0, 0, 5]) + alarm_slot_block(slot) + alarm_slot_block(slot + 1)
        self._pending_alarm_base = slot
        await self._send(body)

    def _parse_alarm_pair(self, pkt: bytes) -> None:
        base = self._pending_alarm_base
        for row, off in ((base, 9), (base + 1, 15)):
            if len(pkt) <= off + 3 or row > 8:
                continue
            hour, minute, flags, daymask = pkt[off], pkt[off + 1], pkt[off + 2], pkt[off + 3]
            status = 0 if hour == 0xFF else (1 if flags & 1 else 2)
            self.alarms[row] = AlarmSlot(
                row=row, status=status, hour=hour, minute=minute,
                repeat=bool(flags & 2), days=decode_daymask(daymask),
            )
        print(f"alarms so far: {self.alarms}")

    async def _read_battery(self) -> None:
        body = bytes([0, 0, 7, 0x10, 1, 0, 0x11, 1, 0])
        await self._send(body)

    def _phone_identifier(self) -> str:
        import uuid
        return ":".join(re.findall("..", "%012x" % uuid.getnode()))

    async def connect_and_read_all(self, timeout: float = 40.0) -> None:
        async with BleakClient(self.address) as client:
            self.client = client
            await client.start_notify(FF01, self._on_ff01)
            await asyncio.wait_for(self.reads_done.wait(), timeout=timeout)

    async def wait_for_device(self, patience: float = 300.0) -> None:
        """Keep retrying until the device advertises, like the official app does.

        The app never rescans to reconnect — it connects straight to the stored
        MAC and lets Android hold the request pending, so it catches even a
        single brief advertisement. A scan-then-connect misses those windows;
        this loop approximates the app's behaviour.
        """
        from bleak import BleakScanner

        deadline = time.time() + patience
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            device = await BleakScanner.find_device_by_address(self.address, timeout=5.0)
            if device is not None:
                print(f"[{time.time():.3f}] found device on attempt {attempt}")
                return
            print(f"[{time.time():.3f}] attempt {attempt}: not advertising yet, retrying...")
        raise TimeoutError(f"device never advertised within {patience}s")


def _self_check() -> None:
    assert crc16_modbus(b"") == 0xFFFF
    assert key_bytes_for("AA:BB:CC:DD:EE:FF") == bytes.fromhex("9F3C")  # synthetic vector; algorithm confirmed against the real device separately
    c = FrameCounter()
    pkt = c.frame(bytes([0, 0, 2, 0xD0, 2, 0x1B, 0xCC]))
    assert pkt.hex() == "bb110800000002d0021bcc8f", pkt.hex()
    ack = build_ack(bytes.fromhex("bb11101100000101010102010103011504010013"))
    assert ack.hex() == "bb11101102008101010102010103011504010095", ack.hex()
    assert is_ack_for(bytes.fromhex("bb110800000082d0021bcc0f"), 2, 0xD0)
    assert not is_ack_for(bytes.fromhex("bb110b0500008cd0d1d2d3e0e1e251"), 2, 0xD0)  # category-12 response, byte7 coincidentally 0xD0
    assert is_category_ack(bytes.fromhex("bb11040000008a01"), 10)
    assert not is_category_ack(bytes.fromhex("bb11040000000a01"), 10)  # missing ack bit
    assert alarm_slot_block(1).hex() == "54040000007f", alarm_slot_block(1).hex()
    assert decode_daymask(0x7F) == [0, 1, 2, 3, 4, 5, 6]
    print("ok")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--connect":
        cli = PillControlClient(sys.argv[2])

        async def run() -> None:
            await cli.wait_for_device()
            await cli.connect_and_read_all()

        asyncio.run(run())
    else:
        _self_check()
