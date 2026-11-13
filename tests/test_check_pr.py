import json
import unittest
from unittest import mock

import fixtures  # noqa: F401  (sets sys.path for script imports)
import check_pr
from fixtures import binding, line, meta, record
from github_api import verify_publication
from registry import RegistryError
from test_github_api import ASSET, AUTHOR, OFFICIAL, REPO, FakeGitHub

BASE, HEAD = "b" * 40, "c" * 40
INDEX, OWNER, META = "index/vi/video", "owners/video.json", "meta/video.json"
FIRST = line(record()) + "\n"
SECOND = FIRST + line(record(vers="1.1.0")) + "\n"


class PullGitHub(FakeGitHub):
    def __init__(self, pr=None, **kwargs):
        super().__init__(**kwargs)
        self.pr = pr or self.pull()
        self.writes = []

    @staticmethod
    def pull(**changes):
        value = {
            "number": 5,
            "state": "open",
            "draft": False,
            "base": {"ref": "master", "sha": BASE, "repo": {"full_name": "ecnivslabs/pixie-plugins"}},
            "head": {"sha": HEAD},
            "user": AUTHOR,
        }
        value.update(changes)
        return value

    def api(self, path, method="GET", data=None, ownership=False):
        if path.startswith("repos/ecnivslabs/pixie-plugins/"):
            if method != "GET":
                self.writes.append((method, path))
                return {"merged": True} if path.endswith("/merge") else None
            return self.pr
        return super().api(path, method, data, ownership)


def run_process(github, base_tree, head_tree, changed):
    def fake_git(*args):
        if args[0] == "merge-base":
            return b"a" * 40 + b"\n"
        if args[0] == "diff":
            return "\0".join(changed).encode() + b"\0"
        return b""

    def fake_read(reference, path):
        return (base_tree if reference == BASE else head_tree).get(path)

    owners = {"official-owners.json": json.dumps({"owner_ids": sorted(OFFICIAL)})}
    base_tree = {**base_tree, **owners}
    event = {"number": 5, "pull_request": {"head": {"sha": HEAD}}}
    with (
        mock.patch.object(check_pr, "git", fake_git),
        mock.patch.object(check_pr, "read_blob", fake_read),
        mock.patch.object(check_pr, "verify_publication", offline_verify),
    ):
        check_pr.process(github, event, "ecnivslabs/pixie-plugins")


def offline_verify(github, candidate, author, owners):
    return verify_publication(github, candidate, author, owners, lambda *args: None)


class ProcessTests(unittest.TestCase):
    existing = {INDEX: FIRST, OWNER: binding(), META: json.dumps(meta())}

    def test_new_version_of_a_registered_plugin_is_merged_and_published(self):
        github = PullGitHub()
        run_process(github, self.existing, {INDEX: SECOND}, [INDEX])
        self.assertEqual(
            github.writes,
            [
                ("PUT", "repos/ecnivslabs/pixie-plugins/pulls/5/merge"),
                ("POST", "repos/ecnivslabs/pixie-plugins/actions/workflows/publish.yml/dispatches"),
            ],
        )

    def test_new_plugin_is_labeled_for_manual_review_and_not_merged(self):
        github = PullGitHub()
        head = {INDEX: FIRST, OWNER: binding(), META: json.dumps(meta())}
        run_process(github, {}, head, [INDEX, OWNER, META])
        self.assertEqual(github.writes, [("POST", "repos/ecnivslabs/pixie-plugins/issues/5/labels")])

    def test_administrative_changes_are_left_to_maintainers(self):
        github = PullGitHub()
        run_process(github, self.existing, self.existing, ["official-owners.json"])
        self.assertEqual(github.writes, [])

    def test_invalid_publication_is_refused_without_writes(self):
        github = PullGitHub()
        bad = FIRST.replace('"size":1024', '"size":1025') + line(record(vers="1.1.0")) + "\n"
        with self.assertRaises(RegistryError):
            run_process(github, self.existing, {INDEX: bad}, [INDEX])
        self.assertEqual(github.writes, [])

    def test_failed_ownership_check_prevents_merge(self):
        github = PullGitHub(permission="read")
        with self.assertRaises(RegistryError):
            run_process(github, self.existing, {INDEX: SECOND}, [INDEX])
        self.assertEqual(github.writes, [])


class IdentityTests(unittest.TestCase):
    def check(self, **changes):
        pr = PullGitHub.pull(**changes)
        check_pr.validate_identity(pr, "ecnivslabs/pixie-plugins", 5, HEAD)

    def test_ready_pull_request_passes(self):
        self.check()

    def test_unsafe_pull_requests_are_rejected(self):
        for changes in (
            {"draft": True},
            {"state": "closed"},
            {"number": 6},
            {"head": {"sha": "d" * 40}},
            {"head": {"sha": "xyz"}},
            {"base": {"ref": "dev", "sha": BASE, "repo": {"full_name": "ecnivslabs/pixie-plugins"}}},
            {"base": {"ref": "master", "sha": BASE, "repo": {"full_name": "fork/pixie-plugins"}}},
            {"user": {"id": "1", "login": "x"}},
        ):
            with self.assertRaises(RegistryError, msg=str(changes)):
                self.check(**changes)


if __name__ == "__main__":
    unittest.main()
