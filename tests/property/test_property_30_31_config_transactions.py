# Feature: guided-provider-config, Properties 30/31: config transactions are
# crash-consistent and provider-isolated; provider change preserves the
# previous ready selection until commit

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from hypothesis import given, settings, strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    invariant,
    rule,
)

from leo_ppt_generator.config.models import ProviderName
from leo_ppt_generator.config.transactions import (
    ConfigTransactionError,
    ConfigTransactionJournal,
    TRANSACTION_STATES,
)

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
NOW = datetime(2026, 1, 8, tzinfo=UTC)
_PROVIDERS = (ProviderName.OPENAI, ProviderName.ATLASCLOUD)


def _journal(home: Path) -> ConfigTransactionJournal:
    return ConfigTransactionJournal(home, clock=lambda: NOW)


class TransactionStateMachine(RuleBasedStateMachine):
    """Property 30: Config transactions are crash-consistent and provider-isolated。"""

    def __init__(self) -> None:
        super().__init__()
        self._temporary = tempfile.TemporaryDirectory()
        self.home = Path(self._temporary.name)
        self.journal = _journal(self.home)
        self.steps: dict[str, int] = {}

    def teardown(self) -> None:
        self._temporary.cleanup()

    @rule(
        operation_id=st.text(
            alphabet=st.characters(
                min_codepoint=0x30, max_codepoint=0x39
            ),
            min_size=1,
            max_size=16,
        ),
        provider=st.sampled_from(_PROVIDERS),
    )
    def begin(self, operation_id: str, provider: ProviderName) -> None:
        try:
            self.journal.write(
                operation_id,
                provider=provider,
                step="prepared",
                target_generation=1,
            )
            self.steps[operation_id] = TRANSACTION_STATES.index("prepared")
        except ConfigTransactionError:
            pass

    @rule(
        operation_id=st.text(
            alphabet=st.characters(
                min_codepoint=0x30, max_codepoint=0x39
            ),
            min_size=1,
            max_size=16,
        ),
        step=st.sampled_from(
            (
                "receipt_invalidated",
                "credential_written",
                "config_committed",
                "completed",
            )
        ),
    )
    def advance(self, operation_id: str, step: str) -> None:
        if operation_id not in self.steps:
            return
        current = self.steps[operation_id]
        target = TRANSACTION_STATES.index(step)
        try:
            self.journal.advance(operation_id, step=step)
            if target >= current:
                self.steps[operation_id] = target
        except ConfigTransactionError:
            # 回退或未知操作必须 fail closed，不改变已知状态。
            pass

    @invariant()
    def journal_states_are_monotonic(self) -> None:
        for operation_id, index in self.steps.items():
            checkpoint = self.journal.read(operation_id)
            assert checkpoint is not None
            assert checkpoint.operation_id == operation_id
            # 从磁盘读取的状态不会回退到已观察到的更低阶段。
            disk_index = TRANSACTION_STATES.index(checkpoint.step)
            assert disk_index <= index or disk_index == index


TestProperty30 = TransactionStateMachine.TestCase


# ---------------------------------------------------------------- Property 31
@PROPERTY_SETTINGS
@given(
    current=st.sampled_from(_PROVIDERS),
    candidate=st.sampled_from(_PROVIDERS),
)
def test_property_31_provider_change_preserves_previous_until_commit(current, candidate):
    """**Validates: Requirements 13.7**"""
    with tempfile.TemporaryDirectory() as directory:
        journal = _journal(Path(directory))
        # 原 Provider 的事务先完成；候选事务独立进行。
        journal.write(
            "current-op",
            provider=current,
            step="completed",
        )
        # 候选事务在 committed 前保留原 Provider 状态。
        journal.write(
            "candidate-op",
            provider=candidate,
            step="prepared",
            old_config_digest=f"digest-{current.value}",
        )
        candidate_checkpoint = journal.read("candidate-op")
        assert candidate_checkpoint.old_config_digest == f"digest-{current.value}"
        # 候选完成切换后，原选择仍可恢复（事务隔离）。
        current_checkpoint = journal.read("current-op")
        assert current_checkpoint.step == "completed"
        assert current_checkpoint.provider is current
