from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from leo_ppt_generator.credentials import (
    KEYCHAIN_SERVICE,
    CredentialError,
    CredentialManager,
    MacOSKeychainStore,
    SecretBuffer,
    WindowsDPAPIStore,
)


@dataclass
class FakeStore:
    values: dict[str, str] = field(default_factory=dict)

    def reference(self, provider):
        return f"keychain:{KEYCHAIN_SERVICE}/{provider}"

    def status(self, provider):
        return "available" if provider in self.values else "missing"

    def read(self, provider):
        if provider not in self.values:
            raise CredentialError("credential_not_found")
        return self.values[provider]

    def write(self, provider, secret):
        self.values[provider] = secret

    def remove(self, provider):
        return self.values.pop(provider, None) is not None


class TTY:
    def isatty(self):
        return True


class Pipe:
    def isatty(self):
        return False


def test_add_status_overwrite_remove_and_secret_redaction():
    store = FakeStore()
    manager = CredentialManager(store, {})

    saved = manager.add("openai", overwrite=False, input_stream=TTY(), reader=lambda _: "secret-value")
    assert saved["credential_ref"] == f"keychain:{KEYCHAIN_SERVICE}/openai"
    assert "secret-value" not in json.dumps(saved)
    assert manager.status("openai")["status"] == "available"
    with pytest.raises(CredentialError, match="credential_overwrite_confirmation_required"):
        manager.add("openai", overwrite=False, input_stream=TTY(), reader=lambda _: "new")
    manager.add("openai", overwrite=True, input_stream=TTY(), reader=lambda _: "new")
    assert store.values["openai"] == "new"
    assert manager.remove("openai")["reason_code"] == "credential_removed"
    assert manager.remove("openai")["reason_code"] == "credential_not_found"


def test_add_uses_chinese_credential_prompt():
    prompts = []
    manager = CredentialManager(FakeStore(), {})

    manager.add(
        "openai-compatible",
        overwrite=False,
        input_stream=TTY(),
        reader=lambda prompt: prompts.append(prompt) or "test-secret",
    )

    assert prompts == ["请输入 openai-compatible 的访问凭据："]


def test_add_rejects_pipe_before_reading_secret():
    called = False

    def reader(_prompt):
        nonlocal called
        called = True
        return "secret"

    with pytest.raises(CredentialError, match="credential_tty_required"):
        CredentialManager(FakeStore(), {}).add(
            "openai", overwrite=False, input_stream=Pipe(), reader=reader
        )
    assert called is False


def test_environment_reference_has_priority_over_os_store():
    manager = CredentialManager(
        FakeStore({"openai": "stored-secret"}), {"OPENAI_API_KEY": "environment-secret"}
    )
    report = manager.status("openai")
    assert report["reference_type"] == "environment-reference"
    assert report["credential_ref"] == "env:OPENAI_API_KEY"
    assert "environment-secret" not in json.dumps(report)


def test_openai_compatible_uses_a_distinct_environment_and_os_store_reference():
    manager = CredentialManager(FakeStore(), {"OPENAI_API_KEY": "proxy-secret"})
    report = manager.status("openai-compatible")
    assert report["credential_ref"] == "env:OPENAI_API_KEY"
    assert "proxy-secret" not in json.dumps(report)


class FakeKeychainAPI:
    def __init__(self):
        self.values = {}
        self.calls = []
        self.copy_status = 0
        self.add_status = 0
        self.update_status = 0
        self.delete_status = 0

    def copy(self, service, account, *, return_data):
        self.calls.append(("copy", service, account, return_data))
        if self.copy_status:
            return self.copy_status, None
        if (service, account) not in self.values:
            return -25300, None
        return 0, self.values[(service, account)] if return_data else None

    def add(self, service, account, value):
        self.calls.append(("add", service, account, value))
        if self.add_status:
            return self.add_status
        key = (service, account)
        if key in self.values:
            return -25299
        self.values[key] = value
        return 0

    def update(self, service, account, value):
        self.calls.append(("update", service, account, value))
        if self.update_status:
            return self.update_status
        key = (service, account)
        if key not in self.values:
            return -25300
        self.values[key] = value
        return 0

    def delete(self, service, account):
        self.calls.append(("delete", service, account))
        if self.delete_status:
            return self.delete_status
        return 0 if self.values.pop((service, account), None) is not None else -25300


def test_keychain_secitem_add_update_read_delete_use_unique_service_account():
    api = FakeKeychainAPI()
    store = MacOSKeychainStore(api)

    assert store.status("atlascloud") == "missing"
    store.write("atlascloud", "first-secret")
    store.write("atlascloud", "updated-secret")
    assert store.status("atlascloud") == "available"
    assert store.read("atlascloud") == "updated-secret"
    assert store.remove("atlascloud") is True
    assert store.remove("atlascloud") is False

    assert any(call[0] == "add" for call in api.calls)
    assert any(call[0] == "update" for call in api.calls)
    assert all(call[1:3] == (KEYCHAIN_SERVICE, "atlascloud") for call in api.calls)


def test_keychain_write_accepts_secret_buffer_without_closing_caller_handle():
    from leo_ppt_generator.credentials import SecretBuffer

    api = FakeKeychainAPI()
    store = MacOSKeychainStore(api)
    secret = SecretBuffer("buffer-secret")

    store.write("openai", secret)

    assert store.read("openai") == "buffer-secret"
    assert secret.closed is False
    secret.close()


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        (-25308, "credential_store_locked"),
        (-25315, "credential_store_locked"),
        (-25291, "credential_store_locked"),
        (-61, "credential_store_denied"),
        (-25292, "credential_store_denied"),
        (-25293, "credential_store_denied"),
        (-34018, "credential_store_denied"),
        (-25295, "credential_blob_invalid"),
        (-26275, "credential_blob_invalid"),
        (-50, "credential_store_failed"),
    ],
)
def test_keychain_maps_secitem_access_failures_to_stable_reason_codes(
    status, reason_code
):
    api = FakeKeychainAPI()
    api.copy_status = status

    with pytest.raises(CredentialError, match=reason_code):
        MacOSKeychainStore(api).status("openai")


@pytest.mark.parametrize(
    ("operation", "status", "reason_code"),
    [
        ("add", -25293, "credential_store_denied"),
        ("update", -25308, "credential_store_locked"),
        ("delete", -34018, "credential_store_denied"),
    ],
)
def test_keychain_maps_mutation_failures_without_using_subprocess(
    monkeypatch, operation, status, reason_code
):
    def reject_subprocess(*_args, **_kwargs):
        raise AssertionError("macOS Keychain adapter must not start a subprocess")

    monkeypatch.setattr("leo_ppt_generator.credentials.subprocess.run", reject_subprocess)
    api = FakeKeychainAPI()
    store = MacOSKeychainStore(api)
    if operation == "add":
        api.add_status = status
        action = lambda: store.write("openai", "canary-secret")
    elif operation == "update":
        api.values[(KEYCHAIN_SERVICE, "openai")] = b"old-secret"
        api.update_status = status
        action = lambda: store.write("openai", "canary-secret")
    else:
        api.delete_status = status
        action = lambda: store.remove("openai")

    with pytest.raises(CredentialError, match=reason_code):
        action()


def test_keychain_rejects_non_utf8_value_as_invalid_blob():
    api = FakeKeychainAPI()
    api.values[(KEYCHAIN_SERVICE, "openai")] = b"\xff"

    with pytest.raises(CredentialError, match="credential_blob_invalid"):
        MacOSKeychainStore(api).read("openai")


def test_keychain_serializes_secitem_access_across_store_instances():
    import threading
    import time

    class ConcurrentProbeAPI(FakeKeychainAPI):
        def __init__(self):
            super().__init__()
            self.values[(KEYCHAIN_SERVICE, "openai")] = b"secret"
            self.active = 0
            self.max_active = 0
            self.guard = threading.Lock()

        def copy(self, service, account, *, return_data):
            with self.guard:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                time.sleep(0.01)
                return super().copy(service, account, return_data=return_data)
            finally:
                with self.guard:
                    self.active -= 1

    api = ConcurrentProbeAPI()
    stores = [MacOSKeychainStore(api), MacOSKeychainStore(api)]
    threads = [
        threading.Thread(target=stores[index % 2].status, args=("openai",))
        for index in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert api.max_active == 1


def test_dpapi_store_encrypts_validates_acl_and_rejects_corruption(tmp_path):
    root = tmp_path / "credentials"
    store = WindowsDPAPIStore(
        root,
        protect=lambda value: b"encrypted:" + value[::-1],
        unprotect=lambda value: value.removeprefix(b"encrypted:")[::-1]
        if value.startswith(b"encrypted:")
        else (_ for _ in ()).throw(ValueError("corrupt")),
        acl_enforcer=lambda _path, _directory: None,
        acl_checker=lambda _path: True,
    )
    store.write("openai", "secret")
    blob = (root / "openai.dpapi").read_bytes()
    assert b"secret" not in blob
    assert store.status("openai") == "available"
    assert store.read("openai") == "secret"
    (root / "openai.dpapi").write_bytes(b"corrupt")
    with pytest.raises(CredentialError, match="credential_blob_invalid"):
        store.status("openai")


def test_dpapi_store_rejects_broad_acl(tmp_path):
    root = tmp_path / "credentials"
    root.mkdir()
    (root / "openai.dpapi").write_bytes(b"encrypted")
    store = WindowsDPAPIStore(
        root,
        protect=lambda value: value,
        unprotect=lambda value: value,
        acl_enforcer=lambda _path, _directory: None,
        acl_checker=lambda _path: False,
    )
    with pytest.raises(CredentialError, match="credential_store_acl_too_broad"):
        store.status("openai")


def test_dpapi_binding_is_current_user_only_and_rejects_machine_scope(monkeypatch):
    from leo_ppt_generator import credentials as credentials_module

    class FakeDPAPI:
        def __init__(self):
            self.calls = []

        def protect(self, value, *, flags):
            self.calls.append(("protect", value, flags))
            return b"protected"

        def unprotect(self, value, *, flags):
            self.calls.append(("unprotect", value, flags))
            return b"secret"

    api = FakeDPAPI()
    assert credentials_module._dpapi_protect(b"secret", api) == b"protected"
    assert credentials_module._dpapi_unprotect(b"protected", api) == b"secret"
    for _operation, _value, flags in api.calls:
        assert flags & credentials_module._CRYPTPROTECT_UI_FORBIDDEN
        assert not flags & credentials_module._CRYPTPROTECT_LOCAL_MACHINE

    monkeypatch.setattr(
        credentials_module,
        "_DPAPI_CURRENT_USER_FLAGS",
        credentials_module._CRYPTPROTECT_LOCAL_MACHINE,
    )
    with pytest.raises(CredentialError, match="credential_dpapi_machine_scope_forbidden"):
        credentials_module._dpapi_protect(b"secret", api)


def test_dpapi_store_accepts_secret_buffer_and_never_writes_plaintext(tmp_path):
    from leo_ppt_generator.credentials import SecretBuffer

    root = tmp_path / "credentials"
    store = WindowsDPAPIStore(
        root,
        protect=lambda value: b"protected:" + value[::-1],
        unprotect=lambda value: value.removeprefix(b"protected:")[::-1],
        acl_enforcer=lambda _path, _directory: None,
        acl_checker=lambda _path: True,
    )
    secret = SecretBuffer("buffer-canary")

    store.write("atlascloud", secret)

    assert secret.closed is False
    assert b"buffer-canary" not in (root / "atlascloud.dpapi").read_bytes()
    assert store.read("atlascloud") == "buffer-canary"
    assert not list(root.glob("*.tmp"))
    secret.close()


def test_dpapi_store_rejects_symlink_roots_and_files(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    root_link = tmp_path / "credentials"
    root_link.symlink_to(target, target_is_directory=True)
    linked_store = WindowsDPAPIStore(
        root_link,
        protect=lambda value: value,
        unprotect=lambda value: value,
        acl_enforcer=lambda _path, _directory: None,
        acl_checker=lambda _path: True,
    )
    with pytest.raises(CredentialError, match="credential_store_path_invalid"):
        linked_store.status("openai")

    root = tmp_path / "safe-credentials"
    root.mkdir()
    outside = tmp_path / "outside.dpapi"
    outside.write_bytes(b"protected")
    (root / "openai.dpapi").symlink_to(outside)
    file_store = WindowsDPAPIStore(
        root,
        protect=lambda value: value,
        unprotect=lambda value: value,
        acl_enforcer=lambda _path, _directory: None,
        acl_checker=lambda _path: True,
    )
    with pytest.raises(CredentialError, match="credential_store_path_invalid"):
        file_store.read("openai")


def test_dpapi_atomic_replace_failure_preserves_old_blob_and_removes_temp(
    tmp_path, monkeypatch
):
    from leo_ppt_generator import credentials as credentials_module

    root = tmp_path / "credentials"
    root.mkdir()
    stable = root / "openai.dpapi"
    stable.write_bytes(b"old-protected")
    store = WindowsDPAPIStore(
        root,
        protect=lambda _value: b"new-protected",
        unprotect=lambda value: value,
        acl_enforcer=lambda _path, _directory: None,
        acl_checker=lambda _path: True,
    )

    def fail_replace(_source, _destination):
        raise PermissionError("replace denied")

    monkeypatch.setattr(credentials_module.os, "replace", fail_replace)
    with pytest.raises(CredentialError, match="credential_store_denied"):
        store.write("openai", "canary-secret")

    assert stable.read_bytes() == b"old-protected"
    assert not list(root.glob("*.tmp"))
    assert all(b"canary-secret" not in path.read_bytes() for path in root.iterdir())


def test_dpapi_post_replace_acl_failure_removes_unsafe_blob_and_temp(tmp_path):
    root = tmp_path / "credentials"
    stable = root / "openai.dpapi"

    def acl_checker(path):
        return path != stable

    store = WindowsDPAPIStore(
        root,
        protect=lambda _value: b"protected",
        unprotect=lambda value: value,
        acl_enforcer=lambda _path, _directory: None,
        acl_checker=acl_checker,
    )
    with pytest.raises(CredentialError, match="credential_store_acl_too_broad"):
        store.write("openai", "secret")

    assert not stable.exists()
    assert not list(root.glob("*.tmp"))


def test_dpapi_store_rejects_empty_oversized_and_non_utf8_blobs(tmp_path):
    root = tmp_path / "credentials"
    root.mkdir()
    stable = root / "openai.dpapi"
    store = WindowsDPAPIStore(
        root,
        protect=lambda value: value,
        unprotect=lambda value: value,
        acl_enforcer=lambda _path, _directory: None,
        acl_checker=lambda _path: True,
    )

    stable.write_bytes(b"")
    with pytest.raises(CredentialError, match="credential_blob_invalid"):
        store.read("openai")

    monkeypatch_blob_limit = 4
    store._max_blob_bytes = monkeypatch_blob_limit
    stable.write_bytes(b"12345")
    with pytest.raises(CredentialError, match="credential_blob_invalid"):
        store.read("openai")

    store._max_blob_bytes = 16
    stable.write_bytes(b"\xff")
    with pytest.raises(CredentialError, match="credential_blob_invalid"):
        store.read("openai")


def test_windows_acl_uses_current_user_sid_and_rejects_broad_principals(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from leo_ppt_generator import credentials as credentials_module

    calls = []
    responses = iter(
        [
            SimpleNamespace(
                returncode=0,
                stdout='"DOMAIN\\alice","S-1-5-21-1000"\n',
            ),
            SimpleNamespace(returncode=0, stdout="processed"),
            SimpleNamespace(
                returncode=0,
                stdout='"DOMAIN\\alice","S-1-5-21-1000"\n',
            ),
            SimpleNamespace(
                returncode=0,
                stdout="C:\\credentials BUILTIN\\Users:(R)\n",
            ),
        ]
    )

    def fake_run(arguments, **_kwargs):
        calls.append(arguments)
        return next(responses)

    monkeypatch.setattr(credentials_module.subprocess, "run", fake_run)
    path = tmp_path / "credentials"
    credentials_module._enforce_windows_acl(path, True)
    assert calls[1] == [
        "icacls",
        str(path),
        "/inheritance:r",
        "/grant:r",
        "*S-1-5-21-1000:(OI)(CI)F",
        "/c",
    ]
    assert credentials_module._windows_acl_is_private(path) is False


def test_secret_buffer_is_redacted_non_serializable_and_closes():
    import pickle

    from leo_ppt_generator.credentials import SecretBuffer

    secret = SecretBuffer("canary-secret")
    assert "canary-secret" not in repr(secret)
    assert "canary-secret" not in str(secret)
    with pytest.raises(TypeError):
        json.dumps({"secret": secret})
    with pytest.raises(TypeError, match="不可序列化"):
        pickle.dumps(secret)

    assert secret.reveal_text() == "canary-secret"
    secret.close()
    assert secret.closed is True
    assert len(secret) == 0
    with pytest.raises(CredentialError, match="credential_secret_closed"):
        secret.reveal_bytes()


def test_envelope_metadata_contains_only_non_sensitive_correlation_fields():
    from leo_ppt_generator.credentials import CredentialEnvelopeMetadata

    metadata = CredentialEnvelopeMetadata(
        provider="openai",
        generation=2,
        write_id="write-123",
        credential_ref="keychain:leo-ppt-generator/openai",
    )
    assert metadata.as_dict() == {
        "schema_version": 1,
        "provider": "openai",
        "generation": 2,
        "write_id": "write-123",
        "credential_ref": "keychain:leo-ppt-generator/openai",
    }
    assert "secret" not in json.dumps(metadata.as_dict()).lower()


class CountingInput:
    def __init__(self, value: str, *, tty: bool = False):
        self.value = value
        self.tty = tty
        self.reads = 0

    def isatty(self):
        return self.tty

    def readline(self):
        self.reads += 1
        return self.value


def test_input_resolver_uses_env_then_store_without_exposing_secret():
    from leo_ppt_generator.credentials import (
        CredentialInputChannel,
        CredentialInputResolver,
    )

    environment = CredentialInputResolver(
        FakeStore({"openai": "stored-secret"}),
        {"OPENAI_API_KEY": "environment-secret"},
    ).select("openai", tty_stream=TTY())
    assert environment.channel is CredentialInputChannel.ENVIRONMENT
    assert environment.credential_ref == "env:OPENAI_API_KEY"
    assert environment.secret is None
    assert "environment-secret" not in repr(environment)

    existing = CredentialInputResolver(
        FakeStore({"openai": "stored-secret"}), {}
    ).select("openai", tty_stream=TTY())
    assert existing.channel is CredentialInputChannel.EXISTING_STORE
    assert existing.credential_ref == f"keychain:{KEYCHAIN_SERVICE}/openai"
    assert existing.secret is None
    assert "stored-secret" not in repr(existing)


def test_input_resolver_tty_precedes_explicit_stdin_and_reads_hidden_once():
    from leo_ppt_generator.credentials import (
        CredentialInputChannel,
        CredentialInputResolver,
    )

    pipe = CountingInput("stdin-secret\n")
    hidden_calls = []
    selection = CredentialInputResolver(FakeStore(), {}).select(
        "openai",
        key_stdin=True,
        input_stream=pipe,
        tty_stream=TTY(),
        hidden_reader=lambda prompt: hidden_calls.append(prompt) or "tty-secret",
    )
    assert selection.channel is CredentialInputChannel.TTY_GETPASS
    assert selection.secret.reveal_text() == "tty-secret"
    assert pipe.reads == 0
    assert len(hidden_calls) == 1
    selection.close()


def test_input_resolver_reads_stdin_once_only_when_explicitly_selected():
    from leo_ppt_generator.credentials import (
        CredentialInputChannel,
        CredentialInputResolver,
    )

    pipe = CountingInput("stdin-secret\nignored\n")
    hidden_calls = []
    resolver = CredentialInputResolver(FakeStore(), {})
    unavailable = resolver.select(
        "openai",
        input_stream=pipe,
        tty_stream=Pipe(),
        hidden_reader=lambda _prompt: hidden_calls.append(True) or "hidden-secret",
    )
    assert unavailable.channel is CredentialInputChannel.UNAVAILABLE
    assert unavailable.reason_code == "credential_input_channel_unavailable"
    assert pipe.reads == 0
    assert hidden_calls == []

    selected = resolver.select(
        "openai",
        key_stdin=True,
        input_stream=pipe,
        tty_stream=Pipe(),
        hidden_reader=lambda _prompt: hidden_calls.append(True) or "hidden-secret",
    )
    assert selected.channel is CredentialInputChannel.EXPLICIT_STDIN
    assert selected.secret.reveal_text() == "stdin-secret\nignored"
    assert selected.requires_store_write is True
    assert pipe.reads == 1
    assert hidden_calls == []
    selected.close()


def test_input_resolver_rejects_empty_explicit_stdin():
    from leo_ppt_generator.credentials import CredentialInputResolver

    with pytest.raises(CredentialError, match="credential_empty"):
        CredentialInputResolver(FakeStore(), {}).select(
            "openai",
            key_stdin=True,
            input_stream=CountingInput("\n"),
            tty_stream=Pipe(),
        )


def test_manager_environment_version_is_rotation_sensitive_and_closes_key():
    class VersionStore(FakeStore):
        def __init__(self):
            super().__init__()
            self.keys = []

        def fingerprint_key(self, create=False):
            key = SecretBuffer(b"k" * 32)
            self.keys.append(key)
            return key

    store = VersionStore()
    environ = {"OPENAI_API_KEY": "first-secret"}
    manager = CredentialManager(store, environ)

    first = manager.environment_version("openai")
    environ["OPENAI_API_KEY"] = "rotated-secret"
    rotated = manager.environment_version("openai")

    assert first is not None and first.startswith("hmac-sha256:")
    assert rotated is not None and rotated != first
    assert all(key.closed for key in store.keys)


def test_input_resolver_force_new_secret_skips_environment_and_existing_store():
    from leo_ppt_generator.credentials import (
        CredentialInputChannel,
        CredentialInputResolver,
    )

    hidden_calls: list[str] = []
    resolver = CredentialInputResolver(
        FakeStore({"openai": "stored-secret"}),
        {"OPENAI_API_KEY": "environment-secret"},
    )

    selection = resolver.select(
        "openai",
        tty_stream=TTY(),
        hidden_reader=lambda prompt: hidden_calls.append(prompt) or "replacement-secret",
        force_new_secret=True,
    )

    assert selection.channel is CredentialInputChannel.TTY_GETPASS
    assert selection.secret is not None
    assert selection.secret.reveal_text() == "replacement-secret"
    assert hidden_calls == ["请输入 openai 的访问凭据："]
    assert "environment-secret" not in repr(selection)
    assert "stored-secret" not in repr(selection)
    selection.close()
