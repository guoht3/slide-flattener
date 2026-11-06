"""Package checked lecture-slide crops and images requiring manual correction."""

import argparse
import csv
import html
import shutil
from pathlib import Path

import cv2
import numpy as np


def contact_sheets(paths, folder, prefix):
    folder.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(paths), 30):
        sheet = np.full((1260, 1700, 3), 245, dtype=np.uint8)
        for index, (name, path) in enumerate(paths[start:start + 30]):
            image = cv2.imread(str(path))
            if image is None:
                raise ValueError(f"Could not read packaged image: {path}")
            thumb = cv2.resize(image, (320, 180), interpolation=cv2.INTER_AREA)
            tile = np.full((210, 340, 3), 245, dtype=np.uint8)
            tile[20:200, 10:330] = thumb
            cv2.putText(tile, Path(name).stem, (10, 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 0), 1)
            row, col = divmod(index, 5)
            sheet[row * 210:(row + 1) * 210, col * 340:(col + 1) * 340] = tile
        path = folder / f"{prefix}_{start // 30 + 1:02d}.jpg"
        if not cv2.imwrite(str(path), sheet):
            raise OSError(f"Could not write contact sheet: {path}")


def gallery(rows, out):
    cards = []
    for row in rows:
        name = html.escape(row["filename"])
        status = row["status"]
        reason = html.escape(row["reason"])
        original = html.escape(row["original"], quote=True)
        processed = html.escape(row["processed"], quote=True)
        badge = "需人工处理" if status == "manual_review" else "自动处理，待你确认"
        cards.append(
            f'<article class="card" data-status="{status}">'
            f'<header><strong>{name}</strong><span class="badge">{badge}</span></header>'
            f'<p>{reason}</p>'
            f'<div class="pair"><a href="{original}" target="_blank">'
            f'<img loading="lazy" src="{original}" alt="原图 {name}"><small>原图 ↗</small></a>'
            f'<a href="{processed}" target="_blank">'
            f'<img loading="lazy" src="{processed}" alt="自动处理 {name}">'
            f'<small>自动处理 ↗</small></a></div></article>'
        )
    accepted = sum(row["status"] == "auto_checked" for row in rows)
    manual = len(rows) - accepted
    page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>讲座图片处理结果</title><style>
:root{{font-family:system-ui,"Microsoft YaHei",sans-serif;color:#17212d;background:#f5f7fa}}
body{{margin:0 auto;max-width:1500px;padding:24px}}h1{{margin:0 0 8px}}
.intro{{color:#4c5a68;line-height:1.6}}.controls{{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}}
button{{border:1px solid #b7c4d3;border-radius:8px;padding:10px 16px;background:white;cursor:pointer;font-size:15px}}
button.active{{background:#145a9e;color:white;border-color:#145a9e}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:16px}}
.card{{background:white;border:1px solid #dbe3ea;border-radius:12px;padding:14px;box-shadow:0 2px 8px #1c2a3810}}
.card[data-status="manual_review"]{{border-color:#e8b8a4}}
.card header{{display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap}}
.badge{{font-size:12px;background:#e7f2e9;color:#23633c;border-radius:12px;padding:4px 8px}}
.card[data-status="manual_review"] .badge{{background:#fff0e8;color:#9f3e20}}
.card p{{min-height:21px;margin:7px 0;color:#555}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.pair a{{color:#145a9e;text-decoration:none}}.pair img{{display:block;width:100%;height:180px;object-fit:contain;background:#e9eef2}}
.pair small{{display:block;padding-top:4px}}
@media(max-width:560px){{body{{padding:12px}}.grid{{grid-template-columns:1fr}}.pair img{{height:130px}}}}
</style></head><body><h1>讲座图片处理结果</h1>
<p class="intro">共 {len(rows)} 张：我初步检查后，将 {accepted} 张放入“自动处理，待你确认”，{manual} 张放入“需人工处理”。
点击图片可查看原尺寸。原图中的遮挡或拍摄时已缺失的部分无法通过裁切恢复。</p>
<div class="controls"><button class="active" data-filter="all">全部 {len(rows)}</button>
<button data-filter="auto_checked">自动处理 {accepted}</button>
<button data-filter="manual_review">需人工处理 {manual}</button></div>
<main class="grid">{''.join(cards)}</main><script>
for(const button of document.querySelectorAll('button[data-filter]')){{
 button.addEventListener('click',()=>{{
  for(const other of document.querySelectorAll('button[data-filter]')) other.classList.toggle('active',other===button);
  const filter=button.dataset.filter;
  for(const card of document.querySelectorAll('.card')) card.hidden=filter!=='all'&&card.dataset.status!==filter;
 }});
}}
</script></body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--processed-dir", type=Path, required=True)
    parser.add_argument("--manual-list", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.out.exists():
        parser.error(f"output already exists; choose a new directory: {args.out}")
    with args.manual_list.open(newline="", encoding="utf-8-sig") as file:
        manual_rows = list(csv.DictReader(file))
    manual = {row["filename"]: row["reason"].strip() for row in manual_rows}
    if len(manual) != len(manual_rows):
        parser.error("duplicate filename in manual review list")
    sources = sorted(args.source_dir.glob("*.jpg"))
    if not sources:
        parser.error("no JPG originals found")
    missing = set(manual) - {path.name for path in sources}
    if missing:
        parser.error(f"manual review list has unknown files: {sorted(missing)}")
    for source in sources:
        processed = args.processed_dir / f"{source.stem}_flat{source.suffix}"
        if not processed.is_file():
            parser.error(f"processed image missing: {processed}")

    rows = []
    accepted_images = []
    manual_images = []
    for source in sources:
        attempted = args.processed_dir / f"{source.stem}_flat{source.suffix}"
        status = "manual_review" if source.name in manual else "auto_checked"
        category = "manual_review" if status == "manual_review" else "auto_checked"
        original_rel = Path(category) / "originals" / source.name
        processed_rel = Path(category) / ("auto_attempts" if status == "manual_review" else "processed") / attempted.name
        for source_path, relative in ((source, original_rel), (attempted, processed_rel)):
            destination = args.out / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
        row = {"filename": source.name, "status": status,
               "reason": manual.get(source.name, ""), "original": original_rel.as_posix(),
               "processed": processed_rel.as_posix()}
        rows.append(row)
        (manual_images if status == "manual_review" else accepted_images).append(
            (source.name, args.out / processed_rel))

    with (args.out / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=("filename", "status", "reason", "original", "processed"))
        writer.writeheader()
        writer.writerows(rows)
    contact_sheets(accepted_images, args.out / "contact_sheets", "auto_checked")
    contact_sheets(manual_images, args.out / "contact_sheets", "manual_review")
    gallery(rows, args.out)
    print(f"Packaged {len(accepted_images)} auto-checked and {len(manual_images)} manual-review images in {args.out}")


if __name__ == "__main__":
    main()
