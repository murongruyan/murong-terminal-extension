# 慕容终端扩展

`慕容 Agent` 的无界面 Android 配套包。

## 用途

- 作为独立可安装包发布。
- 无启动器图标，无用户可见界面。
- 复用与 `慕容 Agent` 相同的发布签名链。
- 暴露一个小型元数据提供者，使 `慕容 Agent` 能够检测扩展包是否已安装及其状态。
- 在构建时将预置的终端工具链打包进 APK。

## 规划功能

- 携带完整的终端工具链，该工具链必须存在于可安装包内。
- 在 CI 或本地构建期间下载精选的 Termux 软件包，进行标准化处理后打包进 APK。
- 使 `慕容 Agent` 在可用时优先使用此包，否则回退到系统环境。

## 当前状态

- 无启动器 Activity。
- 无图标入口。
- 元数据提供者 authority：`cc.rl1.murong.terminalextension.metadata`
- 工具链同步脚本：`scripts/sync_toolchain.py`
- 精选 Termux 软件包列表：`toolchain/termux-curated-packages.json`
- GitHub Actions 工作流：`.github/workflows/build-extension.yml`

## 构建

### 本地日常构建

日常本地构建应使用 `toolchain/prebuilt/arm64-v8a` 下已预置的工具链。

```bash
./gradlew --no-configuration-cache :app:assembleRelease
```

或直接安装：

```bash
./gradlew --no-configuration-cache :app:installRelease
```

### 刷新工具链预构建产物

当你确实需要升级内置终端工具链时，先刷新本地预构建产物，再正常构建。

Windows：

```powershell
.\gradlew.bat --no-configuration-cache :app:refreshBundledToolchainPrebuilt
```

可选覆盖参数：

- `-PBUNDLED_TOOLCHAIN_DOWNLOAD_TIMEOUT=60`
- `-PBUNDLED_TOOLCHAIN_DOWNLOAD_RETRIES=4`
- `-PBUNDLED_TOOLCHAIN_VERSION=toolchain-v2`

刷新完成后，使用正常的 release 命令重新构建。

### GitHub Actions

工作流支持两种模式：

- **默认**：从已提交/本地的预构建工具链进行构建。
- **手动刷新**：通过 `workflow_dispatch` 触发并设置 `refresh_toolchain=true`，工作流会先刷新 `toolchain/prebuilt/<abi>`，再将结果打包为 release APK。

工作流手动触发输入参数：

| 参数 | 说明 |
|------|------|
| `refresh_toolchain` | 构建前是否刷新内置工具链 |
| `toolchain_version` | 工具链版本标签 |
| `app_version_name` | **语义版本名**（如 `1.2.0`），用于展示给用户 |
| `app_version_code` | **内部版本号**（正整数，如 `26070412`），Android 用于判断版本新旧，值越大版本越新 |
| `release_tag` | GitHub Release 标签（如 `murong-terminal-extension-v1.2.0`）；留空则自动生成 |
| `release_name` | Release 标题（如 `Murong Terminal Extension 1.2.0 (26070412)`）；留空则自动生成 |
| `sync_to_server` | 是否通过后端 API 上传扩展包并回写版本信息 |

> **版本号说明**：`app_version_name` 是给人看的「显示版本号」，格式像 `1.2.0`；`app_version_code` 是给系统用的「内部版本号」，是一个正整数（如 `26070412`），每次发版必须比上次更大。

所需密钥：

- `KEYSTORE_BASE64`
- `STORE_PASSWORD`
- `KEY_PASSWORD`

## 推荐更新流程

1. 仅在确实需要升级精选工具链时运行 `:app:refreshBundledToolchainPrebuilt`。
2. 使用 `:app:assembleRelease` 或 `:app:installRelease` 在本地验证。
3. 提升扩展包版本号，然后发布新的 APK。

这样可以保持日常构建快速，同时让工具链更新变为显式操作，而非每次构建都重新下载所有内容。
