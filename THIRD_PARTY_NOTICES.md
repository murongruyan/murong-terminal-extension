# Third-Party Notices

## OpenAI Codex app-server

Murong Terminal Extension redistributes the official `codex-app-server` binary from
[openai/codex](https://github.com/openai/codex), release tag `rust-v0.144.5`, asset
`codex-app-server-aarch64-unknown-linux-musl.tar.gz`.

The component is distributed under the Apache License, Version 2.0. A copy of that
license is stored at `third_party/codex-app-server/LICENSE` and is included in the
packaged toolchain at `share/LICENSES/codex-app-server/LICENSE`.

The upstream binary is not modified; the extension packages it under the dedicated
runtime command name `bin/codex-app-server`. It is not presented as the full Codex CLI.
