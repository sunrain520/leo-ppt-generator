from __future__ import annotations

import pytest

from leo_ppt_generator.templates import (
    TemplateError,
    compose_layout,
    compose_style,
    list_templates,
    load_image_type,
    load_layout,
    load_mode,
    load_rendering,
    paired_rendering,
)


def test_load_rendering_extracts_paste_ready_paragraph():
    rendering = load_rendering("玻璃拟态")
    assert rendering["paste_ready"].startswith("Modern glassmorphism aesthetic")
    assert rendering["positioning"]
    assert "线条质量" in rendering["line_texture_depth"]


def test_load_layout_matches_number_name_and_stem():
    for probe in ("P6", "KPI Tower", "06_KPI_Tower"):
        layout = load_layout(probe)
        assert "KPI Tower" in layout["name"]
        assert layout["skeleton"]
        assert layout["purpose"]


def test_load_layout_missing_raises():
    with pytest.raises(TemplateError, match="layout_not_found"):
        load_layout("no-such-layout")


def test_load_image_type_uses_first_paragraph_as_positioning():
    image_type = load_image_type("漏斗图")
    assert image_type["positioning"].startswith("上宽下窄")
    assert image_type["skeleton"]


def test_load_mode_extracts_argument_skeleton():
    mode = load_mode("结论先行金字塔")
    assert "结论先行" in mode["skeleton"]


def test_paired_rendering_maps_visual_style():
    assert paired_rendering("玻璃拟态风") == "玻璃拟态"


def test_compose_style_merges_brief_rendering_and_mode():
    composed = compose_style("玻璃拟态风", mode="结论先行金字塔")
    assert composed["name"] == "玻璃拟态风"
    assert composed["visual_direction"]
    assert composed["color_palette"]
    assert composed["image_rendering"].startswith("Modern glassmorphism")
    assert "结论先行" in composed["mode"]


def test_compose_style_is_deterministic():
    first = compose_style("玻璃拟态风", mode="结论先行金字塔")
    second = compose_style("玻璃拟态风", mode="结论先行金字塔")
    assert first == second


def test_compose_layout_merges_skeleton_and_image_type():
    composed = compose_layout("P6", image_type="漏斗图")
    assert "KPI Tower" in composed["layout_name"]
    assert composed["skeleton"]
    assert composed["image_type"]


def test_list_templates_enumerates_axes():
    templates = list_templates()
    assert len(templates["renderings"]) == 20
    assert len(templates["layouts"]) == 22
    assert len(templates["image_types"]) == 11
    assert len(templates["modes"]) == 5
