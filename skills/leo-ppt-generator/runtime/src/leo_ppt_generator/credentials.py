"""跨平台 Provider 凭据存储；公开接口只返回引用和非敏感状态。"""

from __future__ import annotations

import ctypes
import getpass
import hashlib
import hmac
import os
import subprocess
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar, Protocol

from .config.runtime_config import default_home

CREDENTIAL_PROTOCOL = "leo-ppt-credential/v1"
CREDENTIAL_ENVELOPE_SCHEMA_VERSION = 1
KEYCHAIN_SERVICE = "leo-ppt-generator"
FINGERPRINT_KEY_ACCOUNT = "verification-fingerprint-key"
FINGERPRINT_KEY_BYTES = 32
CREDENTIAL_VERSION_PREFIX = "hmac-sha256"
PROVIDERS = {
    "openai": "OPENAI_API_KEY",
    "openai-compatible": "OPENAI_API_KEY",
    "atlascloud": "ATLASCLOUD_API_KEY",
    "paddleocr": "PADDLE_OCR_TOKEN",
}


class CredentialError(ValueError):
    reason_code = "credential_error"


class SecretBuffer:
    """短生命周期、可显式清零且禁止序列化的 secret handle。"""

    __slots__ = ("_buffer", "_closed")

    def __init__(self, value: str | bytes | bytearray) -> None:
        if isinstance(value, str):
            encoded = value.encode("utf-8")
        elif isinstance(value, (bytes, bytearray)):
            encoded = bytes(value)
        else:
            raise TypeError("secret 必须是 str 或 bytes-like")
        self._buffer = bytearray(encoded)
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def __len__(self) -> int:
        return 0 if self._closed else len(self._buffer)

    def __bool__(self) -> bool:
        return not self._closed and bool(self._buffer)

    def __repr__(self) -> str:
        return "SecretBuffer(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"

    def __reduce_ex__(self, _protocol: int):
        raise TypeError("SecretBuffer 不可序列化")

    def __copy__(self):
        raise TypeError("SecretBuffer 不可复制")

    def __deepcopy__(self, _memo):
        raise TypeError("SecretBuffer 不可复制")

    def reveal_bytes(self) -> bytes:
        """仅供受保护 store/provider 边界创建最短生命周期副本。"""
        self._ensure_open()
        return bytes(self._buffer)

    def reveal_text(self) -> str:
        """仅供必须接收文本的受保护边界使用。"""
        self._ensure_open()
        return self._buffer.decode("utf-8")

    def close(self) -> None:
        if self._closed:
            return
        for index in range(len(self._buffer)):
            self._buffer[index] = 0
        self._buffer.clear()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise CredentialError("credential_secret_closed")

    def __enter__(self) -> "SecretBuffer":
        self._ensure_open()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


@dataclass(frozen=True, slots=True)
class CredentialEnvelopeMetadata:
    """受保护 OS store envelope 的非敏感、可持久化元数据。"""

    provider: str
    generation: int
    write_id: str
    credential_ref: str
    schema_version: int = CREDENTIAL_ENVELOPE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _provider(self.provider)
        if self.schema_version != CREDENTIAL_ENVELOPE_SCHEMA_VERSION:
            raise CredentialError("credential_envelope_schema_invalid")
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 1
        ):
            raise CredentialError("credential_generation_invalid")
        if not self.write_id:
            raise CredentialError("credential_write_id_invalid")
        if not self.credential_ref:
            raise CredentialError("credential_reference_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "generation": self.generation,
            "write_id": self.write_id,
            "credential_ref": self.credential_ref,
        }


class CredentialInputChannel(str, Enum):
    ENVIRONMENT = "environment"
    EXISTING_STORE = "existing_store"
    TTY_GETPASS = "tty_getpass"
    EXPLICIT_STDIN = "explicit_stdin"
    UNAVAILABLE = "unavailable"


@dataclass(slots=True)
class CredentialInputSelection:
    channel: CredentialInputChannel
    reason_code: str
    credential_ref: str | None = None
    secret: SecretBuffer | None = None

    def __post_init__(self) -> None:
        reference_channel = self.channel in {
            CredentialInputChannel.ENVIRONMENT,
            CredentialInputChannel.EXISTING_STORE,
        }
        secret_channel = self.channel in {
            CredentialInputChannel.TTY_GETPASS,
            CredentialInputChannel.EXPLICIT_STDIN,
        }
        if reference_channel != (self.credential_ref is not None):
            raise CredentialError("credential_input_selection_invalid")
        if secret_channel != (self.secret is not None):
            raise CredentialError("credential_input_selection_invalid")

    @property
    def requires_store_write(self) -> bool:
        return self.secret is not None

    def close(self) -> None:
        if self.secret is not None:
            self.secret.close()

    def __enter__(self) -> "CredentialInputSelection":
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


class CredentialStore(Protocol):
    def reference(self, provider: str) -> str: ...
    def status(self, provider: str) -> str: ...
    def read(self, provider: str) -> str: ...
    def write(self, provider: str, secret: str) -> None: ...
    def remove(self, provider: str) -> bool: ...
    def fingerprint_key(self, create: bool = False) -> SecretBuffer | None: ...


@dataclass(slots=True)
class CredentialInputResolver:
    """按唯一优先级选择凭据来源，不执行持久化。"""

    store: CredentialStore
    environ: dict[str, str] | os._Environ[str] = field(
        default_factory=lambda: os.environ
    )

    def select(
        self,
        provider: str,
        *,
        key_stdin: bool = False,
        input_stream=None,
        tty_stream=None,
        hidden_reader=None,
        force_new_secret: bool = False,
    ) -> CredentialInputSelection:
        provider = _provider(provider)
        environment_name = PROVIDERS[provider]
        if not force_new_secret:
            if self.environ.get(environment_name):
                return CredentialInputSelection(
                    CredentialInputChannel.ENVIRONMENT,
                    "credential_environment_available",
                    credential_ref=f"env:{environment_name}",
                )

            if self.store.status(provider) == "available":
                return CredentialInputSelection(
                    CredentialInputChannel.EXISTING_STORE,
                    "credential_store_available",
                    credential_ref=self.store.reference(provider),
                )

        terminal = sys.stdin if tty_stream is None else tty_stream
        if _is_tty(terminal):
            reader = hidden_reader or getpass.getpass
            return self._secret_selection(
                CredentialInputChannel.TTY_GETPASS,
                "credential_input_tty",
                reader(f"请输入 {provider} 的访问凭据："),
            )

        if key_stdin:
            stream = sys.stdin if input_stream is None else input_stream
            return self._secret_selection(
                CredentialInputChannel.EXPLICIT_STDIN,
                "credential_input_stdin",
                _read_stdin_once(stream),
            )

        return CredentialInputSelection(
            CredentialInputChannel.UNAVAILABLE,
            "credential_input_channel_unavailable",
        )

    @staticmethod
    def _secret_selection(
        channel: CredentialInputChannel,
        reason_code: str,
        value: str | bytes,
    ) -> CredentialInputSelection:
        secret = SecretBuffer(value)
        if not secret:
            secret.close()
            raise CredentialError("credential_empty")
        return CredentialInputSelection(channel, reason_code, secret=secret)


def _is_tty(stream: object) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError):
        return False


def _read_stdin_once(stream: object) -> str | bytes:
    value = stream.readline()
    if isinstance(value, bytes):
        return value.rstrip(b"\r\n")
    if isinstance(value, str):
        return value.rstrip("\r\n")
    raise CredentialError("credential_input_invalid")


def _provider(provider: str) -> str:
    if provider not in PROVIDERS:
        raise CredentialError("credential_provider_unsupported")
    return provider


def environment_credential_version(
    fingerprint_key: SecretBuffer,
    *,
    provider: str,
    env_name: str,
    secret: SecretBuffer | str,
) -> str:
    """用设备本地 Fingerprint_Key 计算环境变量凭据的 HMAC credential version。

    输入为 provider、环境变量名与 secret 的规范化组合；输出
    ``hmac-sha256:<64-hex>``。任何输入变化都改变版本。Fingerprint_Key
    只用于 HMAC，不是 Provider API Key；调用方不得把完整 HMAC 展示给用户。
    """

    if fingerprint_key.closed:
        raise CredentialError("credential_secret_closed")
    provider = _provider(provider)
    if not env_name:
        raise CredentialError("credential_reference_invalid")
    key = fingerprint_key.reveal_bytes()
    payload = (
        secret.reveal_bytes() if isinstance(secret, SecretBuffer) else secret.encode("utf-8")
    )
    message = b"".join(
        [
            provider.encode("utf-8"),
            b"\x00",
            env_name.encode("utf-8"),
            b"\x00",
            payload,
        ]
    )
    digest = hmac.new(key, message, hashlib.sha256).hexdigest()
    return f"{CREDENTIAL_VERSION_PREFIX}:{digest}"


def credential_version_reference(version: str) -> str:
    """返回可在人类输出中展示的截断 credential version 引用。

    完整 HMAC 只进入 receipt fingerprint 输入；人类可读输出仅展示前缀，
    避免泄露完整 HMAC。
    """

    if not version.startswith(f"{CREDENTIAL_VERSION_PREFIX}:"):
        raise CredentialError("credential_reference_invalid")
    digest = version[len(f"{CREDENTIAL_VERSION_PREFIX}:") :]
    if len(digest) != 64:
        raise CredentialError("credential_reference_invalid")
    return f"{CREDENTIAL_VERSION_PREFIX}:{digest[:12]}…"


def _generate_fingerprint_key() -> SecretBuffer:
    return SecretBuffer(os.urandom(FINGERPRINT_KEY_BYTES))


def _require_fingerprint_key_length(value: bytes) -> None:
    if not isinstance(value, bytes) or len(value) != FINGERPRINT_KEY_BYTES:
        raise CredentialError("credential_blob_invalid")


class _KeychainAPI(Protocol):
    def copy(
        self, service: str, account: str, *, return_data: bool
    ) -> tuple[int, bytes | None]: ...

    def add(self, service: str, account: str, value: bytes) -> int: ...

    def update(self, service: str, account: str, value: bytes) -> int: ...

    def delete(self, service: str, account: str) -> int: ...


_ERR_SEC_SUCCESS = 0
_ERR_SEC_WR_PERMISSION = -61
_ERR_SEC_USER_CANCELED = -128
_ERR_SEC_DUPLICATE_ITEM = -25299
_ERR_SEC_ITEM_NOT_FOUND = -25300
_ERR_SEC_NOT_AVAILABLE = -25291
_ERR_SEC_READ_ONLY = -25292
_ERR_SEC_AUTH_FAILED = -25293
_ERR_SEC_INVALID_KEYCHAIN = -25295
_ERR_SEC_INTERACTION_NOT_ALLOWED = -25308
_ERR_SEC_INTERACTION_REQUIRED = -25315
_ERR_SEC_DECODE = -26275
_ERR_SEC_MISSING_ENTITLEMENT = -34018


class _SecItemAPI:
    """Security.framework 的最小进程内绑定；不启动子进程或构造命令行。"""

    _SECURITY_PATH = "/System/Library/Frameworks/Security.framework/Security"
    _CORE_FOUNDATION_PATH = (
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    _UTF8_ENCODING = 0x08000100

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise CredentialError("credential_store_unsupported")
        try:
            self._security = ctypes.CDLL(self._SECURITY_PATH)
            self._core = ctypes.CDLL(self._CORE_FOUNDATION_PATH)
            self._configure_functions()
            self._load_constants()
        except (AttributeError, OSError, ValueError) as exc:
            raise CredentialError("credential_store_unsupported") from exc

    @staticmethod
    def _pointer_constant(library: ctypes.CDLL, name: str) -> int:
        value = ctypes.c_void_p.in_dll(library, name).value
        if value is None:
            raise ValueError(f"missing framework constant: {name}")
        return value

    @staticmethod
    def _symbol_address(library: ctypes.CDLL, name: str) -> int:
        return ctypes.addressof(ctypes.c_char.in_dll(library, name))

    def _configure_functions(self) -> None:
        self._security.SecItemCopyMatching.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._security.SecItemCopyMatching.restype = ctypes.c_int32
        self._security.SecItemAdd.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._security.SecItemAdd.restype = ctypes.c_int32
        self._security.SecItemUpdate.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._security.SecItemUpdate.restype = ctypes.c_int32
        self._security.SecItemDelete.argtypes = [ctypes.c_void_p]
        self._security.SecItemDelete.restype = ctypes.c_int32

        self._core.CFStringCreateWithBytes.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_ssize_t,
            ctypes.c_uint32,
            ctypes.c_bool,
        ]
        self._core.CFStringCreateWithBytes.restype = ctypes.c_void_p
        self._core.CFDataCreate.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_ssize_t,
        ]
        self._core.CFDataCreate.restype = ctypes.c_void_p
        self._core.CFDataGetLength.argtypes = [ctypes.c_void_p]
        self._core.CFDataGetLength.restype = ctypes.c_ssize_t
        self._core.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
        self._core.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_uint8)
        self._core.CFDictionaryCreate.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_ssize_t,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._core.CFDictionaryCreate.restype = ctypes.c_void_p
        self._core.CFRelease.argtypes = [ctypes.c_void_p]
        self._core.CFRelease.restype = None

    def _load_constants(self) -> None:
        security_names = (
            "kSecClass",
            "kSecClassGenericPassword",
            "kSecAttrService",
            "kSecAttrAccount",
            "kSecValueData",
            "kSecReturnData",
            "kSecMatchLimit",
            "kSecMatchLimitOne",
        )
        for name in security_names:
            setattr(self, f"_{name}", self._pointer_constant(self._security, name))
        self._true = self._pointer_constant(self._core, "kCFBooleanTrue")
        self._dictionary_key_callbacks = self._symbol_address(
            self._core, "kCFTypeDictionaryKeyCallBacks"
        )
        self._dictionary_value_callbacks = self._symbol_address(
            self._core, "kCFTypeDictionaryValueCallBacks"
        )

    def _string(self, value: str) -> int:
        encoded = value.encode("utf-8")
        raw = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
        reference = self._core.CFStringCreateWithBytes(
            None, raw, len(encoded), self._UTF8_ENCODING, False
        )
        if not reference:
            raise CredentialError("credential_store_failed")
        return reference

    def _data(self, value: bytes) -> int:
        raw = (ctypes.c_uint8 * len(value)).from_buffer_copy(value)
        reference = self._core.CFDataCreate(None, raw, len(value))
        if not reference:
            raise CredentialError("credential_store_failed")
        return reference

    def _dictionary(self, pairs: tuple[tuple[int, int], ...]) -> int:
        keys = (ctypes.c_void_p * len(pairs))(*(key for key, _ in pairs))
        values = (ctypes.c_void_p * len(pairs))(*(value for _, value in pairs))
        reference = self._core.CFDictionaryCreate(
            None,
            keys,
            values,
            len(pairs),
            self._dictionary_key_callbacks,
            self._dictionary_value_callbacks,
        )
        if not reference:
            raise CredentialError("credential_store_failed")
        return reference

    def _query(
        self,
        service: str,
        account: str,
        *extra: tuple[int, int],
    ) -> int:
        service_ref = self._string(service)
        account_ref = self._string(account)
        try:
            return self._dictionary(
                (
                    (self._kSecClass, self._kSecClassGenericPassword),
                    (self._kSecAttrService, service_ref),
                    (self._kSecAttrAccount, account_ref),
                    *extra,
                )
            )
        finally:
            self._core.CFRelease(service_ref)
            self._core.CFRelease(account_ref)

    def copy(
        self, service: str, account: str, *, return_data: bool
    ) -> tuple[int, bytes | None]:
        extra = (
            (
                (self._kSecMatchLimit, self._kSecMatchLimitOne),
                (self._kSecReturnData, self._true),
            )
            if return_data
            else ((self._kSecMatchLimit, self._kSecMatchLimitOne),)
        )
        query = self._query(service, account, *extra)
        result = ctypes.c_void_p()
        try:
            status = self._security.SecItemCopyMatching(query, ctypes.byref(result))
            if status != _ERR_SEC_SUCCESS or not return_data:
                return status, None
            if not result.value:
                return status, b""
            length = self._core.CFDataGetLength(result)
            pointer = self._core.CFDataGetBytePtr(result)
            return status, ctypes.string_at(pointer, length) if length else b""
        finally:
            if result.value:
                self._core.CFRelease(result)
            self._core.CFRelease(query)

    def add(self, service: str, account: str, value: bytes) -> int:
        value_ref = self._data(value)
        try:
            attributes = self._query(
                service, account, (self._kSecValueData, value_ref)
            )
            try:
                return self._security.SecItemAdd(attributes, None)
            finally:
                self._core.CFRelease(attributes)
        finally:
            self._core.CFRelease(value_ref)

    def update(self, service: str, account: str, value: bytes) -> int:
        query = self._query(service, account)
        value_ref = self._data(value)
        try:
            attributes = self._dictionary(((self._kSecValueData, value_ref),))
            try:
                return self._security.SecItemUpdate(query, attributes)
            finally:
                self._core.CFRelease(attributes)
        finally:
            self._core.CFRelease(value_ref)
            self._core.CFRelease(query)

    def delete(self, service: str, account: str) -> int:
        query = self._query(service, account)
        try:
            return self._security.SecItemDelete(query)
        finally:
            self._core.CFRelease(query)


@dataclass
class MacOSKeychainStore:
    api: _KeychainAPI | None = None
    _lock: ClassVar[threading.RLock] = threading.RLock()

    def __post_init__(self) -> None:
        self.api = self.api or _SecItemAPI()

    def reference(self, provider: str) -> str:
        return f"keychain:{KEYCHAIN_SERVICE}/{_provider(provider)}"

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if status == _ERR_SEC_SUCCESS:
            return
        if status == _ERR_SEC_ITEM_NOT_FOUND:
            raise CredentialError("credential_not_found")
        if status in {
            _ERR_SEC_NOT_AVAILABLE,
            _ERR_SEC_INTERACTION_NOT_ALLOWED,
            _ERR_SEC_INTERACTION_REQUIRED,
        }:
            raise CredentialError("credential_store_locked")
        if status in {
            _ERR_SEC_WR_PERMISSION,
            _ERR_SEC_READ_ONLY,
            _ERR_SEC_AUTH_FAILED,
            _ERR_SEC_MISSING_ENTITLEMENT,
            _ERR_SEC_USER_CANCELED,
        }:
            raise CredentialError("credential_store_denied")
        if status in {_ERR_SEC_INVALID_KEYCHAIN, _ERR_SEC_DECODE}:
            raise CredentialError("credential_blob_invalid")
        raise CredentialError("credential_store_failed")

    @staticmethod
    def _secret_bytes(secret: str | SecretBuffer) -> bytes:
        if isinstance(secret, SecretBuffer):
            return secret.reveal_bytes()
        if isinstance(secret, str):
            return secret.encode("utf-8")
        raise CredentialError("credential_input_invalid")

    def status(self, provider: str) -> str:
        account = _provider(provider)
        with self._lock:
            status, _ = self.api.copy(
                KEYCHAIN_SERVICE, account, return_data=False
            )
        if status == _ERR_SEC_ITEM_NOT_FOUND:
            return "missing"
        self._raise_for_status(status)
        return "available"

    def read(self, provider: str) -> str:
        account = _provider(provider)
        with self._lock:
            status, secret = self.api.copy(
                KEYCHAIN_SERVICE, account, return_data=True
            )
        self._raise_for_status(status)
        if not secret:
            raise CredentialError("credential_reference_unavailable")
        try:
            return secret.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CredentialError("credential_blob_invalid") from exc

    def write(self, provider: str, secret: str | SecretBuffer) -> None:
        account = _provider(provider)
        secret_bytes = self._secret_bytes(secret)
        with self._lock:
            status = self.api.add(KEYCHAIN_SERVICE, account, secret_bytes)
            if status == _ERR_SEC_DUPLICATE_ITEM:
                status = self.api.update(KEYCHAIN_SERVICE, account, secret_bytes)
        self._raise_for_status(status)

    def remove(self, provider: str) -> bool:
        account = _provider(provider)
        with self._lock:
            status = self.api.delete(KEYCHAIN_SERVICE, account)
        if status == _ERR_SEC_ITEM_NOT_FOUND:
            return False
        self._raise_for_status(status)
        return True

    def fingerprint_key(self, create: bool = False) -> SecretBuffer | None:
        """读取或按需创建设备本地 Fingerprint_Key。

        Fingerprint_Key 只用于环境变量凭据的 HMAC credential version；
        缺失时不阻断其他 Provider，调用方仅将相关 receipt 判为 stale。
        """

        account = FINGERPRINT_KEY_ACCOUNT
        with self._lock:
            status, value = self.api.copy(
                KEYCHAIN_SERVICE, account, return_data=True
            )
            if status == _ERR_SEC_ITEM_NOT_FOUND:
                if not create:
                    return None
                key = _generate_fingerprint_key()
                add_status = self.api.add(KEYCHAIN_SERVICE, account, key.reveal_bytes())
                if add_status == _ERR_SEC_DUPLICATE_ITEM:
                    # 并发创建：以已存在的 key 为准，丢弃本次生成的随机值。
                    status, value = self.api.copy(
                        KEYCHAIN_SERVICE, account, return_data=True
                    )
                else:
                    self._raise_for_status(add_status)
                    return key
            self._raise_for_status(status)
        if value is None:
            raise CredentialError("credential_reference_unavailable")
        _require_fingerprint_key_length(value)
        return SecretBuffer(value)


@dataclass
class WindowsDPAPIStore:
    """当前用户 DPAPI store；稳定路径只保存受保护 blob。"""

    root: Path
    protect: object | None = None
    unprotect: object | None = None
    acl_enforcer: object | None = None
    acl_checker: object | None = None
    _lock: ClassVar[threading.RLock] = threading.RLock()
    _max_blob_bytes: ClassVar[int] = 16 * 1024 * 1024

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.protect = self.protect or _dpapi_protect
        self.unprotect = self.unprotect or _dpapi_unprotect
        self.acl_enforcer = self.acl_enforcer or _enforce_windows_acl
        self.acl_checker = self.acl_checker or _windows_acl_is_private

    def _path(self, provider: str) -> Path:
        return self.root / f"{_provider(provider)}.dpapi"

    def reference(self, provider: str) -> str:
        return f"host:dpapi/{_provider(provider)}"

    @staticmethod
    def _secret_bytes(secret: str | SecretBuffer) -> bytes:
        if isinstance(secret, SecretBuffer):
            return secret.reveal_bytes()
        if isinstance(secret, str):
            return secret.encode("utf-8")
        raise CredentialError("credential_input_invalid")

    @staticmethod
    def _raise_path_error() -> None:
        raise CredentialError("credential_store_path_invalid")

    def _validate_root(self, *, allow_missing: bool) -> bool:
        if not self.root.exists() and not self.root.is_symlink():
            if allow_missing:
                return False
            self._raise_path_error()
        if self.root.is_symlink() or not self.root.is_dir():
            self._raise_path_error()
        return True

    def _validate_file(self, path: Path, *, allow_missing: bool) -> bool:
        if not path.exists() and not path.is_symlink():
            if allow_missing:
                return False
            raise CredentialError("credential_not_found")
        if path.is_symlink() or not path.is_file():
            self._raise_path_error()
        return True

    def _require_private_acl(self, path: Path) -> None:
        try:
            private = bool(self.acl_checker(path))
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialError("credential_store_acl_failed") from exc
        if not private:
            raise CredentialError("credential_store_acl_too_broad")

    def _read_blob(self, provider: str) -> bytes:
        path = self._path(provider)
        if not self._validate_root(allow_missing=True):
            raise CredentialError("credential_not_found")
        self._require_private_acl(self.root)
        self._validate_file(path, allow_missing=False)
        self._require_private_acl(path)
        try:
            blob = path.read_bytes()
        except PermissionError as exc:
            raise CredentialError("credential_store_denied") from exc
        except OSError as exc:
            raise CredentialError("credential_store_failed") from exc
        if not blob or len(blob) > self._max_blob_bytes:
            raise CredentialError("credential_blob_invalid")
        return blob

    def status(self, provider: str) -> str:
        path = self._path(provider)
        with self._lock:
            if not self._validate_root(allow_missing=True):
                return "missing"
            self._require_private_acl(self.root)
            if not self._validate_file(path, allow_missing=True):
                return "missing"
            self.read(provider)
            return "available"

    def read(self, provider: str) -> str:
        with self._lock:
            blob = self._read_blob(provider)
            try:
                cleartext = self.unprotect(blob)
                if not isinstance(cleartext, bytes) or not cleartext:
                    raise CredentialError("credential_blob_invalid")
                return cleartext.decode("utf-8")
            except CredentialError:
                raise
            except (UnicodeDecodeError, ValueError, TypeError) as exc:
                raise CredentialError("credential_blob_invalid") from exc
            except Exception as exc:
                raise CredentialError("credential_dpapi_decrypt_failed") from exc

    def _ensure_private_root(self) -> None:
        try:
            self.root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                self.root.mkdir(mode=0o700)
            except FileExistsError:
                pass
            self._validate_root(allow_missing=False)
            self.acl_enforcer(self.root, True)
            self._require_private_acl(self.root)
        except CredentialError:
            raise
        except PermissionError as exc:
            raise CredentialError("credential_store_denied") from exc
        except OSError as exc:
            raise CredentialError("credential_store_failed") from exc
        except Exception as exc:
            raise CredentialError("credential_store_acl_failed") from exc

    def write(self, provider: str, secret: str | SecretBuffer) -> None:
        provider = _provider(provider)
        try:
            encrypted = self.protect(self._secret_bytes(secret))
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialError("credential_dpapi_encrypt_failed") from exc
        if not isinstance(encrypted, bytes) or not encrypted:
            raise CredentialError("credential_dpapi_encrypt_failed")

        with self._lock:
            self._ensure_private_root()
            path = self._path(provider)
            if self._validate_file(path, allow_missing=True):
                self._require_private_acl(path)
            temporary = self.root / f".{provider}.{os.urandom(16).hex()}.tmp"
            descriptor: int | None = None
            replaced = False
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                flags |= getattr(os, "O_BINARY", 0)
                descriptor = os.open(temporary, flags, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    descriptor = None
                    stream.write(encrypted)
                    stream.flush()
                    os.fsync(stream.fileno())
                self.acl_enforcer(temporary, False)
                self._validate_file(temporary, allow_missing=False)
                self._require_private_acl(temporary)
                os.replace(temporary, path)
                replaced = True
                self._validate_file(path, allow_missing=False)
                try:
                    self._require_private_acl(self.root)
                    self._require_private_acl(path)
                except CredentialError:
                    path.unlink(missing_ok=True)
                    raise
            except CredentialError:
                raise
            except PermissionError as exc:
                raise CredentialError("credential_store_denied") from exc
            except OSError as exc:
                raise CredentialError("credential_store_failed") from exc
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                if not replaced:
                    temporary.unlink(missing_ok=True)

    def remove(self, provider: str) -> bool:
        path = self._path(provider)
        with self._lock:
            if not self._validate_root(allow_missing=True):
                return False
            self._require_private_acl(self.root)
            if not self._validate_file(path, allow_missing=True):
                return False
            self._require_private_acl(path)
            try:
                path.unlink()
            except PermissionError as exc:
                raise CredentialError("credential_store_denied") from exc
            except OSError as exc:
                raise CredentialError("credential_store_failed") from exc
            return True

    def fingerprint_key(self, create: bool = False) -> SecretBuffer | None:
        """读取或按需创建当前用户 DPAPI 保护的 Fingerprint_Key。"""

        path = self.root / f"{FINGERPRINT_KEY_ACCOUNT}.dpapi"
        with self._lock:
            if not self._validate_root(allow_missing=True):
                if not create:
                    return None
                self._ensure_private_root()
            else:
                self._require_private_acl(self.root)
            if self._validate_file(path, allow_missing=True):
                self._require_private_acl(path)
                blob = self._read_blob_file(path)
                try:
                    cleartext = self.unprotect(blob)
                except CredentialError:
                    raise
                except Exception as exc:
                    raise CredentialError("credential_dpapi_decrypt_failed") from exc
                if not isinstance(cleartext, bytes):
                    raise CredentialError("credential_blob_invalid")
                _require_fingerprint_key_length(cleartext)
                return SecretBuffer(cleartext)
            if not create:
                return None
            key = _generate_fingerprint_key()
            self._write_blob(path, key.reveal_bytes())
            return key

    def _read_blob_file(self, path: Path) -> bytes:
        try:
            blob = path.read_bytes()
        except PermissionError as exc:
            raise CredentialError("credential_store_denied") from exc
        except OSError as exc:
            raise CredentialError("credential_store_failed") from exc
        if not blob or len(blob) > self._max_blob_bytes:
            raise CredentialError("credential_blob_invalid")
        return blob

    def _write_blob(self, path: Path, cleartext: bytes) -> None:
        try:
            encrypted = self.protect(cleartext)
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialError("credential_dpapi_encrypt_failed") from exc
        if not isinstance(encrypted, bytes) or not encrypted:
            raise CredentialError("credential_dpapi_encrypt_failed")
        self._atomic_replace(path, encrypted)

    def _atomic_replace(self, path: Path, encrypted: bytes) -> None:
        temporary = self.root / f".{path.name}.{os.urandom(16).hex()}.tmp"
        descriptor: int | None = None
        replaced = False
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_BINARY", 0)
            descriptor = os.open(temporary, flags, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = None
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            self.acl_enforcer(temporary, False)
            self._validate_file(temporary, allow_missing=False)
            self._require_private_acl(temporary)
            os.replace(temporary, path)
            replaced = True
            self._validate_file(path, allow_missing=False)
            try:
                self._require_private_acl(self.root)
                self._require_private_acl(path)
            except CredentialError:
                path.unlink(missing_ok=True)
                raise
        except CredentialError:
            raise
        except PermissionError as exc:
            raise CredentialError("credential_store_denied") from exc
        except OSError as exc:
            raise CredentialError("credential_store_failed") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if not replaced:
                temporary.unlink(missing_ok=True)


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

    def fingerprint_key(self, create: bool = False) -> SecretBuffer | None:
        # 不支持平台没有受保护的 Fingerprint_Key；调用方仅将相关 receipt
        # 判为 stale，不得创建明文替代。
        return None


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

    def environment_version(self, provider: str) -> str | None:
        """返回仅供 receipt fingerprint 使用的环境凭据版本。"""

        provider = _provider(provider)
        env_name = PROVIDERS[provider]
        value = self.environ.get(env_name)
        if not value:
            return None
        fingerprint_key = self.store.fingerprint_key(create=False)
        if fingerprint_key is None:
            return None
        secret = SecretBuffer(value)
        try:
            return environment_credential_version(
                fingerprint_key,
                provider=provider,
                env_name=env_name,
                secret=secret,
            )
        finally:
            secret.close()
            fingerprint_key.close()

    def add(self, provider: str, *, overwrite: bool, input_stream=None, reader=None) -> dict[str, object]:
        provider = _provider(provider)
        stream = input_stream or sys.stdin
        if not stream.isatty():
            raise CredentialError("credential_tty_required")
        if self.store.status(provider) == "available" and not overwrite:
            raise CredentialError("credential_overwrite_confirmation_required")
        secret = (reader or getpass.getpass)(f"请输入 {provider} 的访问凭据：")
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


_CRYPTPROTECT_UI_FORBIDDEN = 0x00000001
_CRYPTPROTECT_LOCAL_MACHINE = 0x00000004
_DPAPI_CURRENT_USER_FLAGS = _CRYPTPROTECT_UI_FORBIDDEN
_DPAPI_DESCRIPTION = "leo-ppt-generator current-user credential"


class _DPAPIAPI(Protocol):
    def protect(self, value: bytes, *, flags: int) -> bytes: ...

    def unprotect(self, value: bytes, *, flags: int) -> bytes: ...


class _CtypesDPAPIAPI:
    """进程内 DPAPI binding；绝不启用 machine scope。"""

    def __init__(self) -> None:
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            raise CredentialError("credential_store_unsupported")
        self._crypt32 = win_dll("Crypt32.dll", use_last_error=True)
        self._kernel32 = win_dll("Kernel32.dll", use_last_error=True)
        self._crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self._kernel32.LocalFree.restype = ctypes.c_void_p

    @staticmethod
    def _last_error(operation: str) -> None:
        getter = getattr(ctypes, "get_last_error", None)
        code = int(getter()) if getter is not None else 0
        if code in {5, 1314}:
            raise CredentialError("credential_store_denied")
        if code in {1245, 0x8009000B}:
            raise CredentialError("credential_store_locked")
        if operation == "unprotect":
            # 损坏 blob、其他用户或 machine-scope blob 均不得被当前用户接受。
            raise CredentialError("credential_blob_invalid")
        raise CredentialError("credential_dpapi_encrypt_failed")

    def _copy_output(self, output: _DataBlob) -> bytes:
        if not output.pbData or not output.cbData:
            raise CredentialError("credential_blob_invalid")
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            self._kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))

    def protect(self, value: bytes, *, flags: int) -> bytes:
        source, source_buffer = _blob(value)
        output = _DataBlob()
        try:
            succeeded = self._crypt32.CryptProtectData(
                ctypes.byref(source),
                _DPAPI_DESCRIPTION,
                None,
                None,
                None,
                flags,
                ctypes.byref(output),
            )
            if not succeeded:
                self._last_error("protect")
            return self._copy_output(output)
        finally:
            del source_buffer

    def unprotect(self, value: bytes, *, flags: int) -> bytes:
        source, source_buffer = _blob(value)
        output = _DataBlob()
        try:
            succeeded = self._crypt32.CryptUnprotectData(
                ctypes.byref(source),
                None,
                None,
                None,
                None,
                flags,
                ctypes.byref(output),
            )
            if not succeeded:
                self._last_error("unprotect")
            return self._copy_output(output)
        finally:
            del source_buffer


def _current_user_dpapi_flags() -> int:
    flags = _DPAPI_CURRENT_USER_FLAGS
    if flags & _CRYPTPROTECT_LOCAL_MACHINE:
        raise CredentialError("credential_dpapi_machine_scope_forbidden")
    return flags


def _dpapi_protect(value: bytes, api: _DPAPIAPI | None = None) -> bytes:
    if not value:
        raise CredentialError("credential_empty")
    return (api or _CtypesDPAPIAPI()).protect(
        value,
        flags=_current_user_dpapi_flags(),
    )


def _dpapi_unprotect(value: bytes, api: _DPAPIAPI | None = None) -> bytes:
    if not value:
        raise CredentialError("credential_blob_invalid")
    return (api or _CtypesDPAPIAPI()).unprotect(
        value,
        flags=_current_user_dpapi_flags(),
    )


def _windows_current_identity() -> tuple[str, str]:
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CredentialError("credential_store_acl_failed")
    fields = result.stdout.strip().strip('"').split('","')
    if len(fields) != 2 or not fields[0] or not fields[1].startswith("S-1-"):
        raise CredentialError("credential_store_acl_failed")
    return fields[0], fields[1]


def _enforce_windows_acl(path: Path, directory: bool) -> None:
    _account, sid = _windows_current_identity()
    inheritance = "(OI)(CI)" if directory else ""
    grant = f"*{sid}:{inheritance}F"
    result = subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", grant, "/c"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CredentialError("credential_store_acl_failed")


def _windows_acl_is_private(path: Path) -> bool:
    account, sid = _windows_current_identity()
    result = subprocess.run(
        ["icacls", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CredentialError("credential_store_acl_failed")
    lowered = result.stdout.casefold()
    forbidden_principals = (
        "everyone",
        "authenticated users",
        "builtin\\users",
        "s-1-1-0",
        "s-1-5-11",
        "s-1-5-32-545",
    )
    if any(principal in lowered for principal in forbidden_principals):
        return False
    current_user_markers = (account.casefold(), sid.casefold())
    return any(marker in lowered for marker in current_user_markers)
