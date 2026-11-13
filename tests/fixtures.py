import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))

DIGEST = "a" * 64
URL = "https://github.com/ecnivslabs/pixie-plugins-dist/releases/download/video-1.0.0/video-1.0.0.tar.gz"
TIMESTAMP = "2026-11-01T10:00:00Z"


def record(**overrides):
    value = {
        "name": "video",
        "vers": "1.0.0",
        "engines": {"pixie": ">=1.0.17 <2.0.0"},
        "dl": URL,
        "sha256": DIGEST,
        "size": 1024,
        "published_at": TIMESTAMP,
        "yanked": False,
    }
    value.update(overrides)
    return value


def meta(**overrides):
    value = {
        "tier": "official",
        "title": "Video",
        "summary": "Generate videos from HTML compositions.",
        "keywords": ["video", "render"],
        "license": "Proprietary",
        "source": "closed",
        "relevance": {"filesRead": ["**/*.mp4"], "manifestDeps": ["hyperframes"]},
        "components": {"tools": ["video"], "skills": [], "slots": []},
    }
    value.update(overrides)
    return value


def line(value):
    return json.dumps(value, separators=(",", ":"))


def binding(repository_id=7, repository="ecnivslabs/pixie-plugins-dist"):
    return json.dumps({"repository_id": repository_id, "repository": repository})


def files(**entries):
    """A read function over an in-memory tree; missing paths read as None."""
    return lambda path: entries.get(path)
