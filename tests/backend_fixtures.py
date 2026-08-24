from __future__ import annotations


def backend_contract(provider: str = "fixture", *, mode: str = "generate") -> dict:
    definitions = {
        "fixture": {
            "backend_kind": "openai-compatible",
            "credential_source": "host-managed",
            "capabilities": {
                "generate": True,
                "edit": True,
                "mask": False,
                "max_reference_images": 4,
                "execution_owner": "runtime",
            },
        },
        "openai": {
            "backend_kind": "openai-compatible",
            "credential_source": "environment-reference",
            "credential_ref": "env:OPENAI_API_KEY",
            "capabilities": {
                "generate": True,
                "edit": True,
                "mask": True,
                "max_reference_images": 16,
                "execution_owner": "runtime",
            },
        },
        "openai-compatible": {
            "backend_kind": "openai-compatible",
            "credential_source": "environment-reference",
            "credential_ref": "env:OPENAI_API_KEY",
            "endpoint_origin": "https://proxy.example.com/v1",
            "capabilities": {
                "generate": True,
                "edit": True,
                "mask": True,
                "max_reference_images": 16,
                "execution_owner": "runtime",
            },
        },
        "atlascloud": {
            "backend_kind": "atlascloud",
            "credential_source": "environment-reference",
            "credential_ref": "env:ATLASCLOUD_API_KEY",
            "capabilities": {
                "generate": True,
                "edit": True,
                "mask": False,
                "max_reference_images": 4,
                "execution_owner": "runtime",
            },
        },
        "builtin-imagegen": {
            "backend_kind": "builtin-imagegen",
            "credential_source": "host-managed",
            "capabilities": {
                "generate": True,
                "edit": True,
                "mask": True,
                "max_reference_images": 16,
                "execution_owner": "agent-host",
            },
        },
    }
    return {
        "schema_version": 1,
        "provider": provider,
        "model": "fixture-model" if provider == "fixture" else "gpt-image-2",
        "mode": mode,
        "selection_source": "user-confirmed",
        **definitions[provider],
    }
