import io
import json
import sys
import tarfile
import unittest
from pathlib import Path
from unittest import mock

import fixtures  # noqa: F401  (sets sys.path for script imports)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import make_record  # noqa: E402
from registry import RegistryError  # noqa: E402

URL = "https://github.com/ecnivslabs/pixie-plugins-dist/releases/download/video-1.0.0/video-1.0.0.tar.gz"


def archive(package):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tar:
        data = json.dumps(package).encode()
        info = tarfile.TarInfo("package.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return raw.getvalue()


class FakeGitHub:
    def __init__(self, assets):
        self.assets = assets

    def get(self, path):
        return {"id": 1} if "/releases/tags/" in path else self.assets


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def run(assets, data):
    with mock.patch("make_record.urllib.request.build_opener") as opener:
        opener.return_value.open.return_value = FakeResponse(data)
        return make_record.build(FakeGitHub(assets), "ecnivslabs/pixie-plugins-dist", "video-1.0.0", "video-1.0.0.tar.gz", "video")


class MakeRecordTests(unittest.TestCase):
    package = {"name": "pixie-video", "version": "1.0.0", "engines": {"pixie": ">=1.0.17 <2.0.0"}, "pixie": {"plugin": {}}}

    def asset(self, data, **changes):
        return [{"name": "video-1.0.0.tar.gz", "state": "uploaded", "size": len(data), "created_at": "2026-11-01T10:00:00Z", "browser_download_url": URL, **changes}]

    def test_builds_a_valid_record_from_the_release_and_archive(self):
        data = archive(self.package)
        record = run(self.asset(data), data)
        self.assertEqual(record["vers"], "1.0.0")
        self.assertEqual(record["engines"], {"pixie": ">=1.0.17 <2.0.0"})
        self.assertEqual(record["size"], len(data))
        self.assertEqual(len(record["sha256"]), 64)
        self.assertEqual(record["published_at"], "2026-11-01T10:00:00Z")

    def test_missing_or_unfinished_assets_are_refused(self):
        data = archive(self.package)
        with self.assertRaises(RegistryError):
            run([], data)
        with self.assertRaises(RegistryError):
            run(self.asset(data, state="starter"), data)

    def test_archive_without_a_root_manifest_is_refused(self):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:gz") as tar:
            info = tarfile.TarInfo("other.txt")
            tar.addfile(info, io.BytesIO(b""))
        with self.assertRaises(RegistryError):
            run(self.asset(raw.getvalue()), raw.getvalue())


if __name__ == "__main__":
    unittest.main()
