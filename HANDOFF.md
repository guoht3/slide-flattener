# 交接说明

更新：2026-11-06。下一位执行者先读本项目 `CLARIFY.md`、`DECISIONS.md`、`PROJECT_STATE.md`。

目标是在保留原图和拍摄时间线索的前提下，校正讲座幻灯片照片，后续供 OCR 与音频对齐使用。当前已完成本地部署、右下角边框误检修正、89 张批处理及基于用户反馈的二次分类。代码入口为 `flatten_slides.py`，打包入口为 `package_results.py`，浏览器手调入口为 `manual_editor.py`。操作说明见 `docs/manual-processing.md`。

校正对照包 `deliverables_20261106_v2/` 有 54 张自动待验收、35 张需人工；旧版 `deliverables_20261106/` 保留。人工组由原 23 张及用户指出的 12 张组成，另外 3 张用户指出的图片本来就在人工组。原清单 `docs/manual-review.csv` 与反馈 `docs/user-corner-feedback.csv` 均为本机文件，不进 Git。浏览器手调服务监听 127.0.0.1:8765，手动版本保存在 `manual_corrections/`，均不进 Git。`[ok]` 与自动指标都不是质量结论。

用户已完成全部 35 张手动矫正，共 36 个保存版本。`build_lecture_manuscript.py` 从各人工图片选择最新版本，结合 54 张自动图，复制 89 张到 `deliverables_20261106_v3/selected_images/`，做本地 OCR 并生成 `讲座幻灯片文字稿.docx`。逐行记录在 `ocr_results.json`，来源在 `image_sources.csv`；共 2419 行，111 行低于 0.70。Word 在本机 Word 中导出检查为 87 页，包含 89 图和 89 标题，无短空白尾页。交付目录 `qa/` 存放排版过程和备份。此文稿仅是幻灯片可见文字，不是讲座音频口述稿；后续需人工核对专业词与图表关系，并再处理音频。
