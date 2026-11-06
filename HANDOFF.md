# 交接说明

更新：2026-11-06。下一位执行者先读本项目 `CLARIFY.md`、`DECISIONS.md`、`PROJECT_STATE.md`。

目标是在保留原图和拍摄时间线索的前提下，校正讲座幻灯片照片，后续供 OCR 与音频对齐使用。当前已完成本地部署、右下角边框误检修正、89 张批处理及基于用户反馈的二次分类。代码入口为 `flatten_slides.py`，打包入口为 `package_results.py`，浏览器手调入口为 `manual_editor.py`。操作说明见 `docs/manual-processing.md`。

校正对照包 `deliverables_20261106_v2/` 有 54 张自动待验收、35 张需人工；旧版 `deliverables_20261106/` 保留。人工组由原 23 张及用户指出的 12 张组成，另外 3 张用户指出的图片本来就在人工组。原清单 `docs/manual-review.csv` 与反馈 `docs/user-corner-feedback.csv` 均为本机文件，不进 Git。浏览器手调服务监听 127.0.0.1:8765，手动版本保存在 `manual_corrections/`，均不进 Git。`[ok]` 与自动指标都不是质量结论。

用户已完成全部 35 张手动矫正，共 36 个保存版本。`build_lecture_manuscript.py` 从各人工图片选择最新版本，结合 54 张自动图，复制 89 张到 `deliverables_20261106_v3/selected_images/`，做本地 OCR 并生成 `讲座幻灯片文字稿.docx`。逐行记录在 `ocr_results.json`，来源在 `image_sources.csv`；共 2419 行，111 行低于 0.70。Word 在本机 Word 中导出检查为 87 页，包含 89 图和 89 标题，无短空白尾页。交付目录 `qa/` 存放排版过程和备份。此文稿仅是幻灯片可见文字，不是讲座音频口述稿；后续需人工核对专业词与图表关系，并再处理音频。

用户随后要求移除所有标为“待核对”的文字并生成专业词稿。`refine_manuscript.py` 生成最终清理包 `deliverables_20261106_v6/`：Word 删除 111 段标记内容，清理 OCR 保留 2308 行；95 词主专业词稿逐项可追溯，另有 75 词完全无数字版及出处 CSV。主版剔除纯数字、时间、剂量和普通词，保留 CaMK2A 等名称内数字。清理版 Word 在本机 Word 导出检查为 85 页，89 张图和 89 个标题均在，无短空白页。原始 v3 数据留档；下一步可用该词稿进行音频识别。

当前用户要求按同一设备的时间戳将照片对到录音。已定位 `C:\Users\Administrator\Downloads\日本教授记忆.wav`，精确时长 01:08:20.240，只有 `fmt`/`data` RIFF 块，没有原录制时间；文件创建/修改是 2026-11-03 转存时刻。89 张 JPG EXIF 原始拍摄时间范围是 2026-10-30 14:06:17.204 至 14:59:21.444，跨度 53:04.240。`align_photo_audio.py` 已生成 `deliverables_20261106_alignment_inventory_v2/`，逐张 EXIF、文件名时间、校正版路径均核对齐全。若全部照片属于录音，录音开始只可限定在 13:51:01.204 至 14:06:17.204 之间。Q2 仍待用户提供手机录音开始或结束时间（含日期），之后用该脚本传 `--audio-start` 或 `--audio-end` 生成正式音频分秒表；不得凭转存时间推断。
