# LabForge Android app

The app is this React frontend wrapped with Capacitor. It talks to the same backend as the website.

## Build a debug APK
```
cp .env.example .env          # VITE_API_BASE = the backend URL
npm ci
npm run build:app             # vite build + cap sync android
cd android
echo "sdk.dir=C:/path/to/Android/Sdk" > local.properties   # forward slashes
JAVA_HOME=<JDK 21> ./gradlew assembleDebug                  # JDK 21, not 25
```
APK: `android/app/build/outputs/apk/debug/app-debug.apk`.

## Release APK
Create `android/keystore.properties` (gitignored) with `storeFile`, `storePassword`, `keyAlias`, `keyPassword`,
then `./gradlew assembleRelease`. Keep the keystore backed up and out of git.

## How it differs from the website
- `src/native.ts`: `isNative()`, and `saveBlob()` which opens the Android share sheet for Word/PDF files.
- `src/api.ts`: `VITE_API_BASE`, and a `Bearer` token (the app has no cookie jar). The backend accepts it
  (see `session_token` in `apps/api/main.py`) and returns the token only when `X-LabForge-App: 1` is sent.
- `src/rewarded.ts`: AdMob rewarded ads in the app. Google test ids until `VITE_ADMOB_REWARDED_ID` and the
  AdMob app id in `AndroidManifest.xml` are replaced.
- Credit-pack purchases (Razorpay) are hidden in the app; Google Play requires Play Billing for digital goods.
- `LF_TEST=1` builds an emulator-only app that talks to a backend on the dev machine over http.
