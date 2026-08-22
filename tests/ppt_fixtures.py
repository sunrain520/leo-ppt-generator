from __future__ import annotations

import json
from pathlib import Path

from leo_ppt_generator.editable.adapter import EditableAdapter
from PIL import Image


def build_editable_page(
    source: Path,
    output: Path,
    *,
    text: str = "Editable fixture",
    slide_width: float = 10,
    slide_height: float = 5.625,
) -> tuple[Path, Path]:
    with Image.open(source) as image:
        width, height = image.size
    manifest = output.with_suffix(".manifest.json")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": {"width_px": width, "height_px": height},
                "slide": {"width": slide_width, "height": slide_height},
                "visual_inventory": [],
                "background_strategy": "native-rebuild",
                "text_inventory": [text],
                "quality_checks": {
                    "font_size_calibrated": True,
                    "visual_inventory_matched": True,
                    "background_strategy_checked": True,
                    "shape_corner_geometry_checked": True,
                },
                "text_boxes": [
                    {
                        "text": text,
                        "box_px": [8, 8, width - 16, max(16, height // 4)],
                        "font_size": 24,
                        "color": "000000",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return EditableAdapter.build_page_from_manifest(manifest, output), manifest
