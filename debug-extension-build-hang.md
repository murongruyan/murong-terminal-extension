# [OPEN] extension-build-hang

- Debug Server: `http://127.0.0.1:7777/event`
- Log File: `.dbg/trae-debug-log-extension-build-hang.ndjson`

## 现象
- `murong-terminal-extension` 在开启 `BUNDLED_TOOLCHAIN_ENABLE_DOWNLOAD=true` 后，`release` 构建长时间停在 `:app:prepareBundledToolchainSource`
- 之前编出的 `release` APK 只有占位资源，说明真实 toolchain 没有被打包进去

## 已知事实
- 默认构建路径下，`toolchain/prebuilt/arm64-v8a` 不存在
- 默认 `BUNDLED_TOOLCHAIN_ENABLE_DOWNLOAD=false`
- 开启下载后，Gradle 前台长时间停留在 `prepareBundledToolchainSource`

## 初始假设
1. `sync_toolchain.py` 在下载某个包或索引时阻塞，但 `inheritIO()` 没把进度稳定刷到当前终端，导致看起来像假死
2. `sync_toolchain.py` 的缓存目录或输出目录存在大量旧文件，导致某个文件操作异常缓慢
3. Python 进程实际在等待网络重试或 HTTPS 响应，Gradle 任务本身没有挂死，只是缺少阶段性可见证据
4. Gradle `prepareBundledToolchainSource` 对脚本子进程的调用方式有问题，子进程状态没有被正确感知或输出
5. 真实卡点不在下载，而在脚本解包 `.deb` / `tar` 的某个包阶段

## 调试约束
- 先只加观测与埋点，不先改业务逻辑
- 先拿到运行时证据，再决定修复方式

## 证据结论
- 旧行为：
  - Gradle 里只看到 `:app:prepareBundledToolchainSource`
  - 日志只到 `start download` / `received first download chunk`
  - 同一脚本单独运行可以完整下载并解包
- 关键判断：
  - 网络和镜像源本身不是根因
  - 根因在 `build.gradle.kts` 里通过 `ProcessBuilder(...).inheritIO()` 调 Python 子进程时，子进程输出没有被稳定消费，导致在当前环境里卡住
- 已做修复：
  - 改成 `redirectErrorStream(true)` 并由 Gradle 显式持续读取子进程输出
- 修复后结果：
  - `assembleRelease` 成功跑完整条链路
  - 日志已推进到 `package index resolved`、逐包解包、最终完成打包
  - 完整扩展包 `release` 已安装到设备
