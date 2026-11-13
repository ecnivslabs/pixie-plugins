"""Print the registry record for one GitHub release, ready to append to index/<2 chars>/<name>.

Usage: python3 tools/make_record.py <owner/repo> <tag> <archive asset name> <name> [<target>=<asset name> ...]

Reads the release through `gh api`, downloads the archive to compute its SHA-256, and copies the
engines range from the archive's package.json so the record cannot disagree with it. Each
`<target>=<asset name>` argument adds a native artifact (a separate release asset) for that platform.
"""

import hashlib
import json
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

from github_api import GitHub, HTTPSRedirects  # noqa: E402
from registry import ARCHIVE_SUFFIX, RegistryError, validate_record  # noqa: E402


def fetch(github, repository, release, asset_name):
    """The uploaded release asset with this name, plus its SHA-256 and the downloaded bytes spool."""
    asset = next((item for item in github.get(f"repos/{repository}/releases/{release['id']}/assets?per_page=100") if item["name"] == asset_name), None)
    if asset is None or asset.get("state") != "uploaded":
        raise RegistryError(f"{asset_name} is not an uploaded asset of {repository}")
    digest = hashlib.sha256()
    spool = tempfile.TemporaryFile()
    request = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "pixie-plugins-make-record"})
    with urllib.request.build_opener(HTTPSRedirects).open(request, timeout=60) as response:
        while chunk := response.read(65536):
            digest.update(chunk)
            spool.write(chunk)
    spool.seek(0)
    return asset, digest.hexdigest(), spool


def build(github, repository, tag, asset_name, name, natives=()):
    release = github.get(f"repos/{repository}/releases/tags/{tag}")
    if not asset_name.endswith(ARCHIVE_SUFFIX):
        raise RegistryError(f"the archive must be a {ARCHIVE_SUFFIX} file")
    asset, sha256, spool = fetch(github, repository, release, asset_name)
    with spool, tarfile.open(fileobj=spool, mode="r:gz") as archive:
        member = next((m for m in archive if m.name in {"package.json", "./package.json"}), None)
        if member is None:
            raise RegistryError("the archive has no package.json at its root")
        package = json.loads(archive.extractfile(member).read())
    record = {
        "name": name,
        "vers": package["version"],
        "engines": {"pixie": package["engines"]["pixie"]},
        "dl": asset["browser_download_url"],
        "sha256": sha256,
        "size": asset["size"],
        "published_at": asset["created_at"],
        "yanked": False,
    }
    if natives:
        record["native"] = {}
        for entry in natives:
            target, _, native_name = entry.partition("=")
            native, native_sha, native_spool = fetch(github, repository, release, native_name)
            native_spool.close()
            record["native"][target] = {"url": native["browser_download_url"], "sha256": native_sha, "size": native["size"]}
    validate_record(record, name)
    return record


def main(argv):
    if len(argv) < 5:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        print(json.dumps(build(GitHub(), *argv[1:5], argv[5:]), separators=(",", ":")))
    except (RegistryError, RuntimeError, KeyError, OSError, tarfile.TarError) as error:
        print(f"make_record failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
