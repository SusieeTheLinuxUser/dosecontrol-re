# Initial reconnaissance

Date: 2026-09-15

## Android connection

- ADB-connected device: `[redacted]`
- Connection state: authorized (`device`)
- DoseControl package `lb.android.dosecontrol`: not presently installed.
- No installed package name matching `dose`, `pill`, `med`, or `control` appears to be the DoseControl client.

## Local tooling

Not installed at this point:

- `jadx` / `jadx-cli`
- `apktool`
- Android `aapt`

Available:

- `adb`
- `sha256sum`

## Next action

Install the official **DoseControl Wi-Fi** app from Google Play on the connected Android device. Once installed, obtain its exact package path with:

```bash
adb shell pm path lb.android.dosecontrol
```

Then extract the APK, hash it, and inspect the manifest, resources, and code for endpoints, transport libraries, certificate pinning, and device protocol hints.
