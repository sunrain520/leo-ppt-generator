from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from leo_ppt_generator.credentials import (
    KEYCHAIN_SERVICE,
    CredentialError,
    CredentialManager,
    MacOSKeychainStore,
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


def test_keychain_commands_bind_fixed_service_and_provider_account():
    calls = []

    class Result:
        returncode = 0
        stdout = "secret\n"
        stderr = ""

    def runner(arguments, **kwargs):
        calls.append(arguments)
        return Result()

    store = MacOSKeychainStore(runner)
    store.write("atlascloud", "secret")
    assert store.read("atlascloud") == "secret"
    assert all(KEYCHAIN_SERVICE in call for call in calls)
    assert all("atlascloud" in call for call in calls)


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
