"""Assemble corrected lecture photos and OCR into a traceable Word manuscript.

The source package and all manual versions remain untouched. Each slide record is
written as soon as OCR completes, so a long run can safely resume.
"""

import argparse
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

import cv2
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from rapidocr_onnxruntime import RapidOCR


def source_image(row, corrections):
    folder = corrections / Path(row["filename"]).stem
    versions = sorted(folder.glob("*.jpg")) if folder.is_dir() else []
    if row["status"] == "manual_review":
        if not versions:
            raise ValueError(f"manual image has no saved version: {row['filename']}")
        return versions[-1], "manual", len(versions)
    return row, "automatic", 0


def recognize(engine, image_path):
    result, _ = engine(str(image_path))
    lines = []
    for box, text, score in result or []:
        text = str(text).strip()
        if text:
            lines.append({
                "text": text,
                "confidence": round(float(score), 3),
                "box": [[round(float(x), 1), round(float(y), 1)] for x, y in box],
            })
    return lines


def make_document(records, destination):
    display_dir = destination / "qa" / "word_images"
    display_dir.mkdir(parents=True, exist_ok=True)
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(1.65)
    section.bottom_margin = Cm(1.55)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    normal = doc.styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(9)
    normal.paragraph_format.space_after = Pt(3)
    title_style_ppr = doc.styles["Title"]._element.get_or_add_pPr()
    title_border = title_style_ppr.find(qn("w:pBdr"))
    if title_border is not None:
        title_style_ppr.remove(title_border)
    title = doc.add_paragraph(style="Title")
    title.add_run("讲座幻灯片文字稿")
    title.runs[0].font.color.rgb = RGBColor(0, 0, 0)
    doc.add_paragraph("按照照片拍摄文件名顺序整理，共 89 张。每页包含选用的校正图片和英文文字识别结果。")
    doc.add_paragraph("文字识别只提取幻灯片可见内容，不等于讲者的口述逐字稿。图表线条、箭头与空间关系以配图为准；小字、专有名词和多栏阅读顺序需要结合图片复核。")
    manual = sum(record["source_kind"] == "manual" for record in records)
    doc.add_paragraph(f"图片来源：{manual} 张最新手动校正版，{len(records) - manual} 张自动校正版。原图、旧手动版本和识别明细均另行保留。")
    doc.add_heading("结尾页的三项要点", level=1)
    doc.add_paragraph("以下依据第 87 张照片中的 Take home message 整理，便于先把握讲座结论；详细原文与配图见该页。")
    takeaways = [
        "CaMK2A 通过 GluA 的侧向扩散促进长时程增强 LTP。人类智力障碍相关证据提示，CaMK2A 的超线性响应参与调节体内可塑性的动态范围。",
        "Arc 是 CREB 的靶基因。增强型 SARE 可捕捉与恐惧记忆提取有关的 Arc 记忆印迹细胞；Arc 的活动诱导还与弱突触的逆向突触标记及局部晚期异突触抑制有关。",
        "XCaMPs 多路活动记录与组合式全光学探查，为更精确地记录记忆回路和开展细胞类型特异性操作提供了方法。",
    ]
    for takeaway in takeaways:
        doc.add_paragraph(takeaway, style="List Number")
    doc.add_heading("逐页文字稿", level=1)
    doc.add_page_break()
    for index, record in enumerate(records, 1):
        p = doc.add_heading(f"{index:02d}  {record['filename']}", level=2)
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.keep_with_next = True
        source_label = "手动校正版" if record["source_kind"] == "manual" else "自动校正版"
        meta = doc.add_paragraph(f"拍摄时间 {record['capture_time']}  ·  {source_label}  ·  识别 {len(record['lines'])} 行")
        meta.style = "Subtitle"
        meta.paragraph_format.keep_with_next = True
        picture = doc.add_paragraph()
        picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
        picture.paragraph_format.space_after = Pt(6)
        image = cv2.imread(str(destination / record["selected_image"]))
        if image is None:
            raise ValueError(f"cannot read selected image: {record['filename']}")
        scale = min(1.0, 1800 / image.shape[1])
        if scale < 1:
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        display_path = display_dir / record["filename"]
        if not display_path.is_file() and not cv2.imwrite(str(display_path), image, [cv2.IMWRITE_JPEG_QUALITY, 85]):
            raise ValueError(f"cannot write Word image: {record['filename']}")
        line_count = len(record["lines"])
        picture_width = 10.0 if line_count >= 40 else 11.3 if line_count >= 35 else 12.8 if line_count >= 25 else 15.2
        picture.add_run().add_picture(str(display_path), width=Cm(picture_width))
        heading = doc.add_paragraph("识别文字")
        heading.style = "Heading 3"
        heading.paragraph_format.space_before = Pt(5)
        if record["lines"]:
            for line in record["lines"]:
                paragraph = doc.add_paragraph(style="Normal")
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.0
                run = paragraph.add_run(line["text"])
                run.font.size = Pt(8.0 if line_count >= 40 else 8.5)
                if line["confidence"] < 0.70:
                    run.font.color.rgb = RGBColor(172, 73, 33)
                    paragraph.add_run("  [待核对]").font.color.rgb = RGBColor(172, 73, 33)
        else:
            doc.add_paragraph("未识别到可读文字，请查看配图。")
    output = destination / "讲座幻灯片文字稿.docx"
    if output.is_file():
        backups = destination / "qa" / "word_backups"
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / f"讲座幻灯片文字稿_{datetime.now().strftime('%Y%m%d_%H%M%S%f')}.bak.docx"
        shutil.copy2(output, backup)
    doc.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=Path("deliverables_20261106_v2"))
    parser.add_argument("--corrections", type=Path, default=Path("manual_corrections"))
    parser.add_argument("--out", type=Path, default=Path("deliverables_20261106_v3"))
    args = parser.parse_args()
    package = args.package.resolve()
    corrections = args.corrections.resolve()
    out = args.out.resolve()
    checkpoint = out / "ocr_results.json"
    if out.exists() and any(out.iterdir()) and not checkpoint.is_file():
        raise ValueError(f"output directory already contains unrelated files: {out}")
    with (package / "manifest.csv").open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    if len(rows) != 89:
        raise ValueError(f"expected 89 slide records, found {len(rows)}")
    out.mkdir(parents=True, exist_ok=True)
    selected = out / "selected_images"
    selected.mkdir(exist_ok=True)
    engine = RapidOCR()
    records = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.is_file() else []
    if [record["filename"] for record in records] != [row["filename"] for row in rows[:len(records)]]:
        raise ValueError("OCR checkpoint does not match the package manifest")
    for index, row in enumerate(rows[len(records):], len(records) + 1):
        source, kind, version_count = source_image(row, corrections)
        if kind == "automatic":
            source = package / row["processed"]
        if not source.is_file():
            raise FileNotFoundError(source)
        target = selected / row["filename"]
        shutil.copy2(source, target)
        image = cv2.imread(str(target))
        if image is None:
            raise ValueError(f"cannot read {target}")
        lines = recognize(engine, target)
        stamp = row["filename"].removeprefix("IMG_").removesuffix(".jpg")
        capture_time = datetime.strptime(stamp, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "index": index,
            "filename": row["filename"],
            "capture_time": capture_time,
            "source_kind": kind,
            "source_path": str(source),
            "manual_version_count": version_count,
            "selected_image": str(Path("selected_images") / row["filename"]),
            "image_width": image.shape[1],
            "image_height": image.shape[0],
            "lines": lines,
        }
        records.append(record)
        checkpoint.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{index:02d}/{len(rows)} {row['filename']} {kind} {len(lines)} lines", flush=True)
    with (out / "image_sources.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["index", "filename", "capture_time", "source_kind", "source_path", "manual_version_count", "selected_image", "image_width", "image_height"])
        writer.writeheader()
        writer.writerows({key: record[key] for key in writer.fieldnames} for record in records)
    make_document(records, out)
    print(f"Word saved: {out / '讲座幻灯片文字稿.docx'}", flush=True)


if __name__ == "__main__":
    main()
