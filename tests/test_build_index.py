import datetime
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import fixtures  # noqa: F401  (sets sys.path for script imports)
from build_index import build
from fixtures import binding, line, meta, record
from registry import RegistryError

NOW = datetime.datetime(2026, 11, 13, 12, 0, 0, tzinfo=datetime.timezone.utc)


class Tree(tempfile.TemporaryDirectory):
    def __init__(self):
        super().__init__()
        self.root = Path(self.name)
        for folder in ("index/vi", "meta", "owners"):
            (self.root / folder).mkdir(parents=True)
        self.write("blocklist.json", "[]")

    def __enter__(self):
        return self

    def write(self, relative, content):
        (self.root / relative).write_text(content, encoding="utf-8")

    def plugin(self, records=None, plugin_meta=None):
        self.write("index/vi/video", "".join(line(item) + "\n" for item in (records or [record()])))
        self.write("meta/video.json", json.dumps(plugin_meta or meta()))
        self.write("owners/video.json", binding())


class BuildTests(unittest.TestCase):
    def test_document_lists_versions_meta_and_validity_window(self):
        with Tree() as tree:
            tree.plugin([record(), record(vers="1.1.0", yanked=True)])
            document = build(tree.root, NOW)
        self.assertEqual(document["schemaVersion"], 1)
        self.assertEqual(document["version"], int(NOW.timestamp()))
        self.assertEqual(document["generatedAt"], "2026-11-13T12:00:00Z")
        self.assertEqual(document["expires"], "2026-11-20T12:00:00Z")
        self.assertEqual([item["vers"] for item in document["plugins"]["video"]["versions"]], ["1.0.0", "1.1.0"])
        self.assertTrue(document["plugins"]["video"]["versions"][1]["yanked"])
        self.assertEqual(document["plugins"]["video"]["meta"]["tier"], "official")

    def test_version_grows_with_time_so_clients_can_refuse_rollback(self):
        with Tree() as tree:
            first = build(tree.root, NOW)["version"]
            later = build(tree.root, NOW + datetime.timedelta(seconds=1))["version"]
        self.assertLess(first, later)

    def test_blocklist_is_included_and_validated(self):
        entry = {"name": "video", "vers": "1.0.0", "reason": "Crashes on startup"}
        with Tree() as tree:
            tree.write("blocklist.json", json.dumps([entry]))
            self.assertEqual(build(tree.root, NOW)["blocklist"], [entry])
            tree.write("blocklist.json", json.dumps([{"name": "video"}]))
            with self.assertRaises(RegistryError):
                build(tree.root, NOW)

    def test_a_tampered_tree_fails_the_build_instead_of_being_skipped(self):
        cases = {
            "invalid record": lambda t: t.plugin([record(sha256="nothex")]),
            "missing meta": lambda t: (t.plugin(), (t.root / "meta/video.json").unlink()),
            "missing owner": lambda t: (t.plugin(), (t.root / "owners/video.json").unlink()),
            "bad meta": lambda t: t.plugin(plugin_meta=meta(tier="partner")),
            "misplaced file": lambda t: t.write("index/vi/video-extra-wrong", line(record()) + "\n"),
            "empty file": lambda t: t.write("index/vi/video", "\n"),
            "non boolean yanked": lambda t: t.plugin([record(yanked="no")]),
        }
        for label, mutate in cases.items():
            with self.subTest(label), Tree() as tree:
                mutate(tree)
                with self.assertRaises(RegistryError):
                    build(tree.root, NOW)


@unittest.skipUnless(shutil.which("openssl"), "openssl is required for the signing round trip")
class SigningTests(unittest.TestCase):
    """The workflow signs index.json bytes with openssl; Pixie verifies them with Ed25519."""

    def run_openssl(self, *args):
        return subprocess.run(["openssl", *args], check=False, capture_output=True)

    def test_signature_verifies_and_breaks_on_any_change(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            key, public = work / "key.pem", work / "pub.pem"
            self.assertEqual(self.run_openssl("genpkey", "-algorithm", "ed25519", "-out", str(key)).returncode, 0)
            self.run_openssl("pkey", "-in", str(key), "-pubout", "-out", str(public))
            document = work / "index.json"
            document.write_text('{"version":1}\n')
            signature = work / "index.json.sig"
            sign = self.run_openssl("pkeyutl", "-sign", "-inkey", str(key), "-rawin", "-in", str(document), "-out", str(signature))
            self.assertEqual(sign.returncode, 0, sign.stderr)

            def verify():
                return self.run_openssl("pkeyutl", "-verify", "-pubin", "-inkey", str(public), "-rawin", "-in", str(document), "-sigfile", str(signature)).returncode

            self.assertEqual(verify(), 0)
            document.write_text('{"version":2}\n')
            self.assertNotEqual(verify(), 0)


if __name__ == "__main__":
    unittest.main()
