"""Build the signed-index payload from the repository tree.

Output is a single JSON document. The publish workflow signs its exact bytes,
so clients verify what they download without any canonicalization step.
"""

import datetime
import json
import sys
from pathlib import Path

from registry import (
    NAME,
    RegistryError,
    ownership,
    parse_json,
    records,
    validate_meta,
    validate_record,
)

SCHEMA_VERSION = 1
LIFETIME = datetime.timedelta(days=7)


def timestamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def blocklist(root):
    entries = parse_json((root / "blocklist.json").read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise RegistryError("blocklist.json must be a list")
    for entry in entries:
        valid = (
            isinstance(entry, dict)
            and set(entry) == {"name", "vers", "reason"}
            and isinstance(entry["name"], str)
            and NAME.fullmatch(entry["name"])
            and isinstance(entry["vers"], str)
            and isinstance(entry["reason"], str)
            and 0 < len(entry["reason"]) <= 280
        )
        if not valid:
            raise RegistryError("blocklist entries require name, vers and reason")
    return entries


def build(root, now):
    plugins = {}
    for path in sorted((root / "index").glob("*/*")):
        name = path.name
        if not NAME.fullmatch(name) or path.parent.name != name[:2]:
            raise RegistryError(f"misplaced index file: {path}")
        versions = records(path.read_text(encoding="utf-8"))
        if not versions:
            raise RegistryError(f"empty index file: {path}")
        for record in versions:
            validate_published(record, name)
        meta_path, owner_path = root / "meta" / f"{name}.json", root / "owners" / f"{name}.json"
        if not meta_path.is_file() or not owner_path.is_file():
            raise RegistryError(f"{name} lacks meta or ownership records")
        meta = validate_meta(parse_json(meta_path.read_text(encoding="utf-8")), name)
        ownership(owner_path.read_text(encoding="utf-8"))
        plugins[name] = {"meta": meta, "versions": versions}
    return {
        "schemaVersion": SCHEMA_VERSION,
        "version": int(now.timestamp()),
        "generatedAt": timestamp(now),
        "expires": timestamp(now + LIFETIME),
        "blocklist": blocklist(root),
        "plugins": plugins,
    }


def validate_published(record, name):
    """Published records may be yanked later; every other rule is unchanged."""
    if type(record.get("yanked")) is not bool:
        raise RegistryError("yanked must be a boolean")
    validate_record({**record, "yanked": False}, name)


def main(root, output):
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    document = build(root, now)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Indexed {len(document['plugins'])} plugin(s), version {document['version']}")


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]), Path(sys.argv[2]))
    except (ValueError, OSError) as error:
        print(f"Index build failed: {error}", file=sys.stderr)
        sys.exit(1)
