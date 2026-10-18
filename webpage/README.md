# Sehat Saathi showcase and Android package

This folder contains the public-facing Sehat Saathi showcase page, its installable
PWA shell, and the Trusted Web Activity configuration used to produce an Android
APK.

## Local preview

Serve the repository through a static server rather than opening `index.html`
directly so the service worker can register:

```powershell
python -m http.server 4173 -d webpage
```

The embedded product preview expects the live app at
`http://127.0.0.1:5173/`.

## APK pipeline

The GitHub Actions workflow at
`.github/workflows/build-sehat-saathi-apk.yml` builds a signed release TWA APK
with Bubblewrap. Before running it:

1. Deploy the `webpage/` directory over HTTPS.
2. Add the repository variable `SEHAT_SAATHI_HOST`, containing only the host,
   for example `sehat-saathi.example.com`.
3. Add the signing secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEY_ALIAS`,
   `BUBBLEWRAP_KEYSTORE_PASSWORD`, and `BUBBLEWRAP_KEY_PASSWORD` according to
   the keystore used by the Android release process.
4. Run the workflow manually or push a tag matching `webpage-v*`.

The resulting signed APK is uploaded as the `sehat-saathi-android` workflow
artifact. When the workflow runs from a `webpage-v*` tag, it also creates a
GitHub Release containing `Sehat-Saathi.apk`. The webpage uses the stable URL
below by default, so it continues to work when a newer release is published:

`https://github.com/abdullahnadeem215/sehatsaathi/releases/latest/download/Sehat-Saathi.apk`

You can override that URL by defining `window.SEHAT_SAATHI_APK_URL` before
`app.js` loads.

AMD API keys, model endpoints, and operator tokens must remain in the backend
environment. They are never copied into this public webpage or APK metadata.
