# DoseControl WiFi APK 2.08 — initial static findings

Date: 2026-09-15

## Provenance

- Source: Play Store installation on the owner-controlled Android device.
- Package: `lb.android.dosecontrol`
- Version: `2.08` (`versionCode` 87)
- Base APK: `apk/dosecontrol-2.08-base.apk`
- Base APK SHA-256: `831b34cc386eddddb186cf316ad4a3a44a484303347877e853b037e80cefe44f`
- English resource split: `apk/dosecontrol-2.08-config-en.apk`
- English resource split SHA-256: `240d19c3350ade8eb3fe340c43f8c71b3a2f6e84684bb40681b2b51605d653c1`

## Confirmed architecture

The app bundles the **ThingClips/Tuya Smart SDK**. Relevant embedded package names include:

- `com.thingclips.smart.*`
- `com.thingclips.sdk.*`
- `com.thingclips.smart.sdk.mqtt.api`
- `com.thingclips.smart.dp.parser.*`

This indicates Tuya-style product schemas and data points (DPs), with MQTT used by the vendor SDK for cloud/device updates. It does **not** yet establish a directly usable local command protocol.

## Provisioning evidence

Embedded app copy directs the user to:

1. Put the dispenser into AP mode by holding `+` for three seconds.
2. Join the dispenser access point, named `SmartLife-XXXX`.
3. Provide a 2.4 GHz Wi-Fi SSID and password.
4. Return to the app to complete connection.

This is consistent with Tuya AP-mode provisioning and gives us a controlled local observation point when the dispenser is available.

## DoseControl-operated API endpoints

The following strings are embedded in the official APK:

- `https://dcapi.lost-bytes.com/api`
- `https://dcapi.lost-bytes.com/api/auth/local`
- `https://dcapi.lost-bytes.com/api/auth/local/register`
- `https://dcapi.lost-bytes.com/api/otp/verify`
- `https://dcapi.lost-bytes.com/api/otps`
- `https://dcapi.lost-bytes.com/api/user/check`
- `https://dcapi.lost-bytes.com/api/user/refresh`
- `https://dcapi.lost-bytes.com/api/user/reset`
- `https://dcapi.lost-bytes.com/api/user/migrate`
- `https://dcapi.lost-bytes.com/api/user/add_device`
- `https://dcapi.lost-bytes.com/api/user/remove_device`
- `https://dcapi2.lost-bytes.com/appconfigg/%uid%/`

The API domain and the Tuya cloud SDK are separate layers: the former appears to manage DoseControl accounts and records; the latter appears to manage the smart-device lifecycle and commands.

## App features visible in resources

- Alarm scheduling, duration, ringtone, volume, and voice alarm.
- Daily-dose count and remaining-dose counter.
- Dose records: taken, late, and missed.
- Notifications for alarm start, taken/missed doses, low doses, and disconnection.
- Remote access is subscription-gated according to in-app copy.
- Firebase Cloud Messaging is used for push delivery.

## Android surface

The package declares Wi-Fi, Bluetooth, location, networking, wake-lock, and notification permissions. Its registered custom components include:

- `lb.android.dosecontrol.activity.HomeDashboardActivity`
- `lb.android.dosecontrol.activity.user.UserFuncActivity`
- `lb.android.dosecontrol.utils.DcFirebaseMessagingService`

## Decompilation results

JADX `1.5.6` was obtained directly from the upstream `skylot/jadx` GitHub release and unpacked under `tools/jadx/`. The release ZIP SHA-256 is:

`545ea2be9c242511bc145755cf4bda2485ade42966e096f8b4d3da2a230e8974`

The decompiled source is at `decoded/jadx-2.08/`. JADX reported 323 decompilation errors in third-party code, but the application classes under `sources/lb/android/dosecontrol/` are readable and sufficient for the findings below.

### Confirmed Tuya API usage

The app calls `ThingHomeSdk.init(this)` and uses `ThingHomeSdk.newDeviceInstance(deviceId).publishDps(json, callback)` for configuration writes. Pairing is performed using `ActivatorModelEnum.THING_AP` after requesting a Tuya activator token for the current home.

This confirms the official app does **not** use a bespoke direct HTTP command channel for normal configuration. The command path shown by the app source is:

`DoseControl app -> ThingClips/Tuya SDK -> Tuya cloud/device channel -> dispenser`

Whether the dispenser also exposes a separate local LAN protocol remains **unknown**.

### Confirmed device data points

| DP | Meaning | Value type / observed encoding |
| --- | --- | --- |
| 101-109 | Alarms 1-9 | 32-byte hex string |
| 112 | Device time | four hex characters representing hour and minute |
| 113 | 24-hour time setting | boolean |
| 117 | Loaded-cell count | integer |
| 118 | Remaining-cell count | integer |
| 119 | Low-battery status | boolean |
| 121 | On-external-power status | boolean |
| 122 | Alarm volume | stringified integer |
| 123 | Alarm duration | integer |
| 124 | Warning-ring duration | integer |
| 126 | Ring/voice type | stringified integer |
| 127 | Alarm-muted state | boolean |

### Alarm format

The official app serializes every alarm as a 32-byte value represented as hexadecimal. The decoded structure used by its `SchemaProcessor` is:

- byte `0`: enabled (`1` means enabled)
- bytes `5-6`: hour and minute
- byte `7`: day-of-week bit mask
- byte `9`: taken-status value

When saving an enabled alarm, the app writes byte `7` as `127` and byte `9` as `0`. It sends this as `{"<alarm DP>": "<64 hex characters>"}` through `publishDps`.

This is static source evidence only. Do not write these values to hardware until the owned dispenser has been characterized safely.

## Immediate next steps

1. Decompile with JADX and apktool to map the app classes that call the custom API and Tuya SDK.
2. Identify the Tuya product identifier and DP schema after a dispenser is paired.
3. Capture only owner-controlled pairing and configuration actions, one change at a time.
4. Treat dispensing as safety-critical: do not issue any experimental dispensing action against a loaded dispenser.
