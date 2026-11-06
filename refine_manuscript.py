"""Remove low-confidence OCR lines and prepare a source-backed ASR term list."""

import argparse
import csv
import json
import re
from pathlib import Path

from docx import Document


# Terms are deliberately curated for this lecture. Each item must be present
# in at least one retained OCR line; abbreviations and established aliases are
# matched with targeted patterns rather than a generic keyword frequency cut.
TERM_RULES = [
    # Genes, proteins, reporters, and other molecular entities.
    ("Arc", "分子与基因", r"\bArc\b"),
    ("CAMK2A", "分子与基因", r"\bCAMK2A\b"),
    ("CaMKII", "分子与基因", r"\bCaMK(?:II|ll|2)(?![A-Za-z])"),
    ("CaMKII alpha", "分子与基因", r"CaMK(?:II|ll|2)(?:a|alpha|α)\b"),
    ("CaMKII beta", "分子与基因", r"CaMK(?:II|ll|2)(?:b|beta|β)\b"),
    ("CaMKIV", "分子与基因", r"\bCaMKIV\b"),
    ("CaMKK", "分子与基因", r"\bCaMKK\b"),
    ("calcineurin", "分子与基因", r"\bcalcineurin\b"),
    ("CaN", "分子与基因", r"\bCaN\b"),
    ("CREB", "分子与基因", r"\bCREB\b"),
    ("phospho-CREB", "分子与基因", r"\b(?:phospho.?CREB|pCREB)\b"),
    ("MEF2", "分子与基因", r"\bMEF2\b"),
    ("SRF", "分子与基因", r"\bSRF\b"),
    ("SARE", "分子与基因", r"\bSARE\b"),
    ("E-SARE", "分子与基因", r"\bE.?SARE\b"),
    ("GluA", "分子与基因", r"\bGluA\b"),
    ("GluA1", "分子与基因", r"\bGluA1\b"),
    ("PSD-95", "分子与基因", r"\bPSD.?95\b"),
    ("Ca2+", "分子与基因", r"\bCa2\+?\b"),
    ("PP1", "分子与基因", r"\bPP1\b"),
    ("PPase", "分子与基因", r"\bPPase\b"),
    ("mRNA", "分子与基因", r"\bmRNA\b"),
    ("GFP", "分子与基因", r"\bGFP\b"),
    ("EGFP", "分子与基因", r"\bEGFP\b"),
    ("RFP", "分子与基因", r"\bRFP\b"),
    ("GFP-TeNT", "分子与基因", r"\bGFP.?TeNT\b"),
    # Named mutations: digits are part of a specialist name, not measurements.
    ("P212L", "突变与模型", r"\bP212L\b"),
    ("P235L", "突变与模型", r"\bP235L\b"),
    ("H282R", "突变与模型", r"\bH282R\b"),
    ("E183V", "突变与模型", r"\bE183V\b"),
    ("F98S", "突变与模型", r"\bF98S\b"),
    ("T286P", "突变与模型", r"\bT286P\b"),
    ("N326S", "突变与模型", r"\bN326S\b"),
    ("knock-in mouse", "突变与模型", r"knock.?in mouse"),
    ("de novo mutation", "突变与模型", r"de novo.{0,15}mutation"),
    ("intellectual disability", "突变与模型", r"intellectual disabilit"),
    # Memory, plasticity, and synaptic mechanisms.
    ("hippocampal LTP", "突触与记忆机制", r"hippocampal LTP"),
    ("single-spine LTP", "突触与记忆机制", r"single.?spine LTP"),
    ("heterosynaptic LTD", "突触与记忆机制", r"heterosynaptic LTD"),
    ("synaptic plasticity", "突触与记忆机制", r"synaptic plasticity"),
    ("synaptic potentiation", "突触与记忆机制", r"synaptic potentiation"),
    ("synaptic tagging", "突触与记忆机制", r"synaptic tagging"),
    ("inverse synaptic tagging", "突触与记忆机制", r"inverse synaptic tagging"),
    ("heterosynaptic depression", "突触与记忆机制", r"heterosynaptic depression"),
    ("homeostatic mechanism", "突触与记忆机制", r"homeostatic mechanism"),
    ("lateral diffusion", "突触与记忆机制", r"lateral diffusion"),
    ("lateral dispersion", "突触与记忆机制", r"lateral dispersion"),
    ("dendritic spine", "突触与记忆机制", r"dendritic spine"),
    ("spine volume", "突触与记忆机制", r"spine volume"),
    ("synapse-to-nucleus signaling", "突触与记忆机制", r"synapse.?to.?nucleus signaling"),
    ("input-specific silencing", "突触与记忆机制", r"input.?specific silencing"),
    ("supralinear activation", "突触与记忆机制", r"supralinear.{0,20}activation"),
    ("sublinear summation", "突触与记忆机制", r"sublinear summation"),
    ("memory engram", "突触与记忆机制", r"memory engram"),
    ("engram cell", "突触与记忆机制", r"engram cell"),
    ("fear memory", "突触与记忆机制", r"fear.?memory"),
    ("memory encoding", "突触与记忆机制", r"memory encoding"),
    ("memory consolidation", "突触与记忆机制", r"memory consolidation"),
    ("memory allocation", "突触与记忆机制", r"memory allocation"),
    ("memory circuit", "突触与记忆机制", r"memory circuit"),
    ("Arc engram cell circuit", "突触与记忆机制", r"Arc engram cell circuit"),
    ("Arc enhancer", "突触与记忆机制", r"Arc enhancer"),
    ("SARE enhancer", "突触与记忆机制", r"SARE enhancer"),
    ("Synaptic Activity Responsive Element", "突触与记忆机制", r"Synaptic Activity.?Respons(?:e|ive) Element"),
    ("CREB signaling", "突触与记忆机制", r"CREB signaling"),
    ("CREB-dependent transcription", "突触与记忆机制", r"CREB.?\s*dependent transcription"),
    ("activity-dependent lateral diffusion", "突触与记忆机制", r"activity.?dependent lateral diffusion"),
    # Experimental methods, sensors, and reagents.
    ("FRET", "实验方法与探针", r"\bFRET\b"),
    ("FRET imaging", "实验方法与探针", r"FRET imaging"),
    ("FRET probe", "实验方法与探针", r"FRET.?probe"),
    ("Red K2 alpha", "实验方法与探针", r"RedK2a|Red.?K2α"),
    ("R-CaMP2", "实验方法与探针", r"\bR.?CaMP2\b"),
    ("XCaMPs", "实验方法与探针", r"\bXCaMPs\b"),
    ("XCaMP-C", "实验方法与探针", r"\bXCaMP.?C\b"),
    ("XCaMP-R", "实验方法与探针", r"\bXCaMP.?R\b"),
    ("R-GECO1", "实验方法与探针", r"\bR.?GECO1\b"),
    ("GECI", "实验方法与探针", r"\bGEC[Ii]\b"),
    ("ChR2", "实验方法与探针", r"\bChR2\b"),
    ("rsChRmine", "实验方法与探针", r"\brsChRmine\b"),
    ("CRISPR/Cas9", "实验方法与探针", r"CRISPR.?Cas9"),
    ("ERT2-Cre-ERT2", "实验方法与探针", r"ERT2.?Cre.?ERT2"),
    ("fEPSP", "实验方法与探针", r"\bfEPSP\b"),
    ("HFS", "实验方法与探针", r"\bHFS\b"),
    ("TTX", "实验方法与探针", r"\bTTX\b"),
    ("DOX", "实验方法与探针", r"\bDOX\b"),
    ("MNI-Glu", "实验方法与探针", r"\bMNI.?Glu\b"),
    ("chemTag-GluA1", "实验方法与探针", r"chemTag.?\s*GluA1"),
    ("all-optical interrogation", "实验方法与探针", r"all.?optical interrogation"),
    ("multiplex imaging", "实验方法与探针", r"multiplex imaging"),
    ("optogenetic reactivation", "实验方法与探针", r"optogenetic reactivation"),
    ("two-photon imaging", "实验方法与探针", r"2p.?imaging|two.?photon imaging"),
    ("single-cell resolution", "实验方法与探针", r"single.?cell resolution"),
    ("cell-type-specific manipulation", "实验方法与探针", r"cell.?type specific manipulation"),
    ("high-frequency electrical stimulation", "实验方法与探针", r"high.?frequency electrical stimulation"),
    ("uncaging stimulation", "实验方法与探针", r"uncaging.?stimulat"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("deliverables_20261106_v3"))
    parser.add_argument("--out", type=Path, default=Path("deliverables_20261106_v6"))
    args = parser.parse_args()
    source = args.source.resolve()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"output directory is not empty: {out}")
    records = json.loads((source / "ocr_results.json").read_text(encoding="utf-8"))
    dropped = sum(line["confidence"] < 0.70 for record in records for line in record["lines"])
    clean_records = json.loads(json.dumps(records))
    for record in clean_records:
        record["lines"] = [line for line in record["lines"] if line["confidence"] >= 0.70]

    doc = Document(source / "讲座幻灯片文字稿.docx")
    marked = [paragraph for paragraph in doc.paragraphs if "[待核对]" in paragraph.text]
    if len(marked) != dropped:
        raise ValueError(f"marked paragraphs ({len(marked)}) do not match low-confidence OCR lines ({dropped})")
    for paragraph in marked:
        element = paragraph._element
        element.getparent().remove(element)

    out.mkdir(parents=True, exist_ok=True)
    output_docx = out / "讲座幻灯片文字稿_清理版.docx"
    doc.save(output_docx)
    (out / "ocr_results_clean.json").write_text(json.dumps(clean_records, ensure_ascii=False, indent=2), encoding="utf-8")

    terms = []
    seen = set()
    unmatched = []
    for term, category, pattern in TERM_RULES:
        if term.casefold() in seen:
            raise ValueError(f"duplicate term: {term}")
        seen.add(term.casefold())
        slides = []
        expression = re.compile(pattern, re.IGNORECASE)
        for record in clean_records:
            text = " ".join(line["text"] for line in record["lines"])
            if expression.search(text):
                slides.append(record["index"])
        if slides:
            if re.fullmatch(r"\d+(?:[.,]\d+)?", term):
                raise ValueError(f"numeric-only term: {term}")
            terms.append({"term": term, "category": category, "slide_count": len(slides),
                          "slides": ",".join(str(index) for index in slides)})
        else:
            unmatched.append(term)
    (out / "专业词稿.txt").write_text("\n".join(item["term"] for item in terms) + "\n", encoding="utf-8")
    no_digit_terms = [item["term"] for item in terms if not re.search(r"\d", item["term"])]
    (out / "专业词稿_不含任何数字.txt").write_text("\n".join(no_digit_terms) + "\n", encoding="utf-8")
    with (out / "专业词稿_出处.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["term", "category", "slide_count", "slides"])
        writer.writeheader()
        writer.writerows(terms)
    (out / "交付说明.md").write_text(
        f"# 清理版讲座文字稿与专业词稿\n\n"
        f"从原文字稿删除 {dropped} 段低置信度识别文字及其“待核对”标签，保留 {sum(len(r['lines']) for r in clean_records)} 行。"
        f"图片和其他正文未删改。\n\n专业词稿有 {len(terms)} 个经过幻灯片文字支持的术语，TXT 每行一个，便于导入音频识别工具；"
        f"CSV 给出类别和出现的幻灯片序号。纯数字、时间、剂量和普通英语词没有收录；"
        f"CaMK2A、GluA1、P212L 等名称内部的数字保留。若识别服务要求连名称内部的数字也不能出现，"
        f"可使用《专业词稿_不含任何数字.txt》，其中有 {len(no_digit_terms)} 个词。\n\n"
        f"这是术语候选词表，不代表 OCR 对每个字母都绝对正确。原始逐行 OCR 和原版 Word 仍保存在上一版交付目录。\n",
        encoding="utf-8")
    print(f"removed={dropped} retained={sum(len(r['lines']) for r in clean_records)} terms={len(terms)} no_digit_terms={len(no_digit_terms)}")
    print("unmatched candidates:", ", ".join(unmatched))


if __name__ == "__main__":
    main()
