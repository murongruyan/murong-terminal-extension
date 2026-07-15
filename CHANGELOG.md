# Changelog

## 1.3 / 26071513 — 2026-07-15

### Fixed
- **pkg bad interpreter**: Termux 脚本硬编码的 `/data/data/com.termux/files/usr` 路径在主应用私有 toolchain 目录下不再导致的 `bad interpreter` 错误。构建层区分 ELF 与 shell 脚本，安装时自动重写所有 Termux 固定路径为运行时 `PREFIX`。

### Added
- **apt/dpkg 依赖闭包**: `termux-curated-packages.json` 加入 apt、dpkg、gpgv、termux-keyring 及其 73 个依赖包的完整解析和同步。
- **可重定位的脚本命令**: `pkg` 等非 ELF 命令改为可写给 asset，安装时由 `ToolchainManager` 执行路径重定位。
- **package manager 安全闸**: 上游 APT/dpkg ELF 因编译期固定 prefix 不可重定位，`pkg` 替换为诊断脚本，阻止误导性的自动安装尝试。

### Security
- **扩展签名校验**: 仅在扩展 APK 与主应用签名一致时才加载其工具链。
- **manifest 路径约束**: 所有 files、links、commands 路径经 canonicalize 和越界检查，非 `native/` 目标限制在 toolchain 根目录内，`native/` 目标限制为单文件名。
- **安装失败回滚**: toolchain 安装 I/O 失败时自动清理半成品并返回不可用状态。

### Changed
- `bundledToolchainVersion` 默认值从 `termux-curated-v1` 更新到 `termux-curated-v2`。
- 运行环境变量补齐 `PREFIX`、`TERMUX__PREFIX`、`TERMUX_APP_PACKAGE_MANAGER=apt`。
