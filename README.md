# Murong Terminal Extension

Headless Android companion package for `Murong Agent`.

## Purpose

- Ships as a separate installable package.
- Has no launcher icon and no user-facing UI.
- Reuses the same release signing chain as `murongagent`.
- Exposes a small metadata provider so `Murong Agent` can detect whether the extension package is installed and what state it reports.
- Bundles a staged terminal toolchain into the APK at build time.

## Planned Role

- Carry a full terminal toolchain that must live inside an installable package.
- Download curated Termux packages during CI or local builds, normalize them, and bundle them into the APK.
- Let `Murong Agent` prefer this package when available, and otherwise fall back to the system environment.

## Current State

- No launcher activity.
- No icon entry.
- Metadata provider authority: `cc.rl1.murong.terminalextension.metadata`
- Toolchain staging script: `scripts/sync_toolchain.py`
- Pinned Codex app-server merge script: `scripts/sync_codex_app_server.py`
- Curated Termux package list: `toolchain/termux-curated-packages.json`
- GitHub Actions workflow: `.github/workflows/build-extension.yml`

The extension packages the official OpenAI `codex-app-server` ARM64 musl release as
`bin/codex-app-server`. It is a dedicated app-server executable, not the full `codex`
CLI. The source is pinned reproducibly to:

- Tag: `rust-v0.144.5`
- Asset: `codex-app-server-aarch64-unknown-linux-musl.tar.gz`
- SHA256: `d2230513fcbe363e6230a4cb53917fafd68c2d2bad953035d99059eb18c07117`

## Build

### Local daily build

Daily local builds should use the staged prebuilt toolchain under `toolchain/prebuilt/arm64-v8a`.

```bash
./gradlew --no-configuration-cache :app:assembleRelease
```

Or install directly:

```bash
./gradlew --no-configuration-cache :app:installRelease
```

### Refresh toolchain prebuilt

When you actually want to upgrade the bundled terminal toolchain, refresh the local prebuilt once and then build normally.

Windows:

```powershell
.\gradlew.bat --no-configuration-cache :app:refreshBundledToolchainPrebuilt
```

Optional overrides:

- `-PBUNDLED_TOOLCHAIN_DOWNLOAD_TIMEOUT=60`
- `-PBUNDLED_TOOLCHAIN_DOWNLOAD_RETRIES=4`
- `-PBUNDLED_TOOLCHAIN_VERSION=toolchain-v2`

After refresh completes, build again with the normal release command.

### GitHub Actions

The workflow now supports two modes:

- Push/default: synchronize and package a real complete toolchain; placeholder output is
  rejected by the APK manifest verification step.
- Manual refresh: trigger `workflow_dispatch` with `refresh_toolchain=true`, then the workflow refreshes `toolchain/prebuilt/<abi>` first and packages the release APK from that result.

Both paths verify that the final APK manifest contains `codex-app-server`, that its
native payload is an ELF64 little-endian AArch64 executable, and that the pinned source
metadata and Apache-2.0 license are packaged.

Workflow dispatch inputs:

- `refresh_toolchain`
- `toolchain_version`
- `app_version_name`

Required secrets:

- `KEYSTORE_BASE64`
- `STORE_PASSWORD`
- `KEY_PASSWORD`

## Recommended update flow

1. Run `:app:refreshBundledToolchainPrebuilt` only when the curated toolchain really needs an upgrade.
2. Verify locally with `:app:assembleRelease` or `:app:installRelease`.
3. Bump the extension version label, then publish the new APK.

This keeps local builds with a refreshed prebuilt fast, while CI push builds prioritize
completeness and reproducibility by synchronizing the pinned inputs.

## Third-party license

The bundled OpenAI Codex app-server is distributed under Apache-2.0. See
`THIRD_PARTY_NOTICES.md` and `third_party/codex-app-server/LICENSE`; the license is also
included inside the generated toolchain at
`share/LICENSES/codex-app-server/LICENSE`.
