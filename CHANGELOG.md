# Changelog

## 1.10 / 26071720 — 2026-07-20

### Added
- **完整可重定位 Termux 环境**: APK 内置 Bash、Git、ripgrep、BusyBox、`apt`、`pkg`、`dpkg`、PRoot、证书与包数据库依赖闭包；主程序解包到私有工具链目录后仍能正确解析命令、相对链接和 Termux 固定前缀。
- **官方 Codex app-server**: 固定打包并验证 OpenAI `rust-v0.144.5` 的 ARM64 musl app-server，同时携带来源元数据、归档 SHA-256 与 Apache-2.0 License。

### Fixed
- **GitHub 发布包缺少 Codex**: Release 工作流现在与本地构建走同一条完整工具链路径，并在打包后验证 `codex-app-server` 的命令入口、ARM64 ELF、固定来源元数据和 Apache-2.0 许可证；缺任一项即失败，不能发布。
- **升级可识别**: 默认版本号提升，主应用会因新的工具链指纹重新解包命令入口，不会继续复用旧扩展的无 Codex 工具链。
- **绝对链接与 Root 环境失效**: Termux 固定绝对链接转换为包内相对链接，脚本安装时重写实际 `PREFIX`，原生命令通过 APK 可执行实体加载；扩展 Bash 在主程序取得 Root 后不会因为切换到系统 Shell 而丢失工具链。

### Changed
- 主仓库的统一 `build-all.yml` 会直接检出扩展 `main` 并与主 APK、六个桌面包和两个云中继包一起构建；最终完整性门禁必须同时获得全部 10 个正式包并通过 SHA-256 校验。

## 1.7 / 26071617 — 2026-07-16

### Added
- **官方 Codex app-server**: 固定打包 OpenAI `rust-v0.144.5` 的 ARM64 musl dedicated app-server，命令名为 `codex-app-server`，并对下载归档执行固定 SHA256、ELF64 与 AArch64 校验。
- **可审计许可证**: APK 工具链随包携带 Codex app-server 的 Apache-2.0 许可证和固定来源元数据。

### Fixed
- **普通 push 不再产出 placeholder 工具链**: GitHub Workflow 明确启用完整工具链同步，并在最终 APK manifest 中强制校验 `apt`、`bash`、`pkg`、`proot` 与 `codex-app-server` 等命令及其实际载荷。

### Changed
- 工具链指纹更新为 `termux-curated-v6-codex-app-server-0.144.5`，确保已安装的旧工具链会重新解包新增命令。

## 1.6 / 26071616 — 2026-07-16

### Fixed
- **Android W^X 下 PRoot 子进程无法启动**: `PROOT_LOADER` 改为扩展 APK 原生库，由主应用通过 APK 内可执行实体引用；不再从 `targetSdk 37` 主应用的数据目录直接执行 loader。
- **系统 linker 兼容链路**: 为 PRoot 后续的 `bash`、`apt`、`dpkg` 与新安装命令保留 `termux-exec` system-linker 执行模式。

### Changed
- 工具链指纹更新为 `termux-curated-v5`，强制已安装环境重新生成 APK 内 `proot-loader` 命令入口。

## 1.5 / 26071615 — 2026-07-16

### Fixed
- **扩展环境无法启用**: 构建 manifest 时把指向 `/data/data/com.termux/...` 的绝对 symlink 转换为工具链内相对链接，既满足主程序沙箱校验，也保留链接功能。
- **bin symlink 目标重复拼接**: Termux 绝对 prefix 目标现在从工具链根目录解析，避免 `bzcmp`、`bzless` 被错误写成不存在的 `bin/bin/...`。
- **工作流产物防回归**: GitHub Actions 现在直接读取最终 release APK 内的 manifest；若仍包含绝对目标链接则立即终止发布。
- **APT keyring 被误删**: `etc/apt/trusted.gpg.d` 和 pacman keyring 链接不再被过滤，仓库签名验证可正常读取扩展内公钥。

### Added
- **可用的 `pkg`/`apt`/`dpkg` 运行时**: 扩展加入 `proot` 前缀映射及依赖，让官方 Termux 包在 MurongAgent 私有工具链目录中按其编译期前缀运行。
- **预置包数据库**: 构建时为预置包生成 `dpkg` status、文件列表和维护脚本元数据，避免包管理器把扩展已携带的依赖误判为未安装。

### Changed
- 修复提交从历史 `master` 分支带回默认 `main` 发布链路，确保工作流构建实际包含链接正规化逻辑。
- 本地默认工具链指纹更新为 `termux-curated-v4`，确保已安装的旧缓存会重新解包 keyring、包数据库与 PRoot 兼容层。

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
