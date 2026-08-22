"""首次使用 setup 的无状态协调与同源输出。"""

from __future__ import annotations

import json
from typing import Any

from .application.routes import ROUTES
from .config.backend_contract import BackendContractError, BackendRegistry
from .observability import primary_action_for

SETUP_PROTOCOL = "leo-ppt-setup/v1"
SETUP_SCHEMA_VERSION = 1
HOST_CAPABILITY_STATUSES = frozenset({"available", "unavailable", "unknown"})
TASK_IMAGE_CAPABILITIES = frozenset({"mask", "reference"})
OCR_REQUIREMENTS = frozenset({"not_required", "editable_text_hints"})


class SetupContractError(ValueError):
    reason_code = "setup_contract_error"


def doctor_report(route: str | None) -> dict[str, Any]:
    """延迟导入 doctor owner，避免 setup 与 CLI 的模块环。"""

    from .cli import doctor_report as build_doctor_report

    return build_doctor_report(route)


def _route_capabilities(route: str) -> list[str]:
    return ["generate"] if route == "generate" else ["edit"]


def _provider_options(
    doctor: dict[str, Any],
    *,
    required: set[str],
    host_imagegen: str,
    selected_provider: str | None,
) -> list[dict[str, Any]]:
    registry = BackendRegistry.default()
    options: list[dict[str, Any]] = []
    references = doctor.get("credential_references", {})
    if not isinstance(references, dict):
        references = {}
    for backend in registry.candidates(required):
        provider = backend.name
        if provider == "builtin-imagegen" and host_imagegen == "unavailable":
            continue
        credential = references.get(provider, {})
        if not isinstance(credential, dict):
            credential = {}
        credential_status = str(credential.get("status", "unknown"))
        if provider == "builtin-imagegen":
            credential_status = host_imagegen
        evidence_refs = credential.get("evidence_refs", doctor.get("evidence_refs", []))
        if not isinstance(evidence_refs, list):
            evidence_refs = []
        is_confirmed = provider == selected_provider
        options.append(
            {
                "provider": provider,
                "capabilities": sorted(backend.capabilities),
                "credential_status": credential_status,
                "credential_reference_type": str(
                    credential.get(
                        "reference_type",
                        "host-managed"
                        if backend.backend_kind == "builtin-imagegen"
                        else "unknown",
                    )
                ),
                "evidence_refs": [str(value) for value in evidence_refs],
                "execution_owner": (
                    "agent-host"
                    if backend.backend_kind == "builtin-imagegen"
                    else "runtime"
                ),
                "recommended": (
                    provider == "builtin-imagegen" and host_imagegen == "available"
                )
                or (is_confirmed and credential_status == "available"),
                "recommendation_reason": (
                    "host_capability_confirmed"
                    if provider == "builtin-imagegen" and host_imagegen == "available"
                    else "user_confirmed"
                    if is_confirmed and credential_status == "available"
                    else "credential_available"
                    if credential_status == "available"
                    else "not_ready"
                ),
            }
        )
    return sorted(
        options,
        key=lambda option: (
            0 if option["recommended"] else 1,
            0 if option["credential_status"] == "available" else 1,
        ),
    )


def _optional_services(
    doctor: dict[str, Any], *, route: str, ocr_requirement: str
) -> list[dict[str, Any]]:
    if route == "generate" or ocr_requirement != "editable_text_hints":
        return []
    references = doctor.get("credential_references", {})
    credential = references.get("paddleocr", {}) if isinstance(references, dict) else {}
    if not isinstance(credential, dict):
        credential = {}
    evidence_refs = credential.get("evidence_refs", doctor.get("evidence_refs", []))
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    return [
        {
            "service": "paddleocr",
            "purpose": "editable_text_hints",
            "credential_status": str(credential.get("status", "unknown")),
            "credential_reference_type": str(
                credential.get("reference_type", "unknown")
            ),
            "required": False,
            "fallback": "builtin-ink",
            "evidence_refs": [str(value) for value in evidence_refs],
        }
    ]


def _base_report(
    route: str,
    *,
    host_imagegen: str,
    doctor: dict[str, Any],
    options: list[dict[str, Any]],
    route_capabilities: list[str],
    optional_services: list[dict[str, Any]],
) -> dict[str, Any]:
    local_status = doctor.get("readiness_summary", {}).get(
        "local_mechanism", "blocked" if doctor.get("status") == "blocked" else "ready"
    )
    evidence_refs = doctor.get("evidence_refs", [])
    return {
        "protocol": SETUP_PROTOCOL,
        "schema_version": SETUP_SCHEMA_VERSION,
        "status": "blocked",
        "reason_code": "setup_contract_error",
        "route": route,
        "route_capabilities": route_capabilities,
        "local_mechanism": {
            "status": local_status,
            "reason_code": str(doctor.get("reason_code", "unknown")),
            "evidence_refs": list(evidence_refs) if isinstance(evidence_refs, list) else [],
        },
        "host_capabilities": {"image_generation": host_imagegen},
        "provider_options": options,
        "optional_services": optional_services,
        "selected_provider": None,
        "primary_action": None,
        "details": {
            "warnings": list(doctor.get("warnings", [])),
            "alternatives": [],
            "owner_reason_codes": [str(doctor.get("reason_code", "unknown"))],
            "evidence_refs": list(evidence_refs) if isinstance(evidence_refs, list) else [],
        },
    }


def _set_outcome(
    report: dict[str, Any],
    *,
    status: str,
    reason_code: str,
    selected_provider: str | None = None,
    replacements: dict[str, str] | None = None,
) -> dict[str, Any]:
    report["status"] = status
    report["reason_code"] = reason_code
    report["selected_provider"] = selected_provider
    report["primary_action"] = (
        None
        if status == "ready"
        else primary_action_for(reason_code, **(replacements or {}))
    )
    return validate_setup_report(report)


def build_setup_report(
    route: str,
    *,
    host_imagegen: str = "unknown",
    selected_provider: str | None = None,
    required_image_capabilities: set[str] | None = None,
    ocr_requirement: str = "not_required",
) -> dict[str, Any]:
    """组合 doctor、registry 与宿主声明，不写入任何 readiness 状态。"""

    if host_imagegen not in HOST_CAPABILITY_STATUSES:
        raise SetupContractError("host_image_capability_invalid")
    task_capabilities = required_image_capabilities or set()
    if not isinstance(task_capabilities, set) or not task_capabilities.issubset(
        TASK_IMAGE_CAPABILITIES
    ):
        raise SetupContractError("image_capability_requirement_invalid")
    if ocr_requirement not in OCR_REQUIREMENTS:
        raise SetupContractError("ocr_requirement_invalid")
    doctor = doctor_report(route)
    route_capabilities = _route_capabilities(route) if route in ROUTES else []
    required = set(route_capabilities) | task_capabilities
    reported_capabilities = [
        *route_capabilities,
        *sorted(task_capabilities - set(route_capabilities)),
    ]
    options = _provider_options(
        doctor,
        required=required,
        host_imagegen=host_imagegen,
        selected_provider=selected_provider,
    )
    optional_services = _optional_services(
        doctor, route=route, ocr_requirement=ocr_requirement
    )
    report = _base_report(
        route,
        host_imagegen=host_imagegen,
        doctor=doctor,
        options=options,
        route_capabilities=reported_capabilities,
        optional_services=optional_services,
    )
    replacements = {"route": route, "provider": selected_provider or "provider"}

    if route not in ROUTES or doctor.get("reason_code") == "unknown_route":
        return _set_outcome(
            report,
            status="blocked",
            reason_code="unknown_route",
            replacements=replacements,
        )
    if doctor.get("status") == "blocked":
        return _set_outcome(
            report,
            status="blocked",
            reason_code="setup_local_mechanism_blocked",
            replacements=replacements,
        )
    if any(
        option["credential_status"] in {"resolver_unavailable", "unavailable_resolver"}
        for option in options
        if option["provider"] != "builtin-imagegen"
    ):
        return _set_outcome(
            report,
            status="action_required",
            reason_code="credential_resolver_unavailable",
            replacements=replacements,
        )

    by_name = {option["provider"]: option for option in options}
    if selected_provider is not None:
        if selected_provider == "builtin-imagegen" and host_imagegen != "available":
            reason = (
                "host_image_capability_unknown"
                if host_imagegen == "unknown"
                else "host_image_capability_unavailable"
            )
            return _set_outcome(
                report,
                status="action_required",
                reason_code=reason,
                replacements=replacements,
            )
        selected = by_name.get(selected_provider)
        if selected is None:
            try:
                BackendRegistry.default().select(selected_provider, required=set())
            except BackendContractError:
                reason = "unknown_backend"
                selected_replacements = replacements
            else:
                reason = "provider_capability_required"
                capable_external = [
                    option["provider"]
                    for option in options
                    if option["provider"] != "builtin-imagegen"
                ]
                selected_replacements = {
                    **replacements,
                    "provider": "|".join(capable_external) or "capable-provider",
                }
            return _set_outcome(
                report,
                status="blocked",
                reason_code=reason,
                replacements=selected_replacements,
            )
        if selected["credential_status"] != "available":
            reason = (
                "host_image_capability_unknown"
                if selected_provider == "builtin-imagegen" and host_imagegen == "unknown"
                else "host_image_capability_unavailable"
                if selected_provider == "builtin-imagegen"
                else "selected_provider_unavailable"
            )
            return _set_outcome(
                report,
                status="action_required",
                reason_code=reason,
                replacements=replacements,
            )
        return _set_outcome(
            report,
            status="ready",
            reason_code="setup_ready",
            selected_provider=selected_provider,
            replacements=replacements,
        )

    if host_imagegen == "available":
        return _set_outcome(
            report,
            status="ready",
            reason_code="setup_ready",
            selected_provider="builtin-imagegen",
            replacements=replacements,
        )
    if host_imagegen == "unknown":
        return _set_outcome(
            report,
            status="action_required",
            reason_code="host_image_capability_unknown",
            replacements=replacements,
        )

    external = [
        option
        for option in options
        if option["provider"] != "builtin-imagegen"
        and option["credential_status"] == "available"
    ]
    if not external:
        references = doctor.get("credential_references", {})
        available_but_incapable = []
        if isinstance(references, dict):
            capable = {backend.name for backend in BackendRegistry.default().candidates(required)}
            available_but_incapable = [
                provider
                for provider, value in references.items()
                if provider in {"openai", "atlascloud"}
                and provider not in capable
                and isinstance(value, dict)
                and value.get("status") == "available"
            ]
        if available_but_incapable:
            capable_external = [
                option["provider"]
                for option in options
                if option["provider"] != "builtin-imagegen"
            ]
            return _set_outcome(
                report,
                status="action_required",
                reason_code="provider_capability_required",
                replacements={
                    **replacements,
                    "provider": "|".join(capable_external) or "capable-provider",
                },
            )
        return _set_outcome(
            report,
            status="action_required",
            reason_code="image_provider_configuration_required",
            replacements=replacements,
        )
    reason = (
        "provider_confirmation_required"
        if len(external) == 1
        else "provider_choice_required"
    )
    return _set_outcome(
        report,
        status="choice_required",
        reason_code=reason,
        replacements={
            **replacements,
            "provider": external[0]["provider"] if len(external) == 1 else "openai|atlascloud",
        },
    )


def validate_setup_report(report: dict[str, Any]) -> dict[str, Any]:
    """执行 runtime 必需的 fail-closed v1 不变量；完整结构由 JSON Schema 验证。"""

    if report.get("schema_version") != SETUP_SCHEMA_VERSION:
        raise SetupContractError("setup_schema_version_unsupported")
    status = report.get("status")
    if status not in {"ready", "choice_required", "action_required", "blocked"}:
        raise SetupContractError("setup_status_invalid")
    action = report.get("primary_action")
    if status == "ready" and action is not None:
        raise SetupContractError("setup_primary_action_unexpected")
    if status != "ready" and not isinstance(action, dict):
        raise SetupContractError("setup_primary_action_required")
    return report


def render_setup_json(report: dict[str, Any]) -> str:
    return json.dumps(validate_setup_report(report), ensure_ascii=False, sort_keys=True)


def render_setup_report(report: dict[str, Any]) -> str:
    value = validate_setup_report(report)
    lines = [
        f"状态: {value['status']}",
        f"原因: {value['reason_code']}",
        f"路线: {value['route']}",
        f"宿主图片能力: {value['host_capabilities']['image_generation']}",
    ]
    selected = value.get("selected_provider")
    if selected:
        lines.append(f"已选 Provider: {selected}")
    lines.append("Provider:")
    lines.extend(
        f"- {option['provider']}: {option['credential_status']}"
        for option in value["provider_options"]
    )
    if value["optional_services"]:
        lines.append("可选服务:")
        lines.extend(
            f"- {service['service']}: {service['credential_status']}，fallback={service['fallback']}"
            for service in value["optional_services"]
        )
    if value.get("primary_action"):
        lines.append(f"下一步: {value['primary_action']['command']}")
        lines.append(f"复验: {value['primary_action']['verification']}")
    return "\n".join(lines)
