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
- Curated Termux package list: `toolchain/termux-curated-packages.json`
- GitHub Actions workflow: `.github/workflows/build-extension.yml`

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

The workflow supports two modes:

- **Default**: build from the checked-in/local prebuilt toolchain.
- **Manual refresh**: trigger `workflow_dispatch` with `refresh_toolchain=true`, the workflow refreshes `toolchain/prebuilt/<abi>` first and packages the release APK from that result.

Workflow dispatch inputs:

| Input | Description |
|-------|-------------|
| `refresh_toolchain` | Whether to refresh the bundled toolchain prebuilt before building |
| `toolchain_version` | Toolchain version tag |
| `app_version_name` | **Semantic version name** (e.g. `1.2.0`), displayed to users |
| `app_version_code` | **Internal version code** (positive integer, e.g. `26070412`), used by Android to determine version recency; higher = newer |
| `release_tag` | GitHub Release tag (e.g. `murong-terminal-extension-v1.2.0`); defaults to auto-generated |
| `release_name` | Release title (e.g. `Murong Terminal Extension 1.2.0 (26070412)`); defaults to auto-generated |
| `sync_to_server` | Whether to sync the APK and version info to the backend server via API |

> **Version note**: `app_version_name` is the human-readable display version (format like `1.2.0`); `app_version_code` is the internal version number (a positive integer like `26070412`) that must increase with every release.

Required secrets:

- `KEYSTORE_BASE64`
- `STORE_PASSWORD`
- `KEY_PASSWORD`

## Recommended update flow

1. Run `:app:refreshBundledToolchainPrebuilt` only when the curated toolchain really needs an upgrade.
2. Verify locally with `:app:assembleRelease` or `:app:installRelease`.
3. Bump the extension version label, then publish the new APK.

This keeps normal builds fast and makes toolchain updates explicit instead of re-downloading everything on every build.
