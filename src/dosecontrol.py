"""DoseControl client: Tuya alarm codec + custom backend API.

Confirmed from static analysis of lb.android.dosecontrol v2.08 — see
notes/apk-2.08-findings.md. This does NOT talk to the dispenser directly:
Tuya DP read/write (alarms, settings) needs the paired device's Tuya
local_key or cloud session, which we don't have until pairing happens.
Once paired, feed DPs through Alarm.decode()/encode() and hand the
resulting hex to whatever Tuya channel you use (tinytuya, Tuya Cloud API).

Note: the app's own requests to the custom backend send NO Authorization
header (ApiWrapper.SendJsonRequest.getHeaders() returns an empty map) —
so this wrapper doesn't send one either. That's a vendor finding worth
keeping in mind, not an oversight here.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import IntEnum

# Tuya data points (device/SchemaProcessor.java)
DP_ALARM = {i: str(100 + i) for i in range(1, 10)}  # slot 1-9 -> "101".."109"
DP_TIME = "112"
DP_TIME_FORMAT = "113"
DP_LOADED_CELLS = "117"
DP_REMAINING_CELLS = "118"
DP_LOW_BATT = "119"
DP_ON_ADAPTER = "121"
DP_VOLUME = "122"
DP_RING_DURATION = "123"
DP_WARNING_RING_TIME = "124"
DP_RING_TYPE = "126"
DP_ALARM_IS_MUTED = "127"


class Day(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class TakenStatus(IntEnum):
    PENDING = 0
    MISSED = 1
    TAKEN = 2
    TAKEN_LATE = 3
    TAKEN_EARLY = 4


@dataclass
class Alarm:
    enabled: bool
    hour: int
    minute: int
    days: list[Day] = field(default_factory=lambda: list(Day))
    taken_status: TakenStatus = TakenStatus.PENDING

    def encode(self) -> str:
        """32-byte hex payload, matching SchemaProcessor.encodeAlarm exactly."""
        b = bytearray(32)
        b[0] = 1 if self.enabled else 0
        b[5] = self.hour
        b[6] = self.minute
        b[7] = 127  # the official app always writes "every day", regardless of self.days
        return b.hex()

    @classmethod
    def decode(cls, hex_str: str) -> Alarm:
        """Matches SchemaProcessor.decodeAlarm exactly."""
        b = bytes.fromhex(hex_str)
        if b[0] != 1:
            return cls(enabled=False, hour=0, minute=0, days=[], taken_status=TakenStatus.PENDING)
        days = [d for d in Day if (b[7] >> d) & 1]
        return cls(enabled=True, hour=b[5], minute=b[6], days=days, taken_status=TakenStatus(b[9]))


API_URL = "https://dcapi.lost-bytes.com/api"


class ApiError(Exception):
    pass


class DoseControlApi:
    """Custom backend only (account/history/settings) — not the Tuya device channel."""

    def __init__(self, base_url: str = API_URL):
        self.base_url = base_url

    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(
            self.base_url + path, data=body, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise ApiError(f"{method} {path} -> {e.code}: {e.read().decode(errors='replace')}") from e

    def check_user(self, email: str) -> dict:
        return self._request("POST", "/user/check", {"email": email})

    def get_devices(self, uid: int) -> dict:
        return self._request("GET", f"/user/devices/{uid}")

    def get_device_settings(self, dispenser_id: str) -> dict:
        return self._request("GET", f"/dispenser/{dispenser_id}/settings")

    def save_device_settings(self, dispenser_id: str, doses_per_day: int) -> dict:
        return self._request("POST", f"/dispenser/{dispenser_id}/settings",
                              {"data": {"doses_per_day": doses_per_day}})

    def get_pill_records(self, uid: int, dispenser_id: str, from_date: str, to_date: str) -> dict:
        return self._request(
            "GET", f"/dose-history/get/{dispenser_id}/{uid}?fromDate={from_date}&toDate={to_date}"
        )


def _self_check() -> None:
    a = Alarm(enabled=True, hour=7, minute=30)
    encoded = a.encode()
    assert len(encoded) == 64
    raw = bytes.fromhex(encoded)
    assert (raw[0], raw[5], raw[6], raw[7]) == (1, 7, 30, 127)

    decoded = Alarm.decode(encoded)
    assert decoded.enabled and decoded.hour == 7 and decoded.minute == 30
    assert decoded.taken_status == TakenStatus.PENDING
    assert set(decoded.days) == set(Day)  # byte7=127 -> every day

    assert bytes.fromhex(Alarm(enabled=False, hour=0, minute=0).encode())[0] == 0
    print("ok")


if __name__ == "__main__":
    _self_check()
