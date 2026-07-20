#!/usr/bin/env python3
"""Merge the pinned official Codex app-server release into a staged toolchain."""

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import struct
import tarfile
import tempfile
import time
import urllib.error
import urllib.request


CODEX_TAG = "rust-v0.144.5"
CODEX_ASSET = "codex-app-server-aarch64-unknown-linux-musl.tar.gz"
CODEX_ARCHIVE_SHA256 = "d2230513fcbe363e6230a4cb53917fafd68c2d2bad953035d99059eb18c07117"
CODEX_DOWNLOAD_URL = (
    f"https://github.com/openai/codex/releases/download/{CODEX_TAG}/{CODEX_ASSET}"
)
CODEX_BINARY_MEMBER = "codex-app-server-aarch64-unknown-linux-musl"
CODEX_INSTALL_PATH = pathlib.PurePosixPath("bin/codex-app-server")
CODEX_LICENSE_INSTALL_PATH = pathlib.PurePosixPath(
    "share/LICENSES/codex-app-server/LICENSE"
)
CODEX_METADATA_INSTALL_PATH = pathlib.PurePosixPath(
    "metadata/codex-app-server.json"
)

ELFCLASS64 = 2
ELFDATA2LSB = 1
ET_EXEC = 2
ET_DYN = 3
EM_AARCH64 = 183
ELF_HEADER_SIZE = 64
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Verify and merge the pinned official OpenAI Codex app-server "
            "aarch64-musl binary into an already synchronized toolchain."
        )
    )
    parser.add_argument("--output", required=True, help="Synchronized toolchain root.")
    parser.add_argument("--cache-dir", default=None, help="Optional archive cache directory.")
    parser.add_argument(
        "--archive",
        default=None,
        help="Optional pre-downloaded official archive; it must match the pinned SHA256.",
    )
    parser.add_argument(
        "--license-file",
        default=None,
        help="Apache-2.0 license file to package with the binary.",
    )
    parser.add_argument("--timeout", type=int, default=30, help="Download timeout per attempt.")
    parser.add_argument("--retries", type=int, default=3, help="Download attempt count.")
    return parser.parse_args()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path, expected_sha256):
    actual = sha256_file(path)
    if actual.lower() != expected_sha256.lower():
        raise RuntimeError(
            f"SHA256 mismatch for {path}: expected {expected_sha256}, got {actual}"
        )
    return actual.lower()


def download_pinned_archive(cache_dir, timeout, retries):
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if retries <= 0:
        raise ValueError("retries must be positive")

    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / CODEX_ASSET
    if target.is_file():
        try:
            verify_sha256(target, CODEX_ARCHIVE_SHA256)
            print(f"Using verified cached Codex archive: {target}")
            return target
        except RuntimeError:
            target.unlink()

    last_error = None
    for attempt in range(1, retries + 1):
        temporary = None
        try:
            request = urllib.request.Request(
                CODEX_DOWNLOAD_URL,
                headers={
                    "Accept": "application/octet-stream",
                    "User-Agent": "murong-terminal-extension-toolchain-sync/1.7",
                },
            )
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{CODEX_ASSET}.", suffix=".tmp", dir=cache_dir
            )
            temporary = pathlib.Path(temporary_name)
            downloaded = 0
            with os.fdopen(descriptor, "wb") as output:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    while True:
                        chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            verify_sha256(temporary, CODEX_ARCHIVE_SHA256)
            os.replace(temporary, target)
            print(f"Downloaded and verified Codex archive ({downloaded} bytes): {target}")
            return target
        except Exception as error:
            last_error = error
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if isinstance(error, urllib.error.HTTPError) and error.code == 404:
                break
            if attempt < retries:
                delay = attempt * 2
                print(f"Codex download attempt {attempt} failed: {error}; retrying in {delay}s")
                time.sleep(delay)
    raise RuntimeError(
        f"Unable to download pinned Codex archive after {retries} attempt(s): {last_error}"
    ) from last_error


def validate_aarch64_elf(path):
    with open(path, "rb") as source:
        header = source.read(ELF_HEADER_SIZE)
    if len(header) < ELF_HEADER_SIZE or header[:4] != b"\x7fELF":
        raise RuntimeError(f"Codex binary is not an ELF file: {path}")
    if header[4] != ELFCLASS64:
        raise RuntimeError(f"Codex binary is not ELF64: class={header[4]}")
    if header[5] != ELFDATA2LSB:
        raise RuntimeError(f"Codex binary is not little-endian ELF: data={header[5]}")
    elf_type, machine, version = struct.unpack_from("<HHI", header, 16)
    if elf_type not in (ET_EXEC, ET_DYN):
        raise RuntimeError(f"Codex ELF is not executable/PIE: type={elf_type}")
    if machine != EM_AARCH64:
        raise RuntimeError(
            f"Codex ELF architecture mismatch: expected AArch64 ({EM_AARCH64}), got {machine}"
        )
    if version != 1:
        raise RuntimeError(f"Codex ELF has unsupported version: {version}")


def find_binary_member(archive):
    matches = [
        member
        for member in archive.getmembers()
        if member.isfile()
        and pathlib.PurePosixPath(member.name).name == CODEX_BINARY_MEMBER
    ]
    if len(matches) != 1:
        names = [member.name for member in matches]
        raise RuntimeError(
            f"Expected exactly one {CODEX_BINARY_MEMBER!r} file in {CODEX_ASSET}, "
            f"found {len(matches)}: {names}"
        )
    return matches[0]


def atomic_write_bytes(target, payload, mode=0o644):
    target = pathlib.Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def install_binary_atomically(archive_path, target):
    target = pathlib.Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = pathlib.Path(temporary_name)
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            member = find_binary_member(archive)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"Unable to read Codex binary member: {member.name}")
            output = os.fdopen(descriptor, "wb")
            descriptor = None
            with source, output:
                shutil.copyfileobj(source, output, length=DOWNLOAD_CHUNK_SIZE)
                output.flush()
                os.fsync(output.fileno())
        os.chmod(temporary, 0o755)
        validate_aarch64_elf(temporary)
        binary_sha256 = sha256_file(temporary)
        os.replace(temporary, target)
        return binary_sha256
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def update_layout_metadata(output_root):
    layout_path = pathlib.Path(output_root) / "metadata" / "toolchain-layout.json"
    if not layout_path.is_file():
        raise RuntimeError(
            "Codex must be merged into a synchronized toolchain; "
            f"missing {layout_path}"
        )
    with open(layout_path, "r", encoding="utf-8") as source:
        layout = json.load(source)
    executables = set(layout.get("executables", []))
    executables.add(str(CODEX_INSTALL_PATH))
    layout["executables"] = sorted(executables)
    payload = (json.dumps(layout, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atomic_write_bytes(layout_path, payload)


def validate_license_file(license_path):
    payload = pathlib.Path(license_path).read_bytes()
    text = payload.decode("utf-8")
    if "Apache License" not in text or "Version 2.0" not in text:
        raise RuntimeError(f"Codex license is not an Apache License 2.0 text: {license_path}")
    return payload


def merge_codex_app_server(
    output_root,
    archive_path,
    license_path,
    expected_archive_sha256=CODEX_ARCHIVE_SHA256,
):
    output_root = pathlib.Path(output_root).resolve()
    archive_path = pathlib.Path(archive_path).resolve()
    license_path = pathlib.Path(license_path).resolve()
    layout_path = output_root / "metadata" / "toolchain-layout.json"
    if not layout_path.is_file():
        raise RuntimeError(
            "Codex must be merged after sync_toolchain.py; "
            f"missing {layout_path}"
        )

    archive_sha256 = verify_sha256(archive_path, expected_archive_sha256)
    license_payload = validate_license_file(license_path)
    binary_target = output_root.joinpath(*CODEX_INSTALL_PATH.parts)
    binary_sha256 = install_binary_atomically(archive_path, binary_target)
    update_layout_metadata(output_root)
    atomic_write_bytes(
        output_root.joinpath(*CODEX_LICENSE_INSTALL_PATH.parts),
        license_payload,
    )
    metadata = {
        "name": "OpenAI Codex app-server",
        "source": "https://github.com/openai/codex",
        "tag": CODEX_TAG,
        "asset": CODEX_ASSET,
        "downloadUrl": CODEX_DOWNLOAD_URL,
        "archiveSha256": archive_sha256,
        "binarySha256": binary_sha256,
        "binaryPath": str(CODEX_INSTALL_PATH),
        "license": "Apache-2.0",
        "licensePath": str(CODEX_LICENSE_INSTALL_PATH),
    }
    metadata_payload = (
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    atomic_write_bytes(
        output_root.joinpath(*CODEX_METADATA_INSTALL_PATH.parts),
        metadata_payload,
    )
    return metadata


def main():
    args = parse_args()
    repository_root = pathlib.Path(__file__).resolve().parents[1]
    output_root = pathlib.Path(args.output).resolve()
    cache_dir = pathlib.Path(
        args.cache_dir or repository_root / "toolchain-cache" / "codex"
    ).resolve()
    license_path = pathlib.Path(
        args.license_file
        or repository_root / "third_party" / "codex-app-server" / "LICENSE"
    ).resolve()
    archive_path = (
        pathlib.Path(args.archive).resolve()
        if args.archive
        else download_pinned_archive(cache_dir, args.timeout, args.retries)
    )
    metadata = merge_codex_app_server(output_root, archive_path, license_path)
    print(
        f"Merged {metadata['name']} {metadata['tag']} into "
        f"{output_root / CODEX_INSTALL_PATH}"
    )


if __name__ == "__main__":
    main()
