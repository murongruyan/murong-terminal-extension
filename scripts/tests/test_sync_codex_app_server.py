import hashlib
import io
import json
import os
import pathlib
import struct
import sys
import tarfile
import tempfile
import unittest


SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import sync_codex_app_server as codex_sync


def make_elf(machine=codex_sync.EM_AARCH64, elf_type=codex_sync.ET_DYN):
    header = bytearray(codex_sync.ELF_HEADER_SIZE)
    header[:4] = b"\x7fELF"
    header[4] = codex_sync.ELFCLASS64
    header[5] = codex_sync.ELFDATA2LSB
    header[6] = 1
    struct.pack_into("<HHI", header, 16, elf_type, machine, 1)
    return bytes(header) + b"test-codex-app-server"


class SyncCodexAppServerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.output = self.root / "toolchain"
        (self.output / "metadata").mkdir(parents=True)
        (self.output / "metadata" / "toolchain-layout.json").write_text(
            json.dumps({"symlinks": [], "executables": ["bin/bash"]}),
            encoding="utf-8",
        )
        self.license = self.root / "LICENSE"
        self.license.write_text(
            "Apache License\nVersion 2.0, January 2004\nhttp://www.apache.org/licenses/\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def make_archive(self, binary, member_name=codex_sync.CODEX_BINARY_MEMBER):
        archive_path = self.root / codex_sync.CODEX_ASSET
        with tarfile.open(archive_path, "w:gz") as archive:
            info = tarfile.TarInfo(f"release/{member_name}")
            info.size = len(binary)
            info.mode = 0o755
            info.mtime = 0
            archive.addfile(info, io.BytesIO(binary))
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        return archive_path, digest

    def test_merge_installs_verified_binary_licenseAndMetadata(self):
        binary = make_elf()
        archive, archive_sha256 = self.make_archive(binary)

        metadata = codex_sync.merge_codex_app_server(
            self.output,
            archive,
            self.license,
            expected_archive_sha256=archive_sha256,
        )

        installed = self.output / "bin" / "codex-app-server"
        self.assertEqual(binary, installed.read_bytes())
        if os.name != "nt":
            self.assertTrue(os.stat(installed).st_mode & 0o111)
        layout = json.loads(
            (self.output / "metadata" / "toolchain-layout.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("bin/codex-app-server", layout["executables"])
        self.assertEqual(codex_sync.CODEX_TAG, metadata["tag"])
        self.assertEqual(archive_sha256, metadata["archiveSha256"])
        self.assertTrue(
            (self.output / "share" / "LICENSES" / "codex-app-server" / "LICENSE").is_file()
        )
        packaged_metadata = json.loads(
            (self.output / "metadata" / "codex-app-server.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("bin/codex-app-server", packaged_metadata["binaryPath"])
        self.assertEqual("Apache-2.0", packaged_metadata["license"])

    def test_wrongArchitectureDoesNotReplaceExistingBinary(self):
        existing = self.output / "bin" / "codex-app-server"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"existing-good-binary")
        archive, archive_sha256 = self.make_archive(make_elf(machine=62))

        with self.assertRaisesRegex(RuntimeError, "architecture mismatch"):
            codex_sync.merge_codex_app_server(
                self.output,
                archive,
                self.license,
                expected_archive_sha256=archive_sha256,
            )

        self.assertEqual(b"existing-good-binary", existing.read_bytes())

    def test_archiveChecksumMismatchStopsBeforeReplacement(self):
        existing = self.output / "bin" / "codex-app-server"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"existing-good-binary")
        archive, _ = self.make_archive(make_elf())

        with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
            codex_sync.merge_codex_app_server(
                self.output,
                archive,
                self.license,
                expected_archive_sha256="0" * 64,
            )

        self.assertEqual(b"existing-good-binary", existing.read_bytes())

    def test_archiveRequiresExactPinnedBinaryMember(self):
        archive, archive_sha256 = self.make_archive(
            make_elf(), member_name="unexpected-app-server"
        )

        with self.assertRaisesRegex(RuntimeError, "Expected exactly one"):
            codex_sync.merge_codex_app_server(
                self.output,
                archive,
                self.license,
                expected_archive_sha256=archive_sha256,
            )


if __name__ == "__main__":
    unittest.main()
