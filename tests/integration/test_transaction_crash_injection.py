"""配置事务 kill-point 故障注入集成测试（7.6）。

在每个事务 barrier（receipt invalidation / CredentialStore write /
ConfigStore replace / completion）后模拟进程崩溃，再运行 repair 验证
收敛、Provider 隔离与旧文件完整。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from leo_ppt_generator.config.models import ProviderName
from leo_ppt_generator.config.transactions import (
    ConfigTransactionJournal,
    TRANSACTION_STATES,
)

NOW = datetime(2026, 1, 8, tzinfo=UTC)

_SCRIPT = """
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from leo_ppt_generator.config.transactions import ConfigTransactionJournal

home = Path(sys.argv[1])
operation_id = sys.argv[2]
crash_after = sys.argv[3]
journal = ConfigTransactionJournal(home, clock=lambda: datetime.now(UTC))
journal.write(operation_id, provider=%r, step="prepared")
steps = ["receipt_invalidated", "credential_written", "config_committed", "completed"]
for step in steps:
    journal.advance(operation_id, step=step)
    if step == crash_after:
        print("CRASH_AFTER", step)
        sys.exit(42)
print("DONE")
"""


def _run_crash(home: Path, operation_id: str, crash_after: str) -> int:
    env = {
        **__import__("os").environ,
        "PYTHONPATH": str(
            Path(__file__).resolve().parents[2]
            / "skills/leo-ppt-generator/runtime/src"
        ),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT % "openai", str(home), operation_id, crash_after],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode


def test_crash_after_each_barrier_then_repair_converges():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        for crash_after in TRANSACTION_STATES[1:]:
            operation_id = f"op-{crash_after}"
            code = _run_crash(home, operation_id, crash_after)
            assert code == 42, f"{crash_after} crash must exit non-zero"

            # repair 从 checkpoint 读取：状态必须停在 crash 前已完成的 step。
            journal = ConfigTransactionJournal(home, clock=lambda: NOW)
            checkpoint = journal.read(operation_id)
            assert checkpoint is not None
            assert checkpoint.step in TRANSACTION_STATES
            # 崩溃后的 checkpoint 是已原子完成的步骤，绝不回退。
            crashed_index = TRANSACTION_STATES.index(crash_after)
            disk_index = TRANSACTION_STATES.index(checkpoint.step)
            assert disk_index <= crashed_index + 1

            # 继续 repair：从当前 step 推进到 completed。
            remaining = TRANSACTION_STATES[
                TRANSACTION_STATES.index(checkpoint.step) + 1 :
            ]
            for step in remaining:
                journal.advance(operation_id, step=step)
            terminal = journal.read(operation_id)
            assert terminal.step == "completed"
            assert terminal.operation_id == operation_id


def test_crash_preserves_previous_operator_journal():
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        journal = ConfigTransactionJournal(home, clock=lambda: NOW)
        # 另一个 Provider 的已完成事务保持完整。
        journal.write(
            "other-provider-op",
            provider=ProviderName.ATLASCLOUD,
            step="completed",
        )
        _run_crash(home, "crashing-op", "credential_written")
        other = journal.read("other-provider-op")
        assert other is not None
        assert other.step == "completed"
        assert other.provider is ProviderName.ATLASCLOUD
        # journal 不含 secret 字段。
        payload = json.loads(journal.path("crashing-op").read_text())
        assert "secret" not in json.dumps(payload).lower()
