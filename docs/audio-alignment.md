# 照片与音频时间轴

照片原件：`C:\Users\Administrator\Downloads\20261103-130512\`，89 张。每张均带 `DateTimeOriginal` 与亚秒字段。所用录音：`C:\Users\Administrator\Downloads\日本教授记忆.wav`，时长 01:08:20.240。

当前 `deliverables_20261106_alignment_inventory_v2/photo_audio_timeline.csv` 已列出照片 EXIF 时间、文件名时间、相邻照片间隔和对应的校正版图片。音频分秒列暂空，因为该 WAV 文件不含录制开始或结束时刻。电脑文件时间是 11 月 3 日转存时间，不能填充该列。如果全部照片确实落在这段录音中，则录音开始时间只能限定在 2026-10-30 13:51:01.204 至 14:06:17.204 之间，区间仍宽 15 分 16 秒。

拿到手机录音界面显示的开始时间后，在项目目录运行：

```powershell
& '.\.venv\Scripts\python.exe' align_photo_audio.py --audio 'C:\Users\Administrator\Downloads\日本教授记忆.wav' --photos 'C:\Users\Administrator\Downloads\20261103-130512' --image-sources 'deliverables_20261106_v3\image_sources.csv' --audio-start '2026-10-30 HH:MM:SS' --out 'deliverables_20261106_alignment_final'
```

若只知道结束时间，改用 `--audio-end`。脚本按录音时长反推另一端，输出每张照片的 `audio_offset_seconds` 和 `audio_timecode`，并指出是否落在录音范围内。应使用录音设备显示的本地时钟时间，不使用电脑转存时间。相邻照片的时间窗是幻灯片抽样范围，并非实际换页的精确秒数。
