"""多进程 single-flight 集成测试：同一 Verification_Scope 只产生一个在途请求。"""

from __future__ import annotations

import multiprocessing
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from leo_ppt_generator.config.models import (
    Capability,
    ProviderName,
    VerificationScope,
)
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import compute_verification_fingerprint
from leo_ppt_generator.config.verification_operations import (
    FileVerificationCoordinator,
    VerificationIntent,
)

NOW = datetime(2026, 1, 8, tzinfo=UTC)
PROVIDER_DELAY_SECONDS = 1.5


def _scope() -> VerificationScope:
    fingerprint = compute_verification_fingerprint(
        provider=ProviderName.OPENAI,
        endpoint_origin=None,
        model="gpt-image-2",
        credential_version="generation:1",
        runtime_identity="leo-ppt-generator/test",
        adapter_version="openai/v1",
        verification_policy_version=1,
    )
    return VerificationScope(
        fingerprint=fingerprint,
        required_capabilities=frozenset({Capability.GENERATE}),
    )


def _worker(home: str, operation_id: str, barrier, queue) -> None:
    """每个进程尝试执行同一 scope；只有 owner 实际调用 provider。"""

    registry = ProviderRegistry.default()
    coordinator = FileVerificationCoordinator(home, registry, clock=lambda: NOW)
    scope = _scope()
    intent = VerificationIntent(
        operation_id=operation_id,
        intent_id=f"intent-{operation_id}",
        provider=ProviderName.OPENAI,
        capabilities=frozenset({Capability.GENERATE}),
        request_identity="run-1/page-1",
    )
    barrier.wait()
    calls: list[int] = []

    def provider_executor():
        calls.append(1)
        time.sleep(PROVIDER_DELAY_SECONDS)  # 保持 owner 在途，暴露并发窗口
        return {Capability.GENERATE: {"ok": True}}

    terminal, evidence = coordinator.execute(scope, intent, provider_executor)
    queue.put(
        {
            "operation_id": terminal.operation_id,
            "called": len(calls),
            "evidence": evidence is not None,
            "state": terminal.state,
        }
    )


def test_multiprocess_single_flight_has_one_inflight_request():
    with tempfile.TemporaryDirectory() as directory:
        queue = multiprocessing.Queue()
        barrier = multiprocessing.Barrier(3)
        workers = [
            multiprocessing.Process(
                target=_worker,
                args=(directory, f"op-{index}", barrier, queue),
            )
            for index in range(3)
        ]
        for worker in workers:
            worker.start()
        results = [queue.get(timeout=30) for _ in workers]
        for worker in workers:
            worker.join(timeout=10)

        assert len(results) == 3
        # 只有 owner 调用 provider；其余共享同一 owner 结果且不产生付费调用。
        owners = [item for item in results if item["called"] == 1]
        assert len(owners) == 1
        owner_id = owners[0]["operation_id"]
        assert sum(item["called"] for item in results) == 1
        for item in results:
            assert item["operation_id"] == owner_id
            if item["called"] == 1:
                assert item["state"] == "succeeded"
                assert item["evidence"] is True
            else:
                # joiner 不产生付费调用；结果由 owner 完成后共享。
                assert item["evidence"] is False
