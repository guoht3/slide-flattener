# 交接说明

更新：2026-11-06。下一位执行者先读本项目 `CLARIFY.md`、`DECISIONS.md`、`PROJECT_STATE.md`。

目标是在保留原图和拍摄时间线索的前提下，校正讲座幻灯片照片，后续供 OCR 与音频对齐使用。当前已完成本地部署、右下角边框误检修正、89 张批处理及基于用户反馈的二次分类。代码入口为 `flatten_slides.py`，打包入口为 `package_results.py`，浏览器手调入口为 `manual_editor.py`。操作说明见 `docs/manual-processing.md`。

最新版 `deliverables_20261106_v2/` 有 54 张自动待验收、35 张需人工。旧版 `deliverables_20261106/` 保留。新版人工组由原 23 张及用户指出的 12 张组成；另外 3 张用户指出的图片本来就在人工组。原清单 `docs/manual-review.csv` 与反馈 `docs/user-corner-feedback.csv` 均为本机文件，不进 Git。浏览器手调服务监听 127.0.0.1:8765，手动版本保存在 `manual_corrections/`，均不进 Git。用户还未验收整批质量；`[ok]` 与自动指标都不是质量结论。后续应让用户在新版对照页和编辑器中继续标出边界问题，再按确认后的角点处理人工组。
