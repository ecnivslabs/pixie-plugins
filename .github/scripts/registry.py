"""Registry record parsing and publication rules.

Everything here reads data only. Pull request content is never executed, so a
hostile submission cannot run code in the validating workflow.
"""

import json
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

NAME = re.compile(r"[a-z0-9][a-z0-9-]{1,63}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
VERSION = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]{1,32})?\Z"
)
COMPARATOR = re.compile(
    r"(?:>=|<=|>|<|=|\^|~)?(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z"
)
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
GLOB = re.compile(r"[A-Za-z0-9_./*{},@+-]{1,128}\Z")
TARGETS = {
    "linux-x64",
    "linux-arm64",
    "darwin-x64",
    "darwin-arm64",
    "win32-x64",
    "win32-arm64",
}
TIERS = {"official", "community"}
RESERVED = re.compile(r"(?:official|pixie)(?:-.*)?\Z|ecnivs.*\Z")
SOURCE_PREFIX = "https://github.com/"
MAX_METADATA_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_NATIVE_BYTES = 256 * 1024 * 1024
ARCHIVE_SUFFIX = ".tar.gz"
RECORD_KEYS = {"name", "vers", "engines", "dl", "sha256", "size", "published_at", "yanked"}


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Publication:
    record: dict
    binding: dict
    meta: dict
    is_new: bool
    index_path: str


def parse_json(content):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RegistryError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise RegistryError(f"invalid JSON constant: {value}")

    if len(content.encode("utf-8")) > MAX_METADATA_BYTES:
        raise RegistryError("registry metadata exceeds 1 MiB")
    try:
        return json.loads(
            content, object_pairs_hook=unique_keys, parse_constant=invalid_constant
        )
    except json.JSONDecodeError as error:
        raise RegistryError(f"invalid JSON: {error}") from error


def records(content):
    result = []
    versions = set()
    for line in content.split("\n"):
        if not line.strip():
            continue
        record = parse_json(line)
        if not isinstance(record, dict) or not isinstance(record.get("vers"), str):
            raise RegistryError("each registry record must be an object with a version")
        if record["vers"] in versions:
            raise RegistryError("duplicate plugin version")
        versions.add(record["vers"])
        result.append(record)
    return result


def ownership(content):
    binding = parse_json(content)
    if not isinstance(binding, dict) or set(binding) != {"repository_id", "repository"}:
        raise RegistryError("ownership record requires repository_id and repository")
    if type(binding["repository_id"]) is not int or binding["repository_id"] <= 0:
        raise RegistryError("repository_id must be a positive integer")
    if not isinstance(binding["repository"], str) or not REPOSITORY.fullmatch(
        binding["repository"]
    ):
        raise RegistryError("repository must be a GitHub owner/repository name")
    return binding


def official_owner_ids(content):
    data = parse_json(content)
    ids = data.get("owner_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list) or not all(type(item) is int and item > 0 for item in ids):
        raise RegistryError("official-owners.json requires positive integer owner_ids")
    return set(ids)


def engine_range(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        return False
    return all(COMPARATOR.fullmatch(part) for part in value.strip().split())


def release_location(url):
    if not isinstance(url, str):
        raise RegistryError("release asset URL must be a string")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
    ):
        raise RegistryError("assets must use GitHub HTTPS release download URLs")
    parts = parsed.path.split("/")
    if len(parts) != 7 or parts[3:5] != ["releases", "download"]:
        raise RegistryError("invalid GitHub release asset URL")
    repository = "/".join(parts[1:3])
    if not REPOSITORY.fullmatch(repository) or not parts[5] or not parts[6]:
        raise RegistryError("invalid GitHub release asset path")
    return repository, unquote(parts[5]), unquote(parts[6])


def check_asset(item, label, limit):
    if not isinstance(item, dict) or set(item) - {"url", "sha256", "size"} or len(item) != 3:
        raise RegistryError(f"{label} requires exactly url, sha256 and size")
    if not isinstance(item["sha256"], str) or not SHA256.fullmatch(item["sha256"]):
        raise RegistryError(f"{label} sha256 must be 64 lowercase hexadecimal characters")
    if type(item["size"]) is not int or not 0 < item["size"] <= limit:
        raise RegistryError(f"{label} size is outside the allowed range")
    release_location(item["url"])


def assets(record):
    """Every downloadable artifact of a record, archive first."""
    yield {"url": record["dl"], "sha256": record["sha256"], "size": record["size"], "limit": MAX_ARCHIVE_BYTES}
    for target, artifact in (record.get("native") or {}).items():
        yield {**artifact, "limit": MAX_NATIVE_BYTES, "target": target}


def validate_record(record, name):
    keys = set(record)
    if not RECORD_KEYS <= keys <= RECORD_KEYS | {"native"}:
        raise RegistryError("record keys must be exactly the documented fields")
    if record["name"] != name:
        raise RegistryError("record name must match plugin filename")
    if not isinstance(record["vers"], str) or not VERSION.fullmatch(record["vers"]):
        raise RegistryError("invalid plugin version")
    if record["yanked"] is not False:
        raise RegistryError("new versions must not be yanked")
    engines = record["engines"]
    if not isinstance(engines, dict) or set(engines) != {"pixie"} or not engine_range(engines["pixie"]):
        raise RegistryError("engines must be {pixie: <valid range>}")
    if not isinstance(record["published_at"], str) or not TIMESTAMP.fullmatch(record["published_at"]):
        raise RegistryError("published_at must be a UTC timestamp like 2026-01-02T03:04:05Z")
    check_asset(
        {"url": record["dl"], "sha256": record["sha256"], "size": record["size"]},
        "archive",
        MAX_ARCHIVE_BYTES,
    )
    if not release_location(record["dl"])[2].endswith(ARCHIVE_SUFFIX):
        raise RegistryError(f"archive must be a {ARCHIVE_SUFFIX} file")
    native = record.get("native")
    if native is None:
        return
    if not isinstance(native, dict) or not native or not set(native) <= TARGETS:
        raise RegistryError("native must map supported targets to artifacts")
    for target, artifact in native.items():
        check_asset(artifact, f"native {target}", MAX_NATIVE_BYTES)


def string_list(value, label, limit, pattern=None, length=64):
    if not isinstance(value, list) or len(value) > limit:
        raise RegistryError(f"{label} must be a list of at most {limit} strings")
    for item in value:
        valid = isinstance(item, str) and 0 < len(item) <= length
        if not valid or (pattern and not pattern.fullmatch(item)):
            raise RegistryError(f"{label} contains an invalid entry")
    return value


def validate_meta(meta, name):
    allowed = {"tier", "title", "summary", "keywords", "license", "source", "relevance", "components"}
    if not isinstance(meta, dict) or set(meta) != allowed:
        raise RegistryError("meta requires exactly: " + ", ".join(sorted(allowed)))
    if meta["tier"] not in TIERS:
        raise RegistryError("tier must be official or community")
    for key, limit in (("title", 80), ("summary", 280), ("license", 64)):
        if not isinstance(meta[key], str) or not 0 < len(meta[key]) <= limit:
            raise RegistryError(f"{key} must be 1 to {limit} characters")
    string_list(meta["keywords"], "keywords", 20, length=32)
    source = meta["source"]
    if source == "closed":
        if meta["tier"] != "official":
            raise RegistryError("only official plugins may be closed source")
    elif not (
        isinstance(source, str)
        and source.startswith(SOURCE_PREFIX)
        and REPOSITORY.fullmatch(source[len(SOURCE_PREFIX) :])
    ):
        raise RegistryError('source must be "closed" or a https://github.com/owner/repo URL')
    signals = meta["relevance"]
    if not isinstance(signals, dict) or set(signals) - {"cwd", "filesRead", "manifestDeps"}:
        raise RegistryError("relevance supports cwd, filesRead and manifestDeps")
    for key, value in signals.items():
        string_list(value, f"relevance.{key}", 20, GLOB, 128)
    components = meta["components"]
    if not isinstance(components, dict) or set(components) - {"tools", "skills", "slots"}:
        raise RegistryError("components supports tools, skills and slots")
    for key, value in components.items():
        string_list(value, f"components.{key}", 64)
    if RESERVED.fullmatch(name) and meta["tier"] != "official":
        raise RegistryError("reserved plugin names are official only")
    return meta


def is_index_path(path):
    parts = path.split("/")
    return (
        len(parts) == 3
        and parts[0] == "index"
        and bool(NAME.fullmatch(parts[2]))
        and parts[1] == parts[2][:2]
    )


def publication(changed, read_base, read_head):
    index_paths = [path for path in changed if path.startswith("index/")]
    if len(index_paths) != 1 or not is_index_path(index_paths[0]):
        raise RegistryError("publishing PR must change exactly one plugin file at index/<2 chars>/<name>")
    path = index_paths[0]
    name = path.rsplit("/", 1)[1]
    previous = read_base(path)
    current = read_head(path)
    if current is None:
        raise RegistryError("publishing PR must not delete plugin files")
    if previous is not None and not current.startswith(previous):
        raise RegistryError("publishing PR must preserve existing registry bytes")
    base_records = records(previous or "")
    head_records = records(current)
    if len(head_records) != len(base_records) + 1 or head_records[: len(base_records)] != base_records:
        raise RegistryError("publishing PR must append one version without changing existing records")
    record = head_records[-1]
    validate_record(record, name)
    is_new = previous is None
    owner_path, meta_path = f"owners/{name}.json", f"meta/{name}.json"
    expected = {path, owner_path, meta_path} if is_new else {path}
    if set(changed) != expected:
        raise RegistryError("publishing PR contains unrelated changes or missing registration files")
    reader = read_head if is_new else read_base
    binding_text, meta_text = reader(owner_path), reader(meta_path)
    if binding_text is None or meta_text is None:
        raise RegistryError("plugin requires reviewed ownership and meta records")
    if is_new and (read_base(owner_path) is not None or read_base(meta_path) is not None):
        raise RegistryError("plugin is already registered")
    meta = validate_meta(parse_json(meta_text), name)
    return Publication(record, ownership(binding_text), meta, is_new, path)
