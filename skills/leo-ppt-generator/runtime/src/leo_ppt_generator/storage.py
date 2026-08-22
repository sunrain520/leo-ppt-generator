"""供顶层状态 owner 共用的 durable JSON 辅助函数。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_regular_file(path: str | Path, *, max_bytes: int) -> dict[str, Any]:
    """拒绝链接/设备并以流式读取返回稳定文件身份。"""
    source = Path(path)
    try:
        metadata = source.lstat()
    except FileNotFoundError as exc:
        raise ValueError("input_file_missing") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError("input_symlink_forbidden")
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("input_special_file_forbidden")
    if metadata.st_size > max_bytes:
        raise ValueError("input_too_large")
    return {
        "path": source.resolve(),
        "size": metadata.st_size,
        "sha256": sha256_file(source),
    }


def durable_copy_file(
    source: str | Path,
    target: str | Path,
    *,
    max_bytes: int,
) -> dict[str, Any]:
    """以固定内存、no-follow 源检查和 barrier 语义复制正式输入。"""
    identity = inspect_regular_file(source, max_bytes=max_bytes)
    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    digest = hashlib.sha256()
    copied = 0
    try:
        with Path(identity["path"]).open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                copied += len(chunk)
                if copied > max_bytes:
                    raise ValueError("input_too_large")
                digest.update(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        if copied != identity["size"] or digest.hexdigest() != identity["sha256"]:
            raise ValueError("input_changed_during_copy")
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        fsync_directory(destination.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"size": copied, "sha256": digest.hexdigest()}


def secure_user_tree(root: str | Path) -> None:
    """把 run 内用户内容目录收紧到当前用户，并拒绝链接。"""
    base = Path(root)
    if base.is_symlink():
        raise ValueError("run_symlink_forbidden")
    if not base.exists():
        return
    for path in [base, *sorted(base.rglob("*"))]:
        if path.is_symlink():
            raise ValueError("run_symlink_forbidden")
        if path.is_dir():
            path.chmod(0o700)
        elif path.is_file():
            path.chmod(0o600)


def fsync_file(path: str | Path) -> None:
    descriptor = os.open(Path(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_directory(path: Path) -> bool:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return False
    try:
        os.fsync(descriptor)
    except OSError:
        return False
    finally:
        os.close(descriptor)


def atomic_materialize(path: str | Path, writer, checkpoint=None) -> Path:
    """将复杂二进制产物写入临时文件后原子替换正式路径。"""
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        if checkpoint:
            checkpoint("before_write")
        writer(temporary_path)
        if checkpoint:
            checkpoint("after_write")
        fsync_file(temporary_path)
        if checkpoint:
            checkpoint("after_file_fsync")
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, destination)
        if checkpoint:
            checkpoint("after_replace")
        fsync_directory(destination.parent)
        if checkpoint:
            checkpoint("after_directory_fsync")
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination
    return True


def atomic_write_bytes(path: str | Path, body: bytes, checkpoint=None) -> None:
    checkpoint = checkpoint or (lambda _name: None)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    checkpoint("before_temp_write")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            checkpoint("after_temp_write")
            checkpoint("before_file_fsync")
            os.fsync(handle.fileno())
            checkpoint("after_file_fsync")
        checkpoint("before_replace")
        os.replace(temporary, target)
        checkpoint("after_replace")
        fsync_directory(target.parent)
        checkpoint("after_directory_fsync")
        checkpoint("after_commit")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_json(path: str | Path, value: Any, checkpoint=None) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        checkpoint=checkpoint,
    )
