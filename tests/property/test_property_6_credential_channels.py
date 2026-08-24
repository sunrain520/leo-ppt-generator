from __future__ import annotations

from hypothesis import given, settings, strategies as st

from leo_ppt_generator.credentials import CredentialInputChannel, CredentialInputResolver

PROPERTY_SETTINGS = settings(max_examples=128, derandomize=True, database=None, deadline=None, print_blob=True)
ENV_NAMES = {
    "openai": "OPENAI_API_KEY",
    "openai-compatible": "OPENAI_API_KEY",
    "atlascloud": "ATLASCLOUD_API_KEY",
}


class ObservedStore:
    def __init__(self, available: bool) -> None:
        self.available, self.status_reads, self.reference_reads = available, 0, 0

    def status(self, _provider: str) -> str:
        self.status_reads += 1
        return "available" if self.available else "missing"

    def reference(self, provider: str) -> str:
        self.reference_reads += 1
        return f"store:{provider}"


class ObservedInput:
    def __init__(self, value: str, tty: bool = False) -> None:
        self.value, self.tty, self.reads = value, tty, 0

    def isatty(self) -> bool:
        return self.tty

    def readline(self) -> str:
        self.reads += 1
        return self.value


@PROPERTY_SETTINGS
@given(provider=st.sampled_from(tuple(ENV_NAMES)), tty=st.booleans(), env=st.booleans(), store=st.booleans(), flag=st.booleans(), secret=st.text("abcdef0123456789", min_size=1, max_size=40))
def test_property_6_credential_channel_selection_is_explicit_and_non_interfering(provider, tty, env, store, flag, secret) -> None:
    """**Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6, 10.2, 10.3, 10.4**"""
    observed_store, stdin = ObservedStore(store), ObservedInput(f"{secret}\n")
    hidden_reads: list[str] = []
    selection = CredentialInputResolver(observed_store, {ENV_NAMES[provider]: secret} if env else {}).select(provider, key_stdin=flag, input_stream=stdin, tty_stream=ObservedInput("", tty), hidden_reader=lambda _prompt: hidden_reads.append(secret) or secret)
    expected = CredentialInputChannel.ENVIRONMENT if env else CredentialInputChannel.EXISTING_STORE if store else CredentialInputChannel.TTY_GETPASS if tty else CredentialInputChannel.EXPLICIT_STDIN if flag else CredentialInputChannel.UNAVAILABLE
    assert selection.channel is expected
    assert sum((selection.credential_ref is not None, selection.secret is not None, expected is CredentialInputChannel.UNAVAILABLE)) == 1
    assert stdin.reads == int(expected is CredentialInputChannel.EXPLICIT_STDIN)
    assert len(hidden_reads) == int(expected is CredentialInputChannel.TTY_GETPASS)
    assert observed_store.status_reads == int(not env)
    assert observed_store.reference_reads == int(expected is CredentialInputChannel.EXISTING_STORE)
    if expected in {CredentialInputChannel.ENVIRONMENT, CredentialInputChannel.EXISTING_STORE}:
        assert selection.secret is None and not selection.requires_store_write
        assert selection.credential_ref == (f"env:{ENV_NAMES[provider]}" if env else f"store:{provider}")
    elif selection.secret is not None:
        assert selection.credential_ref is None and selection.requires_store_write
        assert selection.secret.reveal_text() == secret
        selection.close()
