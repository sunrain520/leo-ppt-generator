"""跨平台 Provider 凭据存储；公开接口只返回引用和非敏感状态。"""

from __future__ import annotations

import ctypes
import getpass
import os
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .config.runtime_config import default_home

CREDENTIAL_PROTOCOL = "leo-ppt-credential/v1"
KEYCHAIN_SERVICE = "leo-ppt-generator"
PROVIDERS = {
    "openai": "OPENAI_API_KEY",
    "atlascloud": "ATLASCLOUD_API_KEY",
    "paddleocr": "PADDLE_OCR_TOKEN",
}


class CredentialError(ValueError):
    reason_code = "credential_error"


class CredentialStore(Protocol):
    def reference(self, provider: str) -> str: ...
    def status(self, provider: str) -> str: ...
    def read(self, provider: str) -> str: ...
    def write(self, provider: str, secret: str) -> None: ...
    def remove(self, provider: str) -> bool: ...


def _provider(provider: str) -> str:
    if provider not in PROVIDERS:
        raise CredentialError("credential_provider_unsupported")
    return provider


@dataclass
class MacOSKeychainStore:
    runner: object = subprocess.run

    def reference(self, provider: str) -> str:
        return f"keychain:{KEYCHAIN_SERVICE}/{_provider(provider)}"

    def _run(self, arguments: list[str], *, secret: str | None = None):
        result = self.runner(
            ["security", *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return result
        message = f"{result.stderr} {result.stdout}".lower()
        if "could not be found" in message or result.returncode == 44:
            raise CredentialError("credential_not_found")
        if "interaction is not allowed" in message or "locked" in message:
            raise CredentialError("credential_store_locked")
        if "denied" in message or "not permitted" in message:
            raise CredentialError("credential_store_denied")
        raise CredentialError("credential_store_failed")

    def status(self, provider: str) -> str:
        try:
            self._run(
                ["find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", _provider(provider)]
            )
        except CredentialError as exc:
            if str(exc) == "credential_not_found":
                return "missing"
            raise
        return "available"

    def read(self, provider: str) -> str:
        result = self._run(
            ["find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", _provider(provider), "-w"]
        )
        secret = result.stdout.rstrip("\r\n")
        if not secret:
            raise CredentialError("credential_reference_unavailable")
        return secret

    def write(self, provider: str, secret: str) -> None:
        self._run(
            [
                "add-generic-password",
                "-U",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                _provider(provider),
                "-w",
                secret,
            ],
            secret=secret,
        )

    def remove(self, provider: str) -> bool:
        try:
            self._run(
                ["delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", _provider(provider)]
            )
        except CredentialError as exc:
            if str(exc) == "credential_not_found":
                return False
            raise
        return True


@dataclass
class WindowsDPAPIStore:
    root: Path
    protect: object | None = None
    unprotect: object | None = None
    acl_enforcer: object | None = None
    acl_checker: object | None = None

    def __post_init__(self) -> None:
        self.protect = self.protect or _dpapi_protect
        self.unprotect = self.unprotect or _dpapi_unprotect
        self.acl_enforcer = self.acl_enforcer or _enforce_windows_acl
        self.acl_checker = self.acl_checker or _windows_acl_is_private

    def _path(self, provider: str) -> Path:
        return self.root / f"{_provider(provider)}.dpapi"

    def reference(self, provider: str) -> str:
        return f"host:dpapi/{_provider(provider)}"

    def status(self, provider: str) -> str:
        path = self._path(provider)
        if not path.is_file():
            return "missing"
        if not self.acl_checker(path) or not self.acl_checker(self.root):
            raise CredentialError("credential_store_acl_too_broad")
        self.read(provider)
        return "available"

    def read(self, provider: str) -> str:
        path = self._path(provider)
        if not path.is_file():
            raise CredentialError("credential_not_found")
        try:
            return self.unprotect(path.read_bytes()).decode("utf-8")
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialError("credential_blob_invalid") from exc

    def write(self, provider: str, secret: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.acl_enforcer(self.root, True)
        path = self._path(provider)
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_bytes(self.protect(secret.encode("utf-8")))
            os.chmod(temporary, 0o600)
            self.acl_enforcer(temporary, False)
            os.replace(temporary, path)
            self.acl_enforcer(path, False)
        finally:
            temporary.unlink(missing_ok=True)

    def remove(self, provider: str) -> bool:
        path = self._path(provider)
        if not path.exists():
            return False
        path.unlink()
        return True


class UnsupportedCredentialStore:
    def reference(self, provider: str) -> str:
        _provider(provider)
        raise CredentialError("credential_store_unsupported")

    def status(self, provider: str) -> str:
        _provider(provider)
        return "missing"

    def read(self, provider: str) -> str:
        _provider(provider)
        raise CredentialError("credential_store_unsupported")

    def write(self, provider: str, secret: str) -> None:
        _provider(provider)
        raise CredentialError("credential_store_unsupported")

    def remove(self, provider: str) -> bool:
        _provider(provider)
        return False


def platform_store() -> CredentialStore:
    if sys.platform == "darwin":
        return MacOSKeychainStore()
    if os.name == "nt":
        return WindowsDPAPIStore(default_home() / "credentials")
    return UnsupportedCredentialStore()


@dataclass
class CredentialManager:
    store: CredentialStore
    environ: dict[str, str] | os._Environ[str] = field(
        default_factory=lambda: os.environ
    )

    def status(self, provider: str) -> dict[str, object]:
        provider = _provider(provider)
        environment_name = PROVIDERS[provider]
        if self.environ.get(environment_name):
            return self._report(
                provider, "available", "credential_environment_available", "environment-reference", f"env:{environment_name}"
            )
        status = self.store.status(provider)
        reference = self.store.reference(provider) if status == "available" else None
        return self._report(
            provider,
            status,
            "credential_store_available" if status == "available" else "credential_missing",
            "os-store-reference" if status == "available" else "none",
            reference,
        )

    def add(self, provider: str, *, overwrite: bool, input_stream=None, reader=None) -> dict[str, object]:
        provider = _provider(provider)
        stream = input_stream or sys.stdin
        if not stream.isatty():
            raise CredentialError("credential_tty_required")
        if self.store.status(provider) == "available" and not overwrite:
            raise CredentialError("credential_overwrite_confirmation_required")
        secret = (reader or getpass.getpass)(f"{provider} credential: ")
        if not secret:
            raise CredentialError("credential_empty")
        self.store.write(provider, secret)
        return self._report(provider, "available", "credential_saved", "os-store-reference", self.store.reference(provider))

    def remove(self, provider: str) -> dict[str, object]:
        provider = _provider(provider)
        removed = self.store.remove(provider)
        return self._report(provider, "missing", "credential_removed" if removed else "credential_not_found", "none", None)

    def reference(self, provider: str) -> tuple[str, str]:
        report = self.status(provider)
        if report["status"] != "available":
            return "environment-reference", f"env:{PROVIDERS[_provider(provider)]}"
        return str(report["reference_type"]), str(report["credential_ref"])

    def resolve(self, prefix: str, value: str) -> str:
        provider = value.rsplit("/", 1)[-1]
        provider = _provider(provider)
        expected = self.store.reference(provider)
        if f"{prefix}:{value}" != expected:
            raise CredentialError("credential_reference_invalid")
        return self.store.read(provider)

    @staticmethod
    def _report(provider: str, status: str, reason: str, reference_type: str, reference: str | None) -> dict[str, object]:
        return {
            "protocol": CREDENTIAL_PROTOCOL,
            "schema_version": 1,
            "status": status,
            "reason_code": reason,
            "provider": provider,
            "reference_type": reference_type,
            "credential_ref": reference,
            "evidence_refs": [f"credential://status/{provider}"],
        }


def credential_manager() -> CredentialManager:
    return CredentialManager(platform_store())


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(value: bytes) -> tuple[_DataBlob, object]:
    buffer = ctypes.create_string_buffer(value)
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _dpapi_protect(value: bytes) -> bytes:
    source, source_buffer = _blob(value)
    output = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)):
        raise CredentialError("credential_dpapi_encrypt_failed")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)
        del source_buffer


def _dpapi_unprotect(value: bytes) -> bytes:
    source, source_buffer = _blob(value)
    output = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)):
        raise CredentialError("credential_dpapi_decrypt_failed")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)
        del source_buffer


def _enforce_windows_acl(path: Path, directory: bool) -> None:
    grant = f"{getpass.getuser()}:{'(OI)(CI)' if directory else ''}F"
    result = subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", grant],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CredentialError("credential_store_acl_failed")


def _windows_acl_is_private(path: Path) -> bool:
    result = subprocess.run(["icacls", str(path)], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise CredentialError("credential_store_acl_failed")
    lowered = result.stdout.lower()
    return not any(name in lowered for name in ("everyone", "authenticated users", "builtin\\users"))
