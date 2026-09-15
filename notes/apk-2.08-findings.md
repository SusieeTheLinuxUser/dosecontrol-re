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

The exact encoder, from `device/SchemaProcessor.java`, confirms the field layout precisely:

```java
public static String encodeAlarm(AlarmData alarmData) {
    byte[] bArr = new byte[32];
    bArr[0] = alarmData.enabled ? (byte) 1 : (byte) 0;
    int[] alarmTimeAsArray = alarmData.getAlarmTimeAsArray();
    bArr[5] = (byte) alarmTimeAsArray[0];   // hour
    bArr[6] = (byte) alarmTimeAsArray[1];   // minute
    bArr[7] = 127;                          // day-of-week bitmask, always "all days" on save
    bArr[8] = 0;
    bArr[9] = 0;                            // taken-status, reset to 0 on save
    bArr[10] = 0;
    return HexUtil.bytesToHexString(bArr);  // bytes 11-31 stay zero
}
```

The decoder (`decodeAlarm`) reads the day-of-week mask from byte 7 as 8 individual bits (`AlarmData.Days.fromCode`), so devices can report a per-day mask even though the app itself always writes `127` (every day) on save.

## Account and Tuya-linking flow (confirmed from source)

- `BaseApplication.onCreate()` calls `ThingHomeSdk.init(this)` and `ThingHomeSdk.setDebugMode(false)` at process start — a single global Tuya SDK session for the whole app.
- The app's own account system is a Strapi backend (`dcapi.lost-bytes.com`), modeled by `data/StrapiUser.java`. A `StrapiUser` record carries `tuya_uid`, `tuya_home_number`, `tuya_room_number`, and `tuya_user_number` fields returned by the DoseControl backend — i.e. Tuya identity is assigned server-side per DoseControl account, not chosen by the device owner.
- **Important architecture finding:** the client does not use a per-customer Tuya account. `StrapiUser` embeds a hardcoded lookup table (keyed by `tuya_uid`) of shared Tuya cloud account credentials, and `HomeDashboardActivity`/`UserVerifyActivity` call `ThingHomeSdk.getUserInstance().loginWithEmail(...)` directly with those credentials to establish the Tuya SDK session. In other words, DoseControl pools many customers' devices into a small number of shared Tuya cloud accounts (distinguished internally via home/room/user numbers), rather than giving each customer an isolated Tuya account.
- **This is a vendor-side security finding, not just an interop detail.** The pooled account credentials are plaintext strings embedded in the publicly distributed APK, recoverable by static decompilation (as done here). Anyone who decompiles the app gets working login credentials to cloud accounts that plausibly control other customers' dispensers, not just the extracting user's own device. The actual credential values are **not** included in this file — see the (gitignored, local-only) `notes/local-only-tuya-pool-credentials.md` for reference, and do not publish them anywhere. Recommend responsible disclosure to the vendor describing the architecture flaw without needing to publish live credentials.
- Device pairing (`device/DeviceRegistrationNewActivity.java`) requests a Tuya activator token via `ThingHomeSdk.getActivatorInstance().getActivatorToken(homeId, ...)`, scoped to the current "home" (`HomeModel.getCurrentHome()`, a `SharedPreferences`-stored home ID local to the app), then starts AP-mode pairing with `ActivatorBuilder().setActivatorModel(ActivatorModelEnum.THING_AP)`.

## Additional embedded constants (`Consts.java`)

- A hardcoded JWT (`API_JWT`) used by `UserLoginActivity` for what appears to be a fallback/legacy login path. Decoded payload: `{"id":26,"iat":2022-10-05,"exp":2022-11-04}` — **expired since November 2022**, so not a live credential, but still a code-quality finding (a static token should never be embedded regardless of expiry).
- `PAYMENT_KEY`: an RSA **public** key (not sensitive by construction — public keys are meant to be embedded for client-side encryption).
- A live Stripe **publishable** key (`pk_live_...`) used to init the Stripe SDK — publishable keys are designed to be client-embedded and cannot move funds on their own; standard practice, not a leak.

## Immediate next steps

1. ~~Decompile with JADX and apktool to map the app classes that call the custom API and Tuya SDK.~~ Done via JADX (see "Account and Tuya-linking flow" above); apktool not yet needed.
2. Identify the Tuya product identifier and DP schema after a dispenser is paired. The client source doesn't embed a static product ID — it's assigned server-side per device, so this requires a live pairing capture.
3. Capture only owner-controlled pairing and configuration actions, one change at a time.
4. Treat dispensing as safety-critical: do not issue any experimental dispensing action against a loaded dispenser.
5. Decide how to handle the pooled-Tuya-credential vendor vulnerability (see above) — at minimum avoid using it; consider responsible disclosure to the vendor.
