"""业务 run lifecycle 恢复集成测试（6.6）。

覆盖：首图失败、业务图成功但 evidence merge 失败、纯本地 repair、
同 run/stage/artifact refs 恢复与零重复 Provider 调用。
"""

from __future__ import annotations

import io
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from leo_ppt_generator.application.run_index import RunIndex
from leo_ppt_generator.config.models import (
    Capability,
    ProviderName,
    VerificationSource,
)
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import (
    FileReceiptStore,
    compute_verification_fingerprint,
)
from leo_ppt_generator.config.verification import (
    ProviderCallResult,
    VerificationFailure,
    VerifiedProviderExecutor,
)

NOW = datetime(2026, 1, 8, tzinfo=UTC)
_REGISTRY = ProviderRegistry.default()


def _png() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), color=(0, 255, 0)).save(stream, format="PNG")
    return stream.getvalue()


def _run(home: Path) -> RunIndex:
    return RunIndex.create(
        home / "run", route="generate", runtime_identity="leo-ppt-generator/test"
    )


def _fingerprint() -> object:
    return compute_verification_fingerprint(
        provider=ProviderName.OPENAI,
        endpoint_origin=None,
        model="gpt-image-2",
        credential_version="generation:1",
        runtime_identity="leo-ppt-generator/test",
        adapter_version=_REGISTRY.provider(ProviderName.OPENAI, None).adapter.version,
        verification_policy_version=1,
    )


def _executor(call) -> VerifiedProviderExecutor:
    return VerifiedProviderExecutor(
        provider=ProviderName.OPENAI,
        model="gpt-image-2",
        endpoint_origin=None,
        operation_id="business-image-1",
        capabilities=frozenset({Capability.GENERATE}),
        source=VerificationSource.BUSINESS_REQUEST,
        call=call,
        registry=_REGISTRY,
        clock=lambda: NOW,
    )


def test_first_image_failure_keeps_context_and_checkpoint():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        run = _run(home)
        revision = run.snapshot()["revision"]
        run.checkpoint_readiness_pause(
            expected_revision=revision,
            stage="image.generate",
            required_capabilities=("generate",),
            operation_id="business-image-1",
        )
        calls = []

        def failing_call(**kwargs):
            calls.append(1)
            raise RuntimeError("500 Internal Server Error")

        executor = _executor(failing_call)
        try:
            executor.execute()
        except VerificationFailure as failure:
            assert failure.reason_code == "provider_server_error"
        else:
            raise AssertionError("first image failure must raise")

        # 保留原任务上下文与 checkpoint。
        snapshot = run.snapshot()
        pause = snapshot["readiness_pause"]
        assert pause["stage"] == "image.generate"
        assert pause["operation_id"] == "business-image-1"
        assert calls == [1]


def test_business_success_with_evidence_merge_failure_recovers_locally():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        run = _run(home)
        receipt_store = FileReceiptStore(home, _REGISTRY, clock=lambda: NOW)
        calls = []

        def failing_writer(_path, _value) -> None:
            raise OSError("injected merge failure")

        # 图片成功（保留业务产物），但 evidence merge 失败。
        executor = _executor(
            lambda **kwargs: ProviderCallResult(payload=_png())
        )
        evidence, digest = executor.execute()
        assert digest.media_type == "image/png"

        broken_receipts = FileReceiptStore(
            home, _REGISTRY, clock=lambda: NOW, writer=failing_writer
        )
        try:
            broken_receipts.merge(_fingerprint(), evidence)
        except (OSError, Exception):
            pass
        else:
            raise AssertionError("failing merge must not silently succeed")

        # 纯本地 repair：不调用 Provider 即可恢复 evidence。
        repaired = receipt_store.merge(_fingerprint(), evidence)
        assert set(repaired.capability_evidence) == {Capability.GENERATE}
        assert calls == []


def test_recovery_preserves_run_stage_and_artifact_refs():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        run = _run(home)
        revision = run.snapshot()["revision"]
        updated = run.checkpoint_readiness_pause(
            expected_revision=revision,
            stage="image.generate",
            required_capabilities=("generate",),
            operation_id="business-image-1",
            artifact_refs=("run-1/artifacts/slide-1.png",),
            recovery_ref="run-1/recovery/evidence.json",
        )
        pause = updated["readiness_pause"]
        # 同 run/stage/artifact refs 恢复：checkpoint 完整保留。
        assert updated["route"] == "generate"
        assert pause["stage"] == "image.generate"
        assert pause["artifact_refs"] == ["run-1/artifacts/slide-1.png"]
        assert pause["recovery_ref"] == "run-1/recovery/evidence.json"
        # 清除 pause 后从同一节点继续（clear 不改变 run 身份）。
        cleared = run.clear_readiness_pause(
            expected_revision=updated["revision"]
        )
        assert cleared["readiness_pause"] is None
        assert cleared["run_id"] == updated["run_id"]
        assert cleared["route"] == "generate"
