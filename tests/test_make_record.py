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


def run(assets, data, natives=(), bodies=None):
    queue = [data, *(bodies or [])]
    with mock.patch("make_record.urllib.request.build_opener") as opener:
        opener.return_value.open.side_effect = lambda *args, **kwargs: FakeResponse(queue.pop(0))
        return make_record.build(FakeGitHub(assets), "ecnivslabs/pixie-plugins-dist", "video-1.0.0", "video-1.0.0.tar.gz", "video", natives)


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

    def test_native_artifacts_are_recorded_per_target(self):
        data = archive(self.package)
        native = b"native-bytes"
        assets = self.asset(data) + [
            {"name": "pixie-audio-linux-x64", "state": "uploaded", "size": len(native), "created_at": "2026-11-01T10:00:00Z", "browser_download_url": URL.replace("video-1.0.0.tar.gz", "pixie-audio-linux-x64")}
        ]
        record = run(assets, data, ["linux-x64=pixie-audio-linux-x64"], [native])
        self.assertEqual(list(record["native"]), ["linux-x64"])
        self.assertEqual(record["native"]["linux-x64"]["size"], len(native))
        self.assertEqual(len(record["native"]["linux-x64"]["sha256"]), 64)

    def test_unknown_native_target_or_asset_is_refused(self):
        data = archive(self.package)
        with self.assertRaises(RegistryError):
            run(self.asset(data), data, ["linux-x64=missing"], [b"x"])
        assets = self.asset(data) + [
            {"name": "n", "state": "uploaded", "size": 1, "created_at": "2026-11-01T10:00:00Z", "browser_download_url": URL.replace("video-1.0.0.tar.gz", "n")}
        ]
        with self.assertRaises(RegistryError):
            run(assets, data, ["plan9-x64=n"], [b"x"])

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
