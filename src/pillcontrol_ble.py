"""PillControl BLE client (the actual owned device — see notes/pillcontrol-1.16-findings.md).

Confirmed working standalone against the real dispenser (2026-09-18):
completes the full login handshake and reaches the device's "logged in"
state, independent of the official app or phone.

Requires: pip install bleak

Protocol summary (full detail in notes/):
  - Service 0000ff00-..., write char FF02, notify char FF01.
  - Frame: [0xBB, 0x11, len(body)+1, seq, ...body(response-type,status,tag,payload)..., checksum]
    checksum = sum(all preceding bytes) mod 256.
  - Device pushes a login packet (tag 1) on connect; ack it, then send a
    "device key" (tag 0xD0) derived from CRC16/MODBUS of the device's own
    MAC, then a "phone key" (tag 0xD1, same derivation from the phone's
    MAC — the device may reject an unrecognized one, but the app proceeds
    regardless), then a date/time sync (tag 0xE0). The device then
    considers the session logged in.
"""

from __future__ import annotations

import asyncio
import datetime
import re
import time

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


def is_ack_for(pkt: bytes, tag: int) -> bool:
    """True if pkt is the device's ack for an app-initiated request carrying this tag.

    For app-initiated requests, byte 6 is a sub-payload length (not an
    opcode) and byte 7 carries the real command tag; the ack just sets the
    high bit of byte 6 and echoes the rest.
    """
    return len(pkt) > 7 and pkt[0] == 0xBB and (pkt[6] & 0x80) and pkt[7] == tag


class PillControlClient:
    def __init__(self, address: str):
        self.address = address
        self.client: BleakClient | None = None
        self.counter = FrameCounter()
        self.logged_in = asyncio.Event()

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

        elif opcode == 4:  # periodic heartbeat/status push
            await self.client.write_gatt_char(FF02, build_ack(pkt), response=True)

        elif is_ack_for(pkt, 0xD0):
            phone_key = key_bytes_for(self._phone_identifier())
            await self._send(bytes([0, 0, 2, 0xD1, 2, phone_key[1], phone_key[0]]))

        elif is_ack_for(pkt, 0xD1):
            now = datetime.datetime.now()
            await self._send(bytes([
                0, 0, 8, 0xE0, 8,
                (now.year >> 8) & 0xFF, now.year & 0xFF,
                now.month, now.day, now.hour, now.minute, now.second,
                now.isoweekday() % 7,
            ]))

        elif is_ack_for(pkt, 0xE0):
            print("*** logged in ***")
            self.logged_in.set()

    def _phone_identifier(self) -> str:
        import uuid
        return ":".join(re.findall("..", "%012x" % uuid.getnode()))

    async def connect_and_login(self, timeout: float = 20.0) -> None:
        async with BleakClient(self.address) as client:
            self.client = client
            await client.start_notify(FF01, self._on_ff01)
            await asyncio.wait_for(self.logged_in.wait(), timeout=timeout)


def _self_check() -> None:
    assert crc16_modbus(b"") == 0xFFFF
    assert key_bytes_for("AA:BB:CC:DD:EE:FF") == bytes.fromhex("9F3C")  # synthetic vector; algorithm confirmed against the real device separately
    c = FrameCounter()
    pkt = c.frame(bytes([0, 0, 2, 0xD0, 2, 0x1B, 0xCC]))
    assert pkt.hex() == "bb110800000002d0021bcc8f", pkt.hex()
    ack = build_ack(bytes.fromhex("bb11101100000101010102010103011504010013"))
    assert ack.hex() == "bb11101102008101010102010103011504010095", ack.hex()
    assert is_ack_for(bytes.fromhex("bb110800000082d0021bcc0f"), 0xD0)
    print("ok")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--connect":
        cli = PillControlClient(sys.argv[2])
        asyncio.run(cli.connect_and_login())
    else:
        _self_check()
