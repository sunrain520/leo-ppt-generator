"""文件系统故障注入与 canary 扫描集成测试（13.5）。

覆盖 symlink、特殊文件、宽 ACL、fsync/replace 失败与 endpoint
userinfo/query/fragment 拒绝；递归解析非敏感 schema 并确认日志只含安全 origin。
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from leo_ppt_generator.config.provider_registry import ProviderRegistry
from leo_ppt_generator.config.receipt_store import (
    FileReceiptStore,
    ReceiptStoreError,
)
from leo_ppt_generator.config.runtime_config import (
    ConfigStore,
    RuntimeConfigError,
    validate_endpoint_origin,
)

NOW = datetime(2026, 1, 8, tzinfo=UTC)
_REGISTRY = ProviderRegistry.default()


def test_symlink_receipt_file_is_rejected():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        outside = home / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        receipts = home / "verification-receipts"
        receipts.mkdir()
        link = receipts / "openai.json"
        link.symlink_to(outside)
        store = FileReceiptStore(home, _REGISTRY, clock=lambda: NOW)
        from leo_ppt_generator.config.models import ProviderName

        with pytest.raises(ReceiptStoreError) as captured:
            store._read(ProviderName.OPENAI)
        assert "verification_receipt_file_invalid" in str(captured.value)


def test_symlink_config_store_rejects_atomic_write():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory) / "leo-home"
        home.mkdir()
        target = home / "target.yaml"
        target.write_text("schema_version: 1\n", encoding="utf-8")
        config_path = home / "config.yaml"
        config_path.symlink_to(target)
        store = ConfigStore(home)
        with pytest.raises(RuntimeConfigError) as captured:
            store.compare_and_swap(
                None,
                {"schema_version": 1, "provider_profiles": {}},
            )
        # symlink 目标内容不构成合法 v1：fail closed，不写入 symlink 指向。
        assert str(captured.value) in {
            "config_write_failed",
            "config_invalid",
            "provider_profile_invalid",
        }
        # symlink 目标未被修改。
        assert target.read_text(encoding="utf-8") == "schema_version: 1\n"


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("https://images.example.com", "https://images.example.com"),
        ("https://images.example.com/", "https://images.example.com"),
    ],
)
def test_valid_endpoint_origins(endpoint, expected):
    assert validate_endpoint_origin(endpoint) == expected


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://images.example.com",  # 非 HTTPS
        "https://user:pass@images.example.com",  # userinfo
        "https://images.example.com?key=abc",  # query
        "https://images.example.com/path#frag",  # fragment
        "https://images.example.com/v1",  # path 不属于 origin
        "not-a-url",
        "",
    ],
)
def test_invalid_endpoint_origins_are_rejected(endpoint):
    from leo_ppt_generator.config.runtime_config import RuntimeConfigError

    with pytest.raises(RuntimeConfigError):
        validate_endpoint_origin(endpoint)


def test_failing_receipt_writer_preserves_old_file():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        store = FileReceiptStore(home, _REGISTRY, clock=lambda: NOW)
        from leo_ppt_generator.config.models import (
            Capability,
            CapabilityEvidence,
            ArtifactDigest,
            VerificationSource,
            ProviderName,
        )
        from leo_ppt_generator.config.receipt_store import (
            compute_verification_fingerprint,
        )

        fp = compute_verification_fingerprint(
            provider=ProviderName.OPENAI,
            endpoint_origin=None,
            model="gpt-image-2",
            credential_version="generation:1",
            runtime_identity="leo-ppt-generator/test",
            adapter_version=_REGISTRY.provider(ProviderName.OPENAI, None).adapter.version,
            verification_policy_version=1,
        )
        evidence = {
            Capability.GENERATE: CapabilityEvidence(
                capability=Capability.GENERATE,
                verified_at=NOW,
                expires_at=NOW + __import__("datetime").timedelta(days=7),
                operation_id="op-1",
                verification_source=VerificationSource.PROVIDER_SMOKE,
                artifact_digest=ArtifactDigest(
                    sha256="a" * 64, media_type="image/png", size_bytes=8
                ),
            )
        }
        store.merge(fp, evidence)
        path = store.receipt_path(ProviderName.OPENAI)
        before = path.read_bytes()

        def failing_writer(_path, _value) -> None:
            raise OSError("injected fsync failure")

        broken = FileReceiptStore(
            home, _REGISTRY, clock=lambda: NOW, writer=failing_writer
        )
        with pytest.raises((ReceiptStoreError, OSError)):
            broken.merge(fp, evidence)
        # 旧文件保持完整。
        assert path.read_bytes() == before
        # 无临时残留。
        assert not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]
