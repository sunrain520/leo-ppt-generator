"""模板知识库加载器：把分节轴文档（论证模式/信息图类型/图片渲染/版式库）结构化
读取，并组合成 deck_spec 的确定性注入内容。

The reference library has two kinds of markdown: full style briefs (embedded
JSON, handled by styles.py) and prose axis documents (论证模式、信息图类型、
图片渲染、结构布局、品牌身份、图表语法、版式库、页面语义). This module loads
the prose axes into structured dicts so that `leo-ppt style render` can compose
them deterministically into the deck_spec fields that prepare_slide_prompts.py
already injects (Global Style / Layout blocks).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .styles import StyleStoreError, builtin_style_path, load_style


class TemplateError(ValueError):
    reason_code = "template_store_error"


def _styles_root() -> Path:
    return builtin_style_path("_placeholder").parent


def _read_md(rel: str) -> str:
    path = _styles_root() / rel
    if not path.is_file():
        raise TemplateError(f"template_not_found: {rel}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise TemplateError(f"template_unreadable: {rel}") from exc


def _field(text: str, key: str) -> str:
    """Extract the value after a bold field label. Tolerates the upstream
    convention where the colon sits inside the closing asterisks (「**骨架:**」),
    as well as the plain form (「**骨架**:」). The value ends at the first
    newline; empty values must not swallow the next field's content."""
    bare = key.strip("*")
    m = re.search(
        rf"\*{{0,2}}{bare}[:\：]\*{{0,2}}[ \t]*(.*?)(?=\n|\Z)", text, re.S
    )
    return m.group(1).strip() if m else ""


def _section(text: str, heading: str) -> str:
    """Extract the body under a `## heading` until the next section or `---`.
    The heading is matched literally; only the rest of its line is loose."""
    m = re.search(
        rf"##\s+{re.escape(heading)}[^\n]*\n(.*?)(?=\n##|\n---|\Z)", text, re.S
    )
    return m.group(1).strip() if m else ""


def _blockquote(text: str) -> str:
    """Extract the first `> ...` quote block (the paste-ready paragraph)."""
    m = re.search(r"> (.+?)(?=\n\n|\Z)", text, re.S)
    return m.group(1).strip() if m else ""


def _table(text: str) -> dict[str, str]:
    """Parse a two-column markdown table into {row-key: row-value}."""
    rows: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"\| ([^|]+) \| ([^|]+) \|", line)
        if m:
            rows[m.group(1).strip()] = m.group(2).strip()
    return rows


# --------------------------------------------------------------------------- #
# Axis loaders
# --------------------------------------------------------------------------- #

def load_rendering(name: str) -> dict:
    """Load an AI-image rendering (08_图片渲染) into {positioning, paste_ready, ltd}."""
    text = _read_md(f"08_图片渲染/{name}.md")
    style_para = _section(text, "1. 风格段落")
    if not style_para:  # heading variants
        style_para = text
    return {
        "name": name,
        "positioning": _field(text, "**定位**"),
        "paste_ready": _blockquote(style_para),
        "line_texture_depth": _table(_section(text, "2. 线条 · 纹理 · 深度")),
    }


def load_layout(name: str) -> dict:
    """Load a page layout (12_版式库, e.g. 'P6', 'KPI Tower', '06_KPI_Tower')."""
    root = _styles_root() / "12_版式库"
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0] if text else ""
        if name in title or name in path.stem:
            return {
                "name": title.replace("# 版式：", "").strip(),
                "purpose": _field(text, "**用途**"),
                "content_type": _field(text, "**适用内容类型**"),
                "skeleton": _field(text, "**骨架**"),
                "key_classes": _field(text, "**关键类**"),
                "motion": _field(text, "**动效 recipe**"),
            }
    raise TemplateError(f"layout_not_found: {name}")


def load_image_type(name: str) -> dict:
    """Load an infographic type (07_信息图类型) into {positioning, skeleton}.
    The positioning is the first prose paragraph under the title (no bold
    label), and the skeleton is the `## 1. 构图骨架` section."""
    text = _read_md(f"07_信息图类型/{name}.md")
    positioning = ""
    for line in text.splitlines()[1:]:
        if line.startswith(("#", ">", "|")) or not line.strip():
            continue
        positioning = line.strip()
        break
    return {
        "name": name,
        "positioning": positioning,
        "skeleton": _section(text, "1. 构图骨架") or text,
    }


def load_mode(name: str) -> dict:
    """Load an argument mode (06_论证模式) into {name, skeleton}."""
    text = _read_md(f"06_论证模式/{name}.md")
    return {
        "name": name,
        "skeleton": _section(text, "1. 论证骨架") or text,
    }


# --------------------------------------------------------------------------- #
# Pairing map (视觉风格 ↔ 图片渲染), parsed from the pairing table doc
# --------------------------------------------------------------------------- #

def _pairs() -> dict[str, str]:
    text = _read_md("00_索引/视觉风格配对.md")
    pairs: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"\| ([^|]+) \| ([^|]+) \|", line)
        if m:
            pairs[m.group(1).strip()] = m.group(2).strip()
    return pairs


def paired_rendering(visual_style: str) -> str | None:
    return _pairs().get(visual_style)


# --------------------------------------------------------------------------- #
# Composers: deterministic injection content for deck_spec
# --------------------------------------------------------------------------- #

def compose_style(visual_style: str, *, mode: str | None = None) -> dict:
    """Merge the visual-style brief, its paired image rendering (paste-ready
    paragraph), and the argument mode into one deterministic dict for
    `deck_spec.style`."""
    style = load_style(visual_style)
    m = re.search(r"```json\n(.*)\n```", style["content"], re.S)
    if not m:
        raise TemplateError(f"style_brief_missing: {visual_style}")
    brief = json.loads(m.group(1))
    composed: dict = {
        "name": visual_style,
        "visual_direction": brief.get("visual_direction"),
        "color_palette": brief.get("color_palette"),
        "typography": brief.get("typography"),
        "layout_patterns": brief.get("layout_patterns"),
    }
    rendering_name = paired_rendering(visual_style)
    if rendering_name:
        try:
            composed["image_rendering"] = load_rendering(rendering_name)["paste_ready"]
        except TemplateError:
            composed["image_rendering"] = rendering_name
    if mode:
        composed["mode"] = load_mode(mode)["skeleton"]
    return composed


def compose_layout(layout: str, *, image_type: str | None = None) -> dict:
    """Merge a page layout's skeleton and an optional infographic type into one
    deterministic dict for `slides[].layout`."""
    layout_data = load_layout(layout)
    composed: dict = {
        "layout_name": layout_data["name"],
        "purpose": layout_data["purpose"],
        "content_requirements": layout_data["content_type"],
        "skeleton": layout_data["skeleton"],
    }
    if image_type:
        composed["image_type"] = load_image_type(image_type)["skeleton"]
    return composed


def list_templates() -> dict[str, list[str]]:
    """Enumerate the prose axis documents for discovery."""
    root = _styles_root()
    return {
        "renderings": sorted(p.stem for p in (root / "08_图片渲染").glob("*.md")),
        "layouts": sorted(p.stem for p in (root / "12_版式库").glob("*.md")
                          if not p.stem.startswith(("00_", "01_常犯"))),
        "image_types": sorted(p.stem for p in (root / "07_信息图类型").glob("*.md")),
        "modes": sorted(p.stem for p in (root / "06_论证模式").glob("*.md")),
    }
