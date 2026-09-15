# Medicine Doser

Personal-use interoperability research workspace for the DoseControl Wi-Fi pill dispenser (target model: `MC21-WF-MT`).

## Scope

- Analyze the official Android client after it is obtained from an owner-controlled device.
- Document observable network behavior and supported device functionality.
- Build a local-first replacement only if the device protocol can be used safely and reliably.

No production dispensing logic will be trusted without validation on the physical device.

## Layout

- `apk/` — acquired APKs and integrity hashes; do not commit redistributable binaries later.
- `decoded/` — JADX/apktool outputs.
- `notes/` — dated research findings and protocol notes.
- `captures/` — sanitized traffic captures.
- `src/` — implementation code.

## Next input needed

Install the official DoseControl Wi-Fi app on an Android device you control, enable USB debugging, then provide the output of:

```bash
adb devices
adb shell pm path lb.android.dosecontrol
```

We will pull the installed package from the device rather than using an APK mirror.
