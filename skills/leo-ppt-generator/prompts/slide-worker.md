# Slide Worker Prompt

Use this template when dispatching a slide subagent after the sample slide is approved and full-deck generation is authorized.

```text
Generate slide <N> for this codex-ppt deck.

Deck dir: <absolute deck dir>
Run dir: <absolute run dir>
Backend contract: <absolute run dir>/input/backend-contract.json
Required slide image: 2560x1440 (16:9 2K)
Slide job file: <absolute deck dir>/prompts/slide_<NN>.json
Output target owned by parent: <absolute deck dir>/origin_image/slide_<NN>.png
Selected image backend: <built-in image tool OR CLI/API fallback>
Absolute leo-ppt CLI: <absolute leo-ppt CLI path supplied by parent from runtime_manager.py print-cli>
Sample generation method copied from the approved sample:
- backend_used: <exact backend label recorded by parent>
- tool_name: <built-in image tool OR absolute leo-ppt CLI path + upstream codex-ppt -- image>
- mode: <generate OR edit>
- model/config: <model, size, quality, or "built-in default" if not exposed>
- prompt_source: <approved sample prompt source>
- input_context_preparation: <how local images were made visible or attached>
- approved_sample_path: <absolute path to approved origin_image/slide_XX.png>
- handoff_rule: use this same backend/tool/mode; return a blocker if unavailable
Input images already prepared by the parent:
- <absolute path> - approved sample slide style reference; match style only, do not copy layout
- <absolute path> - strict input asset; preserve labels/data/arrows/content

Read the JSON job file, then follow its `prompt` field exactly. Use the selected image backend and the recorded sample generation method only.
You must produce the final slide candidate by calling the selected image generation backend:
- Built-in mode: use the built-in image generation/editing tool.
- CLI/API fallback generate mode: use `"<absolute leo-ppt CLI path>" upstream --backend-contract <absolute run dir>/input/backend-contract.json codex-ppt -- image generate --size 2560x1440 --prompt-file <job-prompt> --out <candidate-path>`.
- CLI/API fallback edit mode: use `"<absolute leo-ppt CLI path>" upstream --backend-contract <absolute run dir>/input/backend-contract.json codex-ppt -- image edit --size 2560x1440 --prompt-file <job-prompt> --image <absolute-input-path> --out <candidate-path>`; repeat `--image` for every required reference.

Forbidden for final slide image creation:
- local drawing or rendering scripts
- Pillow-generated slides
- SVG, HTML/CSS, or canvas screenshots
- python-pptx/PptxGenJS/native PPT layout screenshots
- manually composited text, card, chart, or image overlays

If you cannot use the selected image backend, stop and return `blocker=<reason>` instead of creating a lower-quality replacement.
If you cannot follow the recorded sample generation method, stop and return `blocker=<reason>` instead of switching tools.
Do not edit slide job files, origin_image, speech.md, or assemble the PPT.

Before returning, visually check:
- Chinese text is readable and not garbled
- every required title, number, unit, label, and citation matches the approved slide job exactly
- style matches the approved sample slide
- required source images are visibly included and not replaced by a similar redraw
- no overlapping or truncated important content
- charts preserve approved values, units, labels, legends, and ordering; do not invent missing data

Return only:
backend_used=<built-in image tool OR absolute leo-ppt CLI path + upstream codex-ppt -- image>
selected_source=/absolute/path/to/$CODEX_HOME/generated_images/.../ig_*.png
qa_note=<one sentence>
worker_duration_seconds=<measured total worker seconds>
backend_duration_seconds=<measured backend call seconds, or not-recorded>
```
