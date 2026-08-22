from __future__ import annotations

import pytest

from leo_ppt_generator.styles import StyleStoreError, list_styles, load_style, save_style
from leo_ppt_generator import cli


def test_user_style_overrides_builtin_and_is_persisted(tmp_path):
    builtin = load_style("清爽专业风", home=tmp_path)
    saved = save_style("清爽专业风", "# 用户风格\n色彩：蓝灰\n", home=tmp_path)
    loaded = load_style("清爽专业风", home=tmp_path)
    assert builtin["source"] == "builtin"
    assert saved["source"] == "user"
    assert loaded["source"] == "user"
    assert "用户风格" in loaded["content"]
    assert any(item["name"] == "清爽专业风" and item["source"] == "user" for item in list_styles(home=tmp_path))


def test_style_store_rejects_sensitive_content_and_requires_explicit_overwrite(tmp_path):
    save_style("custom", "# safe\n", home=tmp_path)
    with pytest.raises(StyleStoreError, match="style_name_conflict"):
        save_style("custom", "# changed\n", home=tmp_path)
    with pytest.raises(StyleStoreError, match="style_sensitive_content_forbidden"):
        save_style("secret", "api_key: do-not-save\n", home=tmp_path)
    replaced = save_style("custom", "# changed\n", home=tmp_path, overwrite=True)
    assert replaced["source"] == "user"


def test_style_store_validates_name_and_missing_style(tmp_path):
    with pytest.raises(StyleStoreError, match="style_name_invalid"):
        save_style("../escape", "safe", home=tmp_path)
    with pytest.raises(StyleStoreError, match="style_not_found"):
        load_style("missing", home=tmp_path)


def test_style_cli_save_load_list_and_conflict_are_machine_observable(tmp_path, capsys):
    content_file = tmp_path / "style.md"
    content_file.write_text("# CLI 风格\n主色：深蓝\n", encoding="utf-8")
    saved = cli.main(["style", "save", "cli-style", "--content-file", str(content_file), "--home", str(tmp_path)])
    assert saved == 0
    save_payload = capsys.readouterr().out
    assert '"reason_code": "style_saved"' in save_payload

    assert cli.main(["style", "load", "cli-style", "--home", str(tmp_path)]) == 0
    load_payload = capsys.readouterr().out
    assert '"source": "user"' in load_payload
    assert "CLI 风格" in load_payload

    assert cli.main(["style", "list", "--home", str(tmp_path)]) == 0
    assert '"reason_code": "style_listed"' in capsys.readouterr().out

    assert cli.main(["style", "save", "cli-style", "--content-file", str(content_file), "--home", str(tmp_path)]) == 2
    conflict_payload = capsys.readouterr().err
    assert '"reason_code": "style_name_conflict"' in conflict_payload
