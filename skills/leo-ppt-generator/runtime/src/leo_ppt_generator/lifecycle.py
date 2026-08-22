"""只读诊断与范围受控的临时文件清理。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from filelock import FileLock

from .application.routes import ROUTES
from .config.runtime_config import RuntimeConfigError, load_runtime_config
from .storage import atomic_write_json, canonical_json, sha256_bytes, sha256_file


class CleanupConflict(RuntimeError):
    reason_code = "cleanup_conflict"


class Lifecycle:
    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir).resolve()

    def _scoped_files(self, scope: str) -> list[Path]:
        roots = {
            "temp": self.run_dir / "tmp",
            "failed-attempts": self.run_dir / "work" / "failed-attempts",
            "input": self.run_dir / "input",
        }
        if scope not in roots:
            raise CleanupConflict("cleanup_scope_invalid")
        root = roots[scope]
        if root.is_symlink():
            raise CleanupConflict("cleanup_symlink_escape")
        if not root.exists():
            return []
        result = []
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise CleanupConflict("cleanup_symlink_escape")
            if path.is_file():
                path.resolve().relative_to(root.resolve())
                result.append(path)
        return result

    def _temporary_files(self) -> list[Path]:
        return self._scoped_files("temp")

    def _worker_units(self) -> dict[str, list[str]]:
        result = {"active": [], "failed": [], "pending": []}
        for path, collection in (
            (self.run_dir / "image-deck/slide_jobs.json", "slides"),
            (self.run_dir / "editable/page_jobs.json", "pages"),
        ):
            if not path.is_file():
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            for item in value.get(collection, []):
                identity = str(item.get("page_id") or item.get("slide_id"))
                status = item.get("status")
                if status in {"active", "dispatched", "running"}:
                    result["active"].append(identity)
                elif status in {"failed", "blocked", "timeout"}:
                    result["failed"].append(identity)
                elif status == "pending":
                    result["pending"].append(identity)
        return result

    def _event_log_status(self) -> dict:
        path = self.run_dir / "events.ndjson"
        if not path.is_file():
            return {"valid_events": 0, "tail_invalid": False, "last_seq": 0}
        valid = 0
        last_seq = 0
        tail_invalid = False
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                tail_invalid = True
                break
            sequence = event.get("seq")
            if not isinstance(sequence, int) or sequence != last_seq + 1:
                tail_invalid = True
                break
            valid += 1
            last_seq = sequence
        return {
            "valid_events": valid,
            "tail_invalid": tail_invalid,
            "last_seq": last_seq,
        }

    def _run_index_status(self) -> tuple[dict | None, dict]:
        path = self.run_dir / "run.json"
        if not path.is_file():
            return None, {"status": "failed", "reason_code": "run_index_missing"}
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None, {"status": "failed", "reason_code": "run_index_invalid"}
        if not isinstance(state, dict):
            return None, {"status": "failed", "reason_code": "run_index_invalid"}
        return state, {"status": "passed"}

    def _input_integrity(self, state: dict) -> dict:
        value = state.get("input")
        if not isinstance(value, dict) or state.get("input_available") is False:
            return {"status": "not_applicable"}
        relative = value.get("path")
        expected = value.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            return {"status": "failed", "reason_code": "run_index_invalid"}
        candidate = (self.run_dir / relative).resolve()
        try:
            candidate.relative_to(self.run_dir)
        except ValueError:
            return {"status": "failed", "reason_code": "run_symlink_forbidden"}
        if not candidate.is_file():
            return {"status": "failed", "reason_code": "input_file_missing"}
        if sha256_file(candidate) != expected:
            return {"status": "failed", "reason_code": "source_hash_mismatch"}
        return {"status": "passed", "path": relative}

    def _timing_status(self) -> dict:
        path = self.run_dir / "reports/timing.json"
        if not path.is_file():
            return {"status": "not_recorded"}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {"status": "failed", "reason_code": "timing_report_invalid"}
        if not isinstance(value, dict) or not isinstance(value.get("stages"), list):
            return {"status": "failed", "reason_code": "timing_report_invalid"}
        return {
            "status": "passed",
            "stage_count": len(value["stages"]),
            "page_count": len(value.get("pages", [])) if isinstance(value.get("pages", []), list) else 0,
            "backend_call_count": len(value.get("backend_calls", []))
            if isinstance(value.get("backend_calls", []), list)
            else 0,
        }

    def diagnose(self) -> dict:
        state, run_index = self._run_index_status()
        if state is None:
            return {
                "schema_version": 1,
                "status": "failed",
                "revision": None,
                "runtime": {"identity": None, "status": "unknown"},
                "config": {"status": "not_checked"},
                "protocol": {
                    "run_schema": "failed",
                    "route": "unknown",
                    "stage": "unknown",
                },
                "integrity": {"run_index": run_index, "input": {"status": "unknown"}},
                "workers": {"active": [], "failed": [], "pending": []},
                "operations": {},
                "temporary_files": [],
                "event_log": self._event_log_status(),
                "observability": {"timing": self._timing_status()},
                "next_action": {
                    "kind": "restore_run_index",
                    "reason_code": run_index["reason_code"],
                },
            }
        temporary = self._temporary_files()
        event_log = self._event_log_status()
        workers = self._worker_units()
        input_integrity = self._input_integrity(state)
        timing = self._timing_status()
        route = state.get("route")
        route_steps = ROUTES[route].steps if route in ROUTES else ()
        protocol = {
            "run_schema": "passed" if state.get("schema_version") == 1 else "failed",
            "route": "passed" if route in ROUTES else "failed",
            "stage": "passed"
            if state.get("stage") == "created" or state.get("stage") in route_steps
            else "failed",
        }
        try:
            config = load_runtime_config()
            config_status = {
                "status": "passed",
                "path": str(config.path),
                "sources": config.sources,
                "warnings": list(config.warnings),
            }
        except RuntimeConfigError as exc:
            config_status = {"status": "failed", "reason_code": str(exc)}
        operations = {
            operation_id: {
                "status": operation.get("status"),
                "safe_to_retry": operation.get("safe_to_retry", False),
            }
            for operation_id, operation in state.get("operations", {}).items()
        }
        if input_integrity["status"] == "failed":
            action = {
                "kind": "restore_frozen_input",
                "reason_code": input_integrity["reason_code"],
            }
        elif event_log["tail_invalid"]:
            action = {"kind": "repair_event_tail", "reason_code": "event_log_tail_invalid"}
        elif temporary:
            action = {"kind": "cleanup_preview", "reason_code": "temporary_files_present"}
        elif workers["failed"] or state.get("status") == "failed":
            action = {"kind": "retry_failed_pages", "reason_code": "failed_units_present"}
        elif workers["active"]:
            action = {"kind": "wait_completion", "reason_code": "active_workers_present"}
        elif state.get("status") in {"completed", "cancelled"}:
            action = {"kind": "none", "reason_code": "terminal_run"}
        else:
            action = {"kind": "resume", "reason_code": "checkpoint_available"}
        return {
            "schema_version": 1,
            "status": state.get("status"),
            "revision": state["revision"],
            "runtime": {
                "identity": state.get("runtime_identity"),
                "status": "passed" if state.get("runtime_identity") else "failed",
            },
            "config": config_status,
            "integrity": {"run_index": run_index, "input": input_integrity},
            "protocol": protocol,
            "workers": workers,
            "operations": operations,
            "temporary_files": [path.relative_to(self.run_dir).as_posix() for path in temporary],
            "event_log": event_log,
            "observability": {"timing": timing},
            "next_action": action,
        }

    def reset_failed_pages(self) -> dict:
        reset: list[str] = []
        specifications = (
            (self.run_dir / "image-deck/slide_jobs.json", "slides", ".slide_jobs.json.lock"),
            (self.run_dir / "editable/page_jobs.json", "pages", ".page_jobs.json.lock"),
        )
        for path, collection, lock_name in specifications:
            if not path.is_file():
                continue
            with FileLock(str(path.parent / lock_name)):
                value = json.loads(path.read_text(encoding="utf-8"))
                changed = False
                for item in value.get(collection, []):
                    if item.get("status") not in {"failed", "blocked", "timeout"}:
                        continue
                    identity = item.get("page_id") or item.get("slide_id")
                    preserved = {
                        key: item[key]
                        for key in ("page_id", "slide_id", "number", "source", "source_sha256", "notes")
                        if key in item
                    }
                    item.clear()
                    item.update({**preserved, "status": "pending"})
                    reset.append(str(identity))
                    changed = True
                if changed:
                    value["revision"] = int(value.get("revision", 0)) + 1
                    value["run_status"] = "prepared"
                    value.pop("delivery", None)
                    atomic_write_json(path, value)
        return {"reset_units": reset}

    def wait_for_workers(self, *, grace_seconds: float) -> dict:
        deadline = time.monotonic() + max(0.0, grace_seconds)
        specifications = (
            (self.run_dir / "image-deck/slide_jobs.json", "slides", ".slide_jobs.json.lock"),
            (self.run_dir / "editable/page_jobs.json", "pages", ".page_jobs.json.lock"),
        )

        def active_units() -> list[str]:
            active: list[str] = []
            for path, collection, _ in specifications:
                if not path.is_file():
                    continue
                value = json.loads(path.read_text(encoding="utf-8"))
                for item in value.get(collection, []):
                    if item.get("status") in {"active", "dispatched", "running"}:
                        active.append(str(item.get("page_id") or item.get("slide_id")))
            return active

        initially_active = active_units()
        while initially_active and time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
            initially_active = active_units()

        return {
            "grace_seconds": grace_seconds,
            "remaining_active_units": initially_active,
        }

    def cancel_worker_units(self) -> dict:
        specifications = (
            (self.run_dir / "image-deck/slide_jobs.json", "slides", ".slide_jobs.json.lock"),
            (self.run_dir / "editable/page_jobs.json", "pages", ".page_jobs.json.lock"),
        )
        cancelled: list[str] = []
        timed_out: list[str] = []
        for path, collection, lock_name in specifications:
            if not path.is_file():
                continue
            with FileLock(str(path.parent / lock_name)):
                value = json.loads(path.read_text(encoding="utf-8"))
                changed = False
                for item in value.get(collection, []):
                    identity = str(item.get("page_id") or item.get("slide_id"))
                    if item.get("status") in {"active", "dispatched", "running"}:
                        item["status"] = "timeout"
                        timed_out.append(identity)
                        changed = True
                    elif item.get("status") == "pending":
                        item["status"] = "cancelled"
                        cancelled.append(identity)
                        changed = True
                if changed:
                    value["revision"] = int(value.get("revision", 0)) + 1
                value["run_status"] = "cancelled"
                atomic_write_json(path, value)
        return {
            "timed_out_units": timed_out,
            "cancelled_units": cancelled,
        }

    def wait_and_cancel_workers(self, *, grace_seconds: float) -> dict:
        """兼容入口；需要跨 run 原子性时由调用者分开编排两个阶段。"""

        return {
            **self.wait_for_workers(grace_seconds=grace_seconds),
            **self.cancel_worker_units(),
        }

    def cleanup_preview(self, *, expected_revision: int, scope: str = "temp") -> dict:
        state = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
        if state["revision"] != expected_revision:
            raise CleanupConflict("cleanup_revision_drift")
        if self._worker_units()["active"]:
            raise CleanupConflict("cleanup_active_workers")
        if scope == "input" and state.get("status") not in {"completed", "failed", "cancelled"}:
            raise CleanupConflict("cleanup_input_requires_terminal_run")
        files = self._scoped_files(scope)
        entries = [
            {
                "category": scope,
                "path": path.relative_to(self.run_dir).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "containment": "passed",
                "retention_reason": "explicit_scope_requested",
            }
            for path in files
        ]
        paths = [entry["path"] for entry in entries]
        fingerprint = sha256_bytes(
            canonical_json(
                {"revision": expected_revision, "scope": scope, "entries": entries}
            ).encode()
        )
        preview = {
            "schema_version": 1,
            "revision": expected_revision,
            "scope": scope,
            "paths": paths,
            "entries": entries,
            "fingerprint": fingerprint,
        }
        atomic_write_json(self.run_dir / f"reports/cleanup-preview-{scope}.json", preview)
        return preview

    def cleanup_apply(self, preview: dict) -> dict:
        current = self.cleanup_preview(
            expected_revision=preview["revision"], scope=preview.get("scope", "temp")
        )
        if current["fingerprint"] != preview["fingerprint"]:
            error = CleanupConflict("cleanup_fingerprint_drift")
            error.reason_code = "cleanup_fingerprint_drift"
            raise error
        removed = []
        scope_roots = {
            "temp": self.run_dir / "tmp",
            "failed-attempts": self.run_dir / "work" / "failed-attempts",
            "input": self.run_dir / "input",
        }
        scope_root = scope_roots[current["scope"]].resolve()
        for relative in current["paths"]:
            target = (self.run_dir / relative).resolve()
            target.relative_to(scope_root)
            target.unlink()
            removed.append(relative)
        receipt = {
            "schema_version": 1,
            "scope": current["scope"],
            "removed": removed,
            "fingerprint": current["fingerprint"],
            "recoverable": False,
        }
        if current["scope"] == "input":
            state = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
            state["input_available"] = False
            state["prepare_disabled_reason"] = "input_removed"
            state["revision"] += 1
            atomic_write_json(self.run_dir / "run.json", state)
        atomic_write_json(self.run_dir / "reports/cleanup-receipt.json", receipt)
        return receipt
