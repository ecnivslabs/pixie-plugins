"""GitHub lookups that tie a publication to its source repository.

Ownership follows the numeric repository ID, so renaming or transferring a
repository keeps its plugins and recreating an old URL does not acquire them.
"""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from urllib.parse import quote, urlsplit

from registry import REPOSITORY, RegistryError, assets, check_archive, release_location

TOKEN_VARIABLE = "REGISTRY_OWNERSHIP_TOKEN"


class GitHub:
    def __init__(self):
        self.cache = {}

    def api(self, path, method="GET", data=None, ownership=False):
        environment = dict(os.environ)
        token = os.environ.get(TOKEN_VARIABLE) if ownership else None
        if token:
            environment["GH_TOKEN"] = token
        command = ["gh", "api", "--method", method, path]
        if data is not None:
            command.extend(["--input", "-"])
        result = subprocess.run(
            command,
            input=json.dumps(data) if data is not None else None,
            capture_output=True,
            text=True,
            env=environment,
            timeout=60,
            check=False,
        )
        if result.returncode:
            status = re.search(r"HTTP [0-9]{3}", result.stderr)
            detail = status.group() if status else f"exit status {result.returncode}"
            raise RuntimeError(f"GitHub API failed ({detail}): {method} {path}")
        return json.loads(result.stdout) if result.stdout.strip() else None

    def get(self, path):
        if path not in self.cache:
            self.cache[path] = self.api(path)
        return self.cache[path]

    def repository(self, path, fresh=False):
        repository = self.api(path) if fresh else self.get(path)
        if not isinstance(repository, dict) or type(repository.get("id")) is not int:
            raise RegistryError("GitHub returned invalid repository metadata")
        name = repository.get("full_name")
        if not isinstance(name, str) or not REPOSITORY.fullmatch(name):
            raise RegistryError("GitHub returned invalid repository name")
        owner = repository.get("owner")
        if not isinstance(owner, dict) or type(owner.get("id")) is not int:
            raise RegistryError("GitHub returned invalid repository owner")
        return repository

    def authorize(self, repository, author):
        owner = repository["owner"]
        if owner.get("type") == "User" and owner["id"] == author["id"]:
            return
        path = f"repos/{repository['full_name']}/collaborators/{quote(author['login'], safe='')}/permission"
        try:
            permission = self.api(path, ownership=True)
        except RuntimeError as error:
            raise RuntimeError(
                f"Cannot verify source repository permissions. Configure {TOKEN_VARIABLE} "
                f"with read access to repository collaborators. Automatic publishing is blocked. {error}"
            ) from error
        if not isinstance(permission, dict) or permission.get("permission") not in {"write", "admin"}:
            raise RegistryError("PR author must have write, maintain, or admin access to the source repository")
        if permission.get("user", {}).get("id") != author["id"]:
            raise RegistryError("GitHub permission response does not match PR author's account ID")

    def release_asset(self, url, repository_id):
        source, tag, filename = release_location(url)
        repository = self.repository(f"repos/{source}")
        if repository["id"] != repository_id:
            raise RegistryError("release asset belongs to a different repository ID")
        canonical = repository["full_name"]
        release = self.get(f"repos/{canonical}/releases/tags/{quote(tag, safe='')}")
        if not isinstance(release, dict) or type(release.get("id")) is not int or release.get("draft"):
            raise RegistryError("release must be published in the registered repository")
        for page in range(1, 101):
            entries = self.get(f"repos/{canonical}/releases/{release['id']}/assets?per_page=100&page={page}")
            if not isinstance(entries, list):
                raise RegistryError("GitHub returned invalid release assets")
            for asset in entries:
                if asset.get("name") == filename and asset.get("state") == "uploaded":
                    found = release_location(asset.get("browser_download_url"))
                    if (found[0].lower(), found[1], found[2]) != (canonical.lower(), tag, filename):
                        raise RegistryError("release asset URL does not match registered repository")
                    return asset
            if len(entries) < 100:
                break
        raise RegistryError("download URL does not identify an uploaded release asset")


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        if urlsplit(new_url).scheme != "https":
            raise RegistryError("release asset redirected outside HTTPS")
        return super().redirect_request(request, fp, code, message, headers, new_url)


def verify_download(asset, sha256, size, limit, check=None):
    """Download an asset, verify size and SHA-256, and run `check` on the verified bytes."""
    if type(asset.get("size")) is not int or asset["size"] != size or size > limit:
        raise RegistryError("release asset size does not match the record or exceeds the limit")
    digest = hashlib.sha256()
    downloaded = 0
    request = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "pixie-plugins-registry"})
    with tempfile.TemporaryFile() as spool:
        with urllib.request.build_opener(HTTPSRedirects).open(request, timeout=60) as response:
            while chunk := response.read(65536):
                downloaded += len(chunk)
                if downloaded > size:
                    raise RegistryError("release asset exceeds declared size")
                digest.update(chunk)
                spool.write(chunk)
        if downloaded != size or digest.hexdigest() != sha256:
            raise RegistryError("release asset size or SHA-256 mismatch")
        if check is not None:
            spool.seek(0)
            check(spool)


def verify_publication(github, publication, author, official_owners, download=verify_download):
    repository_id = publication.binding["repository_id"]
    repository = github.repository(f"repositories/{repository_id}")
    if repository["id"] != repository_id:
        raise RegistryError("GitHub returned a different repository ID")
    if publication.is_new and publication.binding["repository"].lower() != repository["full_name"].lower():
        raise RegistryError("new ownership record must use canonical repository name")
    if publication.meta["tier"] == "official" and repository["owner"]["id"] not in official_owners:
        raise RegistryError("official plugins must be owned by an official account")
    github.authorize(repository, author)
    checked = set()
    for artifact in assets(publication.record):
        key = (artifact["url"], artifact["sha256"])
        if key in checked:
            continue
        asset = github.release_asset(artifact["url"], repository_id)
        if artifact.get("target") is None and asset.get("created_at") != publication.record["published_at"]:
            raise RegistryError("published_at must equal the release asset creation time")
        check = None
        if artifact.get("target") is None:
            record = publication.record
            check = lambda spool, record=record: check_archive(spool, record)
        download(asset, artifact["sha256"], artifact["size"], artifact["limit"], check)
        checked.add(key)
    repository = github.repository(f"repositories/{repository_id}", fresh=True)
    if repository["id"] != repository_id:
        raise RegistryError("repository identity changed during asset verification")
    github.authorize(repository, author)
    return repository
