import json
import unittest

import fixtures
from fixtures import binding, files, line, meta, record
from registry import (
    RegistryError,
    engine_range,
    is_index_path,
    ownership,
    parse_json,
    publication,
    records,
    release_location,
    validate_meta,
    validate_record,
)

INDEX = "index/vi/video"
OWNER = "owners/video.json"
META = "meta/video.json"


def new_plugin(**changes):
    return {INDEX: line(record(**changes)) + "\n", OWNER: binding(), META: json.dumps(meta())}


class ParsingTests(unittest.TestCase):
    def test_duplicate_keys_and_constants_are_rejected(self):
        with self.assertRaises(RegistryError):
            parse_json('{"a":1,"a":2}')
        with self.assertRaises(RegistryError):
            parse_json('{"a":NaN}')
        with self.assertRaises(RegistryError):
            parse_json("{")

    def test_oversized_metadata_is_rejected(self):
        with self.assertRaises(RegistryError):
            parse_json('"' + "x" * (1024 * 1024) + '"')

    def test_duplicate_versions_are_rejected(self):
        with self.assertRaises(RegistryError):
            records(line(record()) + "\n" + line(record()) + "\n")

    def test_ownership_requires_numeric_repository_id(self):
        self.assertEqual(ownership(binding())["repository_id"], 7)
        for bad in ('{"repository_id":"7","repository":"a/b"}', '{"repository_id":true,"repository":"a/b"}', '{"repository_id":7}'):
            with self.assertRaises(RegistryError):
                ownership(bad)

    def test_release_urls_must_be_github_https_downloads(self):
        self.assertEqual(release_location(fixtures.URL)[1:], ("video-1.0.0", "video-1.0.0.tar.gz"))
        for bad in (
            "http://github.com/a/b/releases/download/t/f.tar.gz",
            "https://evil.example/a/b/releases/download/t/f.tar.gz",
            "https://github.com/a/b/releases/download/t/f.tar.gz?x=1",
            "https://github.com/a/b/archive/t.tar.gz",
            "https://github.com/a/b/releases/download/t",
        ):
            with self.assertRaises(RegistryError, msg=bad):
                release_location(bad)


class RecordTests(unittest.TestCase):
    def check(self, **changes):
        validate_record(record(**changes), "video")

    def test_a_complete_record_is_valid(self):
        self.check()
        self.check(vers="1.2.3-rc.1")

    def test_engine_ranges_match_the_host_grammar(self):
        for good in (">=1.0.17", "^1.2.3", ">=1.0.0 <2.0.0"):
            self.assertTrue(engine_range(good))
        for bad in ("", "garbage", ">=1", "*", ">=1.0.0 || <0.5.0", None, 3):
            self.assertFalse(engine_range(bad), bad)

    def test_invalid_fields_are_rejected(self):
        for changes in (
            {"engines": {"pixie": "garbage"}},
            {"engines": {"pixie": ">=1.0.0", "node": ">=20.0.0"}},
            {"vers": "1.0"},
            {"vers": "../1.0.0"},
            {"yanked": True},
            {"sha256": "A" * 64},
            {"sha256": "a" * 63},
            {"size": 0},
            {"size": 65 * 1024 * 1024},
            {"size": True},
            {"published_at": "2026-11-01"},
            {"dl": "https://github.com/a/b/releases/download/t/video.zip"},
            {"name": "other"},
        ):
            with self.assertRaises(RegistryError, msg=str(changes)):
                self.check(**changes)

    def test_unknown_keys_are_rejected(self):
        value = record()
        value["extra"] = 1
        with self.assertRaises(RegistryError):
            validate_record(value, "video")

    def test_native_artifacts_need_supported_targets_and_full_metadata(self):
        artifact = {"url": fixtures.URL.replace("video-1.0.0.tar.gz", "audio.node"), "sha256": fixtures.DIGEST, "size": 10}
        self.check(native={"linux-x64": artifact})
        for native in ({"plan9-x64": artifact}, {"linux-x64": {**artifact, "size": 0}}, {}, {"linux-x64": {"url": artifact["url"]}}):
            with self.assertRaises(RegistryError, msg=str(native)):
                self.check(native=native)


class MetaTests(unittest.TestCase):
    def test_valid_official_and_community_meta(self):
        validate_meta(meta(), "video")
        validate_meta(meta(tier="community", source="https://github.com/someone/tool"), "tool")

    def test_closed_source_is_official_only(self):
        with self.assertRaises(RegistryError):
            validate_meta(meta(tier="community", source="closed"), "tool")

    def test_reserved_names_are_official_only(self):
        for name in ("official", "pixie", "pixie-video", "ecnivs-kit", "ecnivslabs"):
            validate_meta(meta(), name)
            with self.assertRaises(RegistryError, msg=name):
                validate_meta(meta(tier="community", source="https://github.com/a/b"), name)

    def test_bad_shapes_are_rejected(self):
        for changes in (
            {"tier": "partner"},
            {"title": ""},
            {"summary": "x" * 281},
            {"keywords": ["k"] * 21},
            {"source": "git@github.com:a/b.git"},
            {"relevance": {"urls": ["x"]}},
            {"relevance": {"filesRead": ["a b"]}},
            {"components": {"tools": [""]}},
        ):
            with self.assertRaises(RegistryError, msg=str(changes)):
                validate_meta(meta(**changes), "video")
        with self.assertRaises(RegistryError):
            validate_meta({**meta(), "extra": 1}, "video")


class PublicationTests(unittest.TestCase):
    def test_index_paths_use_the_name_prefix(self):
        self.assertTrue(is_index_path(INDEX))
        for bad in ("index/xx/video", "index/vi/Video", "index/vi/video/extra", "owners/video.json", "index/v/v"):
            self.assertFalse(is_index_path(bad), bad)

    def test_new_plugin_requires_all_three_files(self):
        tree = new_plugin()
        result = publication(sorted(tree), files(), files(**tree))
        self.assertTrue(result.is_new)
        self.assertEqual(result.record["name"], "video")
        self.assertEqual(result.meta["tier"], "official")
        with self.assertRaises(RegistryError):
            publication([INDEX, OWNER], files(), files(**tree))

    def test_new_plugin_cannot_reuse_a_registered_name(self):
        tree = new_plugin()
        with self.assertRaises(RegistryError):
            publication(sorted(tree), files(**{OWNER: binding()}), files(**tree))

    def test_new_version_appends_one_line_and_reads_base_metadata(self):
        first = line(record()) + "\n"
        second = first + line(record(vers="1.1.0")) + "\n"
        base = files(**{INDEX: first, OWNER: binding(), META: json.dumps(meta())})
        result = publication([INDEX], base, files(**{INDEX: second}))
        self.assertFalse(result.is_new)
        self.assertEqual(result.record["vers"], "1.1.0")

    def test_existing_records_cannot_change_or_be_reordered(self):
        first = line(record()) + "\n"
        base = files(**{INDEX: first, OWNER: binding(), META: json.dumps(meta())})
        for head in (
            line(record(sha256="b" * 64)) + "\n" + line(record(vers="1.1.0")) + "\n",
            line(record(vers="1.1.0")) + "\n",
            first + line(record(vers="1.1.0")) + "\n" + line(record(vers="1.2.0")) + "\n",
            line(record(yanked=True)) + "\n" + line(record(vers="1.1.0")) + "\n",
        ):
            with self.assertRaises(RegistryError):
                publication([INDEX], base, files(**{INDEX: head}))

    def test_deleting_or_touching_other_files_is_rejected(self):
        first = line(record()) + "\n"
        base = files(**{INDEX: first, OWNER: binding(), META: json.dumps(meta())})
        with self.assertRaises(RegistryError):
            publication([INDEX], base, files())
        head = files(**{INDEX: first + line(record(vers="1.1.0")) + "\n"})
        for extra in (META, OWNER, "official-owners.json", ".github/workflows/publish.yml"):
            with self.assertRaises(RegistryError, msg=extra):
                publication([INDEX, extra], base, head)

    def test_more_than_one_plugin_per_pr_is_rejected(self):
        tree = new_plugin()
        other = {"index/ot/other": line(record(name="other")) + "\n"}
        with self.assertRaises(RegistryError):
            publication(sorted(tree) + list(other), files(), files(**tree, **other))


if __name__ == "__main__":
    unittest.main()
