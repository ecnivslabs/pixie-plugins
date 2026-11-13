import unittest
from unittest import mock

import fixtures
from fixtures import binding, meta, record
from github_api import GitHub, verify_download, verify_publication
from registry import Publication, RegistryError

REPO = {"id": 7, "full_name": "ecnivslabs/pixie-plugins-dist", "owner": {"id": 284757888, "type": "Organization"}}
AUTHOR = {"id": 106900369, "login": "vinceswu"}
ASSET = {
    "name": "video-1.0.0.tar.gz",
    "state": "uploaded",
    "size": 1024,
    "created_at": fixtures.TIMESTAMP,
    "browser_download_url": fixtures.URL,
}
OFFICIAL = {106900369, 284757888}


class FakeGitHub(GitHub):
    def __init__(self, repository=REPO, permission="write", assets=(ASSET,), draft=False):
        super().__init__()
        self.repository_data = repository
        self.permission = permission
        self.assets = list(assets)
        self.draft = draft
        self.calls = []

    def api(self, path, method="GET", data=None, ownership=False):
        self.calls.append(path)
        if path.startswith("repositories/") or path == f"repos/{self.repository_data['full_name']}":
            return self.repository_data
        if "/collaborators/" in path:
            return {"permission": self.permission, "user": {"id": AUTHOR["id"]}}
        if "/releases/tags/" in path:
            return {"id": 1, "draft": self.draft}
        if "/assets" in path:
            return self.assets
        raise AssertionError(path)


def publication(**changes):
    return Publication(record(**changes), {"repository_id": 7, "repository": REPO["full_name"]}, meta(), True, "index/vi/video")


def no_download(*args):
    return None


class VerifyPublicationTests(unittest.TestCase):
    def run_verify(self, github=None, pub=None, owners=OFFICIAL, author=AUTHOR, download=no_download):
        return verify_publication(github or FakeGitHub(), pub or publication(), author, owners, download)

    def test_valid_publication_passes(self):
        self.assertEqual(self.run_verify()["id"], 7)

    def test_download_receives_the_declared_hash_and_size(self):
        seen = []
        self.run_verify(download=lambda *args: seen.append(args))
        self.assertEqual(seen[0][1:4], (fixtures.DIGEST, 1024, 64 * 1024 * 1024))
        self.assertIsNotNone(seen[0][4], "the archive must be layout checked")

    def test_official_tier_needs_an_official_owner(self):
        with self.assertRaisesRegex(RegistryError, "official account"):
            self.run_verify(owners={1})

    def test_community_tier_does_not_need_an_official_owner(self):
        pub = Publication(record(), publication().binding, meta(tier="community", source="https://github.com/a/b"), True, "i")
        self.run_verify(pub=pub, owners={1})

    def test_author_without_write_access_is_rejected(self):
        with self.assertRaisesRegex(RegistryError, "write"):
            self.run_verify(github=FakeGitHub(permission="read"))

    def test_personal_repository_owner_needs_no_permission_lookup(self):
        repo = {**REPO, "owner": {"id": AUTHOR["id"], "type": "User"}}
        github = FakeGitHub(repository=repo)
        self.run_verify(github=github, owners={AUTHOR["id"]})
        self.assertFalse(any("/collaborators/" in call for call in github.calls))

    def test_binding_must_match_the_repository_id(self):
        pub = Publication(record(), {"repository_id": 8, "repository": REPO["full_name"]}, meta(), True, "i")
        with self.assertRaisesRegex(RegistryError, "different repository ID"):
            self.run_verify(pub=pub)

    def test_new_binding_must_use_the_canonical_name(self):
        pub = Publication(record(), {"repository_id": 7, "repository": "someone/else"}, meta(), True, "i")
        with self.assertRaisesRegex(RegistryError, "canonical"):
            self.run_verify(pub=pub)

    def test_asset_from_another_repository_is_rejected(self):
        other = fixtures.URL.replace("ecnivslabs/pixie-plugins-dist", "evil/dist")
        with self.assertRaisesRegex(RegistryError, "different repository ID"):
            self.run_verify(pub=publication(dl=other), github=FakeGitHub(repository={**REPO, "id": 9}))

    def test_missing_or_draft_release_assets_are_rejected(self):
        with self.assertRaisesRegex(RegistryError, "uploaded release asset"):
            self.run_verify(github=FakeGitHub(assets=[]))
        with self.assertRaisesRegex(RegistryError, "uploaded release asset"):
            self.run_verify(github=FakeGitHub(assets=[{**ASSET, "state": "starter"}]))
        with self.assertRaisesRegex(RegistryError, "published"):
            self.run_verify(github=FakeGitHub(draft=True))

    def test_published_at_must_match_the_asset_creation_time(self):
        with self.assertRaisesRegex(RegistryError, "published_at"):
            self.run_verify(pub=publication(published_at="2026-11-02T10:00:00Z"))

    def test_native_artifacts_are_downloaded_too(self):
        native_url = fixtures.URL.replace("video-1.0.0.tar.gz", "audio.node")
        native_asset = {**ASSET, "name": "audio.node", "browser_download_url": native_url, "size": 10}
        native = {"linux-x64": {"url": native_url, "sha256": "b" * 64, "size": 10}}
        seen = []
        self.run_verify(
            github=FakeGitHub(assets=[ASSET, native_asset]),
            pub=publication(native=native),
            download=lambda *args: seen.append((*args[1:4], args[4])),
        )
        self.assertIn(("b" * 64, 10, 256 * 1024 * 1024, None), seen)


class FakeResponse:
    def __init__(self, data):
        self.chunks = [data[i : i + 4] for i in range(0, len(data), 4)] + [b""]

    def read(self, size):
        return self.chunks.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DownloadTests(unittest.TestCase):
    def download(self, data, sha256, size, asset_size=None, limit=1000):
        import hashlib

        asset = {"size": size if asset_size is None else asset_size, "browser_download_url": fixtures.URL}
        with mock.patch("github_api.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = FakeResponse(data)
            verify_download(asset, sha256 or hashlib.sha256(data).hexdigest(), size, limit)

    def test_matching_download_passes(self):
        self.download(b"hello world", None, 11)

    def test_hash_mismatch_is_rejected(self):
        with self.assertRaisesRegex(RegistryError, "SHA-256"):
            self.download(b"hello world", "0" * 64, 11)

    def test_size_disagreements_are_rejected(self):
        with self.assertRaises(RegistryError):
            self.download(b"hello world!", None, 11)
        with self.assertRaises(RegistryError):
            self.download(b"hello", None, 11)
        with self.assertRaises(RegistryError):
            self.download(b"hello world", None, 11, asset_size=12)
        with self.assertRaises(RegistryError):
            self.download(b"x" * 2000, None, 2000, limit=1000)


if __name__ == "__main__":
    unittest.main()
