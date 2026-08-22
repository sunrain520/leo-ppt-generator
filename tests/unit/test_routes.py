from __future__ import annotations

import zipfile

import pytest
from leo_ppt_generator.application.routes import (
    ROUTES,
    RouteContractError,
    classify_input,
    route_definition,
    select_route,
    validate_input_content,
)
from PIL import Image
from pptx import Presentation


@pytest.mark.parametrize(
    ("kind", "editable", "upgrade", "selected", "expected"),
    [
        ("content", False, False, (), "generate"),
        ("image", True, False, (), "direct-editable"),
        ("image-deck", True, True, (), "upgrade-full"),
        ("image-deck", True, True, (1, 3), "upgrade-selected"),
    ],
)
def test_selects_each_finite_route(kind, editable, upgrade, selected, expected):
    assert select_route(kind, editable=editable, upgrade=upgrade, selected_pages=selected) == expected


def test_route_steps_are_code_owned_and_unknown_values_fail_closed():
    assert set(ROUTES) == {"generate", "direct-editable", "upgrade-full", "upgrade-selected"}
    assert route_definition("upgrade-selected").steps[-1] == "hybrid.assemble"
    with pytest.raises(RouteContractError, match="unknown_route"):
        route_definition("runtime-injected")
    with pytest.raises(RouteContractError, match="unknown_step"):
        route_definition("generate").require_step("shell.eval")


def test_classify_input_rejects_untrusted_office_before_routing(tmp_path):
    bad = tmp_path / "deck.pptx"
    bad.write_bytes(b"not-a-zip")
    with pytest.raises(RouteContractError, match="untrusted_office_input"):
        classify_input(bad, office_trusted=False)


def test_classify_supported_inputs_and_trusted_office(tmp_path):
    markdown = tmp_path / "content.md"
    markdown.write_text("# deck", encoding="utf-8")
    image = tmp_path / "page.png"
    image.write_bytes(b"fixture")
    pdf = tmp_path / "deck.pdf"
    pdf.write_bytes(b"fixture")
    office = tmp_path / "deck.pptx"
    Presentation().save(office)
    assert classify_input(markdown) == "content"
    assert classify_input(image) == "image"
    assert classify_input(pdf) == "pdf"
    assert classify_input(office, office_trusted=True) == "office"
    with pytest.raises(RouteContractError, match="unsupported_input"):
        classify_input(tmp_path / "unknown.bin")
    with pytest.raises(RouteContractError, match="route_confirmation_required"):
        select_route("content", editable=True, upgrade=True)


@pytest.mark.parametrize("active_member", ["ppt/vbaProject.bin", "ppt/embeddings/object.bin"])
def test_office_trust_does_not_bypass_active_content_preflight(tmp_path, active_member):
    office = tmp_path / "active.pptx"
    with zipfile.ZipFile(office, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml", "<p:presentation/>")
        archive.writestr(active_member, b"active")

    with pytest.raises(RouteContractError, match="untrusted_office_input"):
        classify_input(office, office_trusted=True)


def test_input_content_validation_accepts_real_signatures_and_rejects_mismatch(tmp_path):
    content = tmp_path / "content.md"
    content.write_text("# deck", encoding="utf-8")
    image = tmp_path / "page.png"
    Image.new("RGB", (16, 9), "white").save(image)
    pdf = tmp_path / "deck.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    office = tmp_path / "deck.pptx"
    Presentation().save(office)
    for path, kind in ((content, "content"), (image, "image"), (pdf, "pdf"), (office, "office")):
        validate_input_content(path, kind)

    bad_content = tmp_path / "bad.md"
    bad_content.write_bytes(b"text\x00payload")
    bad_image = tmp_path / "bad.png"
    bad_image.write_bytes(b"not-an-image")
    bad_pdf = tmp_path / "bad.pdf"
    bad_pdf.write_bytes(b"not-a-pdf")
    for path, kind in ((bad_content, "content"), (bad_image, "image"), (bad_pdf, "pdf")):
        with pytest.raises(RouteContractError, match="input_type_mismatch"):
            validate_input_content(path, kind)
