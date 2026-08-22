"""全离线端到端配置与任务恢复 journeys（14.2）。

覆盖：安装后 config status → 配置 env 凭据 → configured_unverified →
Host guard 惰性验证放行 → 首图成功合并 evidence → ready → 复查恢复。
全部使用 fake/本地实现，零真实 Provider 调用。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from leo_ppt_generator.config.host_guard import HostProbe, HostReadinessGuard
from leo_ppt_generator.config.models import (
    Capability,
    ConfigStatus,
    HostCapabilityState,
    ProviderName,
    VerificationSource,
)
from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import FileReceiptStore
from leo_ppt_generator.config.runtime_config import ConfigStore
from leo_ppt_generator.config.service import ConfigService, StatusRequest
from leo_ppt_generator.config.verification import (
    ProviderCallResult,
    VerifiedProviderExecutor,
)

NOW = datetime(2026, 1, 8, tzinfo=UTC)
REQUIRED = frozenset({Capability.GENERATE})


class EnvStore:
    def __init__(self, environ: dict[str, str]) -> None:
        self.environ = environ

    def status(self, provider: str) -> dict:
        from leo_ppt_generator.credentials import PROVIDERS

        env_name = PROVIDERS[provider]
        if self.environ.get(env_name):
            return {
                "status": "available",
                "reason_code": "credential_store_available",
                "provider": provider,
                "reference_type": "environment-reference",
                "credential_ref": f"env:{env_name}",
                "credential_version": "hmac-sha256:unresolved",
            }
        return {
            "status": "missing",
            "reason_code": "credential_missing",
            "provider": provider,
            "reference_type": "none",
            "credential_ref": None,
        }

    def reference(self, provider: str) -> str:
        return f"env:{provider}"

    def read(self, provider: str) -> str:
        raise AssertionError("不得读取 secret")

    def write(self, provider: str, secret) -> None:
        raise AssertionError("不得写入")

    def remove(self, provider: str) -> bool:
        return False

    def fingerprint_key(self, create: bool = False):
        return None


def _configured_service(home: Path) -> ConfigService:
    store = ConfigStore(home)
    store.compare_and_swap(
        None,
        {
            "schema_version": 1,
            "selected_provider": "openai",
            "provider_profiles": {
                "openai": {
                    "model": "gpt-image-2",
                    "credential_source": "environment-reference",
                    "credential_ref": "env:OPENAI_API_KEY",
                }
            },
        },
    )
    registry = ProviderRegistry.default()
    return ConfigService(
        store,
        EnvStore({"OPENAI_API_KEY": "sk-journey"}),
        registry,
        FileReceiptStore(home, registry, clock=lambda: NOW),
        clock=lambda: NOW,
        cli_path="/usr/local/bin/leo-ppt",
    )


def test_journey_from_unverified_to_ready_via_first_business_image():
    """首图惰性验证闭环：configured_unverified → ready。"""
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        service = _configured_service(home)
        guard = HostReadinessGuard(cli_path="/usr/local/bin/leo-ppt")

        # 1. 安装后：configured_unverified，guard 放行惰性验证。
        report = service.status(StatusRequest())
        assert report.status is ConfigStatus.CONFIGURED_UNVERIFIED
        decision = guard.evaluate(
            report_status=report.status,
            required_capabilities=REQUIRED,
            host=HostProbe(HostCapabilityState.UNKNOWN),
        )
        assert decision.action == "continue"
        assert decision.lazy_verification is True

        # 2. 首张业务图片成功：合并 evidence，scope 升级 ready。
        registry = ProviderRegistry.default()
        executor = VerifiedProviderExecutor(
            provider=ProviderName.OPENAI,
            model="gpt-image-2",
            endpoint_origin=None,
            operation_id="business-1",
            capabilities=REQUIRED,
            source=VerificationSource.BUSINESS_REQUEST,
            call=lambda **kwargs: ProviderCallResult(payload=_png()),
            registry=registry,
            clock=lambda: NOW,
        )
        evidence, _ = executor.execute()
        receipt_store = FileReceiptStore(home, registry, clock=lambda: NOW)
        from leo_ppt_generator.config.receipt_store import (
            compute_verification_fingerprint,
        )

        fingerprint = compute_verification_fingerprint(
            provider=ProviderName.OPENAI,
            endpoint_origin=None,
            model="gpt-image-2",
            credential_version="hmac-sha256:unresolved",
            runtime_identity="leo-ppt-generator/0.1.0",
            adapter_version=registry.provider(
                ProviderName.OPENAI, None
            ).adapter.version,
            verification_policy_version=1,
        )
        receipt_store.merge(fingerprint, evidence)

        # 3. 复查：ready，guard 直接放行。
        rechecked = service.status(StatusRequest())
        assert rechecked.status is ConfigStatus.READY
        decision2 = guard.evaluate(
            report_status=rechecked.status,
            required_capabilities=REQUIRED,
            host=HostProbe(HostCapabilityState.UNKNOWN),
        )
        assert decision2.action == "continue"
        assert decision2.eligibility == "allowed"
        assert decision2.lazy_verification is False


def test_journey_guard_resume_after_user_configures():
    """用户完成配置后 guard recheck 恢复原任务。"""
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        service = _configured_service(home)
        guard = HostReadinessGuard(cli_path="/usr/local/bin/leo-ppt")

        # 配置缺失：guard 暂停，给出终端命令。
        from leo_ppt_generator.config.runtime_config import ConfigStore as CS

        bare = CS(home)
        # 空配置：not_configured。
        empty_service = ConfigService(
            bare,
            EnvStore({}),
            ProviderRegistry.default(),
            FileReceiptStore(home, ProviderRegistry.default(), clock=lambda: NOW),
            clock=lambda: NOW,
            cli_path="/usr/local/bin/leo-ppt",
        )
        report = empty_service.status(StatusRequest())
        assert report.status is ConfigStatus.NOT_CONFIGURED
        paused = guard.evaluate(
            report_status=report.status,
            required_capabilities=REQUIRED,
            host=HostProbe(HostCapabilityState.UNKNOWN),
            resume_ref="run-1/stage-image",
        )
        assert paused.action == "blocked_invalid"
        assert paused.primary_action is not None

        # 用户完成配置后复查：allowed → resume 同节点。
        configured = service.status(StatusRequest())
        rechecked = guard.recheck(
            report_status=configured.status,
            required_capabilities=REQUIRED,
            host=HostProbe(HostCapabilityState.UNKNOWN),
            context=paused,
            resume_ref="run-1/stage-image",
        )
        assert rechecked.action == "resume"
        assert rechecked.resume_ref == "run-1/stage-image"


def test_journey_cli_config_status_end_to_end():
    """CLI 层端到端：config status 返回合规 report。"""
    root = Path(__file__).resolve().parents[2]
    cli_root = root / "skills/leo-ppt-generator/runtime/src"
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory) / "home"
        env = {
            **os.environ,
            "LEO_PPT_HOME": str(home),
            "PYTHONPATH": str(cli_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        env.pop("OPENAI_API_KEY", None)
        result = subprocess.run(
            [sys.executable, "-m", "leo_ppt_generator", "config", "status", "--json"],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        report = payload["report"]
        assert report["protocol"] == "leo-ppt-config/v1"
        assert report["readiness_scope"]["route"] == "generate"
        assert report["status"] in {
            "not_configured",
            "configured_unverified",
            "ready",
            "invalid",
            "degraded",
        }
        if report["status"] == "not_configured":
            import shlex

            action = report["primary_action"]
            assert action["kind"] == "run_cli"
            assert shlex.split(action["command"])[-1] == "config"


def _png() -> bytes:
    import io

    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", (4, 4), color=(0, 128, 255)).save(stream, format="PNG")
    return stream.getvalue()
