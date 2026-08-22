"""U0 clean-export import、资源和领域状态隔离 characterization。"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class PageArtifact:
    schema_version: int
    page_id: str
    mode: str
    artifact_path: str
    validation_path: str


class CapabilityAdapter:
    """U0 原型：只暴露稳定能力与资源定位，不泄露 vendor 模块。"""

    def __init__(self, capability: str, skill_root: Path) -> None:
        self.capability = capability
        self._skill_root = skill_root.resolve()

    def resource(self, relative: str) -> Path:
        candidate = (self._skill_root / relative).resolve()
        candidate.relative_to(self._skill_root)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate

    def require_worker(self, page_count: int, worker_available: bool) -> str:
        if page_count > 1 and not worker_available:
            return "blocked/worker_capability_unavailable"
        return "allowed"


def office_preflight(path: Path) -> str:
    """U0 原型：主动内容或外部关系必须在 Office 解析前拒绝。"""
    with zipfile.ZipFile(path) as archive:
        names = {name.lower() for name in archive.namelist()}
        if any("vbaproject" in name or name.startswith("embeddings/") or "/embeddings/" in name for name in names):
            return "blocked/untrusted_office_input"
        for name in names:
            if not name.endswith(".rels"):
                continue
            body = archive.read(name).decode("utf-8", errors="replace").lower()
            if 'targetmode="external"' in body or "targetmode='external'" in body:
                return "blocked/untrusted_office_input"
    return "allowed"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class U0IsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        codex = os.environ.get("U0_CODEX_EXPORT")
        editable = os.environ.get("U0_EDITABLE_EXPORT")
        if not codex or not editable:
            raise unittest.SkipTest(
                "需要 U0_CODEX_EXPORT 与 U0_EDITABLE_EXPORT 指向固定 commit 的 clean export"
            )
        cls.codex_root = Path(codex).resolve()
        cls.editable_root = Path(editable).resolve()
        cls.codex_scripts = cls.codex_root / "skills/codex-ppt/scripts"
        cls.editable_skill = cls.editable_root / "skills/image-to-editable-ppt"
        cls.editable_cli = cls.editable_skill / "cli"
        for path in (cls.codex_scripts, cls.editable_cli):
            if not path.is_dir():
                raise RuntimeError(f"clean export 结构不完整：{path}")

    def test_both_capabilities_import_in_one_interpreter(self) -> None:
        codex_state = _load_module(
            "leo_u0_codex_slide_state", self.codex_scripts / "slide_run_state.py"
        )
        sys.path.insert(0, str(self.editable_cli))
        try:
            editable_cli = importlib.import_module("editppt.cli")
        finally:
            sys.path.remove(str(self.editable_cli))
        self.assertEqual(codex_state.normalize_slide_id("1"), "slide_01")
        self.assertTrue(callable(editable_cli.main))

    def test_resources_resolve_through_adapter(self) -> None:
        codex = CapabilityAdapter("image-deck", self.codex_root / "skills/codex-ppt")
        editable = CapabilityAdapter("editable", self.editable_skill)
        self.assertEqual(codex.resource("prompts/slide-worker.md").name, "slide-worker.md")
        self.assertEqual(editable.resource("prompts/page-worker.md").name, "page-worker.md")
        with self.assertRaises(ValueError):
            codex.resource("../../LICENSE")

    def test_page_artifact_hides_vendor_paths(self) -> None:
        artifact = PageArtifact(1, "page_001", "editable", "pages/page_001/page.pptx", "pages/page_001/validation.json")
        encoded = json.dumps(asdict(artifact), sort_keys=True)
        self.assertNotIn("_vendor", encoded)
        self.assertNotIn(str(self.codex_root), encoded)
        self.assertNotIn(str(self.editable_root), encoded)

    def test_domain_state_writes_remain_isolated_under_concurrency(self) -> None:
        codex_state = _load_module(
            "leo_u0_codex_concurrent_state", self.codex_scripts / "slide_run_state.py"
        )
        editable_state = _load_module(
            "leo_u0_editable_concurrent_state",
            self.editable_cli / "editppt/runtime/deck_run_state.py",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_path = root / "image-deck/slide_jobs.json"
            editable_path = root / "editable/page_jobs.json"

            def write_codex(index: int) -> None:
                codex_state.write_json(codex_path, {"domain": "image-deck", "revision": index})

            def write_editable(index: int) -> None:
                editable_state.write_json(editable_path, {"domain": "editable", "revision": index})

            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = []
                for index in range(40):
                    futures.append(pool.submit(write_codex, index))
                    futures.append(pool.submit(write_editable, index))
                for future in futures:
                    future.result()

            self.assertEqual(json.loads(codex_path.read_text())["domain"], "image-deck")
            self.assertEqual(json.loads(editable_path.read_text())["domain"], "editable")
            self.assertFalse((root / "page_jobs.json").exists())

    def test_multi_page_without_worker_is_blocked(self) -> None:
        for capability in (
            CapabilityAdapter("image-deck", self.codex_root / "skills/codex-ppt"),
            CapabilityAdapter("editable", self.editable_skill),
        ):
            self.assertEqual(
                capability.require_worker(page_count=2, worker_available=False),
                "blocked/worker_capability_unavailable",
            )
            self.assertEqual(capability.require_worker(page_count=1, worker_available=False), "allowed")

    def test_office_preflight_fails_closed_on_external_relationship(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "external.pptx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "ppt/_rels/presentation.xml.rels",
                    '<Relationships><Relationship TargetMode="External" '
                    'Target="https://example.invalid/template.potx"/></Relationships>',
                )
            self.assertEqual(office_preflight(path), "blocked/untrusted_office_input")

    @unittest.skipIf(os.name == "nt", "SIGKILL characterization 仅适用于 POSIX")
    def test_interrupted_state_write_characterization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_target = root / "codex.json"
            editable_target = root / "editable.json"
            initial = '{"revision": 1}\n'
            codex_target.write_text(initial, encoding="utf-8")
            editable_target.write_text(initial, encoding="utf-8")

            codex_code = """
import importlib.util, os, signal, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('codex_state', Path(sys.argv[1]))
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module.os.replace=lambda *_: os.kill(os.getpid(), signal.SIGKILL)
module.write_json(Path(sys.argv[2]), {'revision': 2, 'payload': 'x' * 100000})
"""
            codex = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    codex_code,
                    str(self.codex_scripts / "slide_run_state.py"),
                    str(codex_target),
                ],
                check=False,
            )
            self.assertEqual(-signal.SIGKILL, codex.returncode)
            self.assertEqual({"revision": 1}, json.loads(codex_target.read_text()))

            editable_code = """
import importlib.util, os, signal, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('editable_state', Path(sys.argv[1]))
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
def interrupted(self, body, encoding=None):
    with self.open('w', encoding=encoding) as handle:
        handle.write(body[:len(body)//2]); handle.flush()
        os.kill(os.getpid(), signal.SIGKILL)
Path.write_text=interrupted
module.write_json(Path(sys.argv[2]), {'revision': 2, 'payload': 'x' * 100000})
"""
            editable = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    editable_code,
                    str(self.editable_cli / "editppt/runtime/deck_run_state.py"),
                    str(editable_target),
                ],
                check=False,
            )
            self.assertEqual(-signal.SIGKILL, editable.returncode)
            with self.assertRaises(json.JSONDecodeError):
                json.loads(editable_target.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args, _unittest_args = parser.parse_known_args()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(U0IsolationTest)
    )
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "tests_run": result.testsRun,
                    "failures": len(result.failures),
                    "errors": len(result.errors),
                    "skipped": len(result.skipped),
                    "passed": result.wasSuccessful() and not result.skipped,
                },
                sort_keys=True,
            )
        )
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
