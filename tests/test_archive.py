import gzip
import io
import json
import tarfile
import unittest

import fixtures  # noqa: F401  (sets sys.path for script imports)
from fixtures import record
from registry import RegistryError, check_archive, safe_entry_path

PACKAGE = {"name": "pixie-video", "version": "1.0.0", "engines": {"pixie": ">=1.0.17 <2.0.0"}, "pixie": {"plugin": {}}}


def build(entries, compress=True):
    """entries: list of (name, content_or_None, type, linkname)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for name, content, kind, link in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.linkname = link
            data = content.encode() if isinstance(content, str) else b""
            info.size = len(data) if kind == tarfile.REGTYPE else 0
            archive.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
    data = raw.getvalue()
    return io.BytesIO(gzip.compress(data) if compress else data)


def reg(name, content="x"):
    return (name, content, tarfile.REGTYPE, "")


def good(**changes):
    package = {**PACKAGE, **changes}
    return [reg("package.json", json.dumps(package)), reg("dist/plugin.js", "export {}")]


class PathTests(unittest.TestCase):
    def test_plain_relative_paths_pass(self):
        self.assertEqual(safe_entry_path("a/b.js"), "a/b.js")
        self.assertEqual(safe_entry_path("./package.json"), "package.json")

    def test_traversal_absolute_and_odd_paths_fail(self):
        for name in ("", "/a", "../a", "a/..", "a//b", "a/./b", "a\\b", "c:x", "a\0b", "x" * 1025):
            with self.assertRaises(RegistryError, msg=repr(name)):
                safe_entry_path(name)


class ArchiveTests(unittest.TestCase):
    def check(self, entries, **record_changes):
        check_archive(build(entries), record(**record_changes))

    def test_valid_archive_passes_including_dot_slash_names(self):
        self.check(good())
        self.check([reg("./package.json", json.dumps(PACKAGE)), reg("./dist/plugin.js")])

    def test_unsafe_entries_are_rejected(self):
        for entry in (
            reg("../escape.txt"),
            reg("/abs.txt"),
            ("link", None, tarfile.SYMTYPE, "/etc"),
            ("hard", None, tarfile.LNKTYPE, "package.json"),
            ("fifo", None, tarfile.FIFOTYPE, ""),
            ("dev", None, tarfile.CHRTYPE, ""),
        ):
            with self.assertRaises(RegistryError, msg=entry[0]):
                self.check(good() + [entry])

    def test_manifest_requirements(self):
        with self.assertRaisesRegex(RegistryError, "no package.json"):
            self.check([reg("nested/package.json", json.dumps(PACKAGE))])
        with self.assertRaisesRegex(RegistryError, "pixie.plugin"):
            self.check(good(pixie={}))
        with self.assertRaisesRegex(RegistryError, "version differs"):
            self.check(good(version="9.9.9"))
        with self.assertRaisesRegex(RegistryError, "engines.pixie differs"):
            self.check(good(engines={"pixie": ">=1.0.0"}))
        with self.assertRaises(RegistryError):
            self.check([reg("package.json", "{not json")])

    def test_size_and_count_bounds(self):
        import registry

        original = (registry.MAX_ENTRIES, registry.MAX_EXTRACTED_BYTES)
        try:
            registry.MAX_ENTRIES = 2
            with self.assertRaisesRegex(RegistryError, "too many"):
                self.check(good() + [reg("c.js")])
            registry.MAX_ENTRIES = original[0]
            registry.MAX_EXTRACTED_BYTES = 10
            with self.assertRaisesRegex(RegistryError, "size limit"):
                self.check(good())
        finally:
            registry.MAX_ENTRIES, registry.MAX_EXTRACTED_BYTES = original

    def test_non_gzip_and_truncated_archives_are_rejected(self):
        with self.assertRaisesRegex(RegistryError, "readable tar.gz"):
            check_archive(io.BytesIO(b"not an archive"), record())
        with self.assertRaises(RegistryError):
            check_archive(io.BytesIO(build(good()).getvalue()[:30]), record())
        with self.assertRaises(RegistryError):
            check_archive(build(good(), compress=False), record())


if __name__ == "__main__":
    unittest.main()
