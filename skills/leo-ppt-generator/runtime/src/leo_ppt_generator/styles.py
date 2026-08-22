"""可执行的内置/用户风格库合同。"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .config.runtime_config import default_home
from .storage import atomic_write_bytes, sha256_bytes


class StyleStoreError(ValueError):
    reason_code = "style_store_error"


_NAME = re.compile(r"^[\w\-\u4e00-\u9fff]{1,80}$", re.UNICODE)
_SECRET = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|secret|password|bearer\s+[a-z0-9._-]+)"
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


def _validate_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME.fullmatch(name.strip()):
        raise StyleStoreError("style_name_invalid")
    return name.strip()


def _sanitize(content: str) -> str:
    if not isinstance(content, str) or not content.strip():
        raise StyleStoreError("style_content_empty")
    if _SECRET.search(content) or _EMAIL.search(content):
        raise StyleStoreError("style_sensitive_content_forbidden")
    return content.strip() + "\n"


def user_style_path(name: str, *, home: Path | None = None) -> Path:
    return (home or default_home()) / "styles" / f"{_validate_name(name)}.md"


def builtin_style_path(name: str) -> Path:
    root = Path(__file__).resolve().parents[3] / "references/styles"
    return root / f"{_validate_name(name)}.md"


def save_style(
    name: str,
    content: str,
    *,
    home: Path | None = None,
    overwrite: bool = False,
    rename: str | None = None,
) -> dict:
    target = user_style_path(rename or name, home=home)
    if target.exists() and not overwrite:
        raise StyleStoreError("style_name_conflict")
    body = _sanitize(content).encode("utf-8")
    atomic_write_bytes(target, body)
    return {
        "name": target.stem,
        "source": "user",
        "path": str(target),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def load_style(name: str, *, home: Path | None = None) -> dict:
    user = user_style_path(name, home=home)
    path = user if user.is_file() else builtin_style_path(name)
    if not path.is_file():
        raise StyleStoreError("style_not_found")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StyleStoreError("style_unreadable") from exc
    content = _sanitize(content)
    return {
        "name": path.stem,
        "source": "user" if path == user else "builtin",
        "path": str(path),
        "content": content,
        "sha256": sha256_bytes(content.encode("utf-8")),
    }


def list_styles(*, home: Path | None = None) -> list[dict]:
    builtin_root = builtin_style_path("_placeholder").parent
    names: dict[str, dict] = {}
    for path in sorted(builtin_root.glob("*.md")):
        names[path.stem] = {"name": path.stem, "source": "builtin", "path": str(path)}
    user_root = (home or default_home()) / "styles"
    for path in sorted(user_root.glob("*.md")) if user_root.is_dir() else []:
        names[path.stem] = {"name": path.stem, "source": "user", "path": str(path)}
    return list(names.values())
