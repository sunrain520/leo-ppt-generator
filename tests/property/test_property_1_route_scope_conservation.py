from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from hypothesis import given, settings, strategies as st
from leo_ppt_generator.application.routes import ROUTES, TASK_CAPABILITIES
from leo_ppt_generator.config.models import ArtifactDigest, Capability, CapabilityEvidence, ProviderName, RouteName, VerificationSource
from leo_ppt_generator.config.readiness import build_readiness_scope
from leo_ppt_generator.config.receipt_store import ReceiptInspection

PROPERTY_SETTINGS = settings(
    max_examples=128,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
NOW = datetime(2026, 1, 8, tzinfo=UTC)


def _evidence(capability: Capability) -> CapabilityEvidence:
    return CapabilityEvidence(
        capability=capability,
        verified_at=NOW,
        expires_at=NOW + timedelta(days=7),
        operation_id=f"operation-{capability.value}",
        verification_source=VerificationSource.BUSINESS_REQUEST,
        artifact_digest=ArtifactDigest(
            sha256=hashlib.sha256(capability.value.encode()).hexdigest(),
            media_type="image/png",
            size_bytes=128,
        ),
    )


@PROPERTY_SETTINGS
@given(
    route=st.one_of(st.none(), st.sampled_from(tuple(RouteName))),
    task_capabilities=st.frozensets(st.sampled_from(tuple(sorted(TASK_CAPABILITIES, key=lambda item: item.value)))),
    evidenced_capabilities=st.frozensets(st.sampled_from(tuple(Capability))),
)
def test_property_1_route_scope_conservation(route, task_capabilities, evidenced_capabilities):
    """**Validates: Requirements 2.16, 6.19, 16.2, 16.3, 16.4, 16.8**"""
    selected_route = RouteName.GENERATE if route is None else route
    receipt = ReceiptInspection(
        provider=ProviderName.OPENAI,
        status="valid",
        reason_code="verification_receipt_valid",
        fingerprint_matches=True,
        valid_evidence={item: _evidence(item) for item in evidenced_capabilities},
    )
    scope = build_readiness_scope(route=route, task_capabilities=task_capabilities, receipt=receipt)
    required = ROUTES[selected_route.value].base_capabilities | task_capabilities

    assert scope.route is selected_route
    assert scope.required_capabilities == required
    assert scope.verified_capabilities == required & evidenced_capabilities
    assert scope.missing_capabilities == required - scope.verified_capabilities
    assert scope.verified_capabilities.isdisjoint(scope.missing_capabilities)
    assert scope.verified_capabilities | scope.missing_capabilities == required
