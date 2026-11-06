# 查看与手动处理

打开本地 `deliverables_20261106/index.html`，可按“自动处理”与“需人工处理”筛选；点击图片可打开原尺寸。`manifest.csv` 记录每张图片的分类与路径。

需要手动移动四角时，在项目目录的 PowerShell 中运行：

```powershell
& '.\.venv\Scripts\python.exe' annotate.py --source-dir deliverables_20261106\manual_review\originals --out deliverables_20261106\manual_review\corrected --no-autocolor
```

在 `edit` 窗口拖动红点，`preview` 窗口实时显示结果。`NEXT`、`PREV`、`DONE` 或 Esc 会保存当前图。尚未补回原照片缺失的内容；这类图片只能保留现有局部画面，或查找其他照片。
