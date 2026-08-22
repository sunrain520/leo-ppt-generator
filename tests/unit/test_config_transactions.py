"""ConfigTransaction journal 与崩溃一致性的单元测试。"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from leo_ppt_generator.config.models import ProviderName
from leo_ppt_generator.config.transactions import (
    ConfigTransactionError,
    ConfigTransactionJournal,
)

NOW = datetime(2026, 1, 8, tzinfo=UTC)


def _journal(home: Path) -> ConfigTransactionJournal:
    return ConfigTransactionJournal(home, clock=lambda: NOW)


def test_checkpoint_writes_and_reads_roundtrip():
    with tempfile.TemporaryDirectory() as directory:
        journal = _journal(Path(directory))
        journal.write(
            "operation-1",
            provider=ProviderName.OPENAI,
            step="prepared",
            old_config_digest="old-digest",
            target_generation=1,
        )
        checkpoint = journal.read("operation-1")
        assert checkpoint is not None
        assert checkpoint.operation_id == "operation-1"
        assert checkpoint.provider is ProviderName.OPENAI
        assert checkpoint.step == "prepared"
        assert checkpoint.old_config_digest == "old-digest"
        assert checkpoint.target_generation == 1
        # 持久化内容不含 secret。
        payload = json.loads(journal.path("operation-1").read_text())
        assert "secret" not in json.dumps(payload).lower()


def test_advance_follows_state_machine_order():
    with tempfile.TemporaryDirectory() as directory:
        journal = _journal(Path(directory))
        journal.write("op-1", provider=ProviderName.OPENAI, step="prepared")
        journal.advance("op-1", step="receipt_invalidated")
        journal.advance("op-1", step="credential_written", credential_write_id="write-1")
        journal.advance(
            "op-1",
            step="config_committed",
            new_config_digest="new-digest",
        )
        terminal = journal.advance("op-1", step="completed")
        assert terminal.step == "completed"
        assert terminal.credential_write_id == "write-1"
        assert terminal.new_config_digest == "new-digest"


def test_advance_rejects_backwards_step():
    with tempfile.TemporaryDirectory() as directory:
        journal = _journal(Path(directory))
        journal.write("op-1", provider=ProviderName.OPENAI, step="completed")
        with pytest.raises(ConfigTransactionError):
            journal.advance("op-1", step="prepared")


def test_read_missing_returns_none():
    with tempfile.TemporaryDirectory() as directory:
        journal = _journal(Path(directory))
        assert journal.read("missing") is None


def test_advance_missing_fails_closed():
    with tempfile.TemporaryDirectory() as directory:
        journal = _journal(Path(directory))
        with pytest.raises(ConfigTransactionError):
            journal.advance("missing", step="prepared")


def test_invalid_step_rejected():
    with tempfile.TemporaryDirectory() as directory:
        journal = _journal(Path(directory))
        with pytest.raises(ConfigTransactionError):
            journal.write(
                "op-1", provider=ProviderName.OPENAI, step="bogus"
            )
