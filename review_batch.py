"""Build contact sheets and a conservative review list from flattened slides.

This is a triage aid, not a correctness verdict: dark slides and photo-heavy
slides can be flagged even when their corners are accurate.
"""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Review a batch of flattened lecture slides")
    parser.add_argument("folder", type=Path, help="folder containing *_flat.jpg images")
    parser.add_argument("--out", type=Path, default=Path("review_sheets"))
    parser.add_argument("--min-bright-share", type=float, default=0.70)
    parser.add_argument("--min-gray-std", type=float, default=12.0)
    args = parser.parse_args()

    paths = sorted(args.folder.glob("*_flat.jpg"))
    if not paths:
        parser.error("no *_flat.jpg images found")
    args.out.mkdir(parents=True, exist_ok=True)

    rows = []
    tiles = []
    for path in paths:
        image = cv2.imread(str(path))
        if image is None:
            rows.append((path.name, "review", "unreadable", "", ""))
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        bright_share = float(np.mean(gray > 140))
        gray_std = float(gray.std())
        reasons = []
        if bright_share < args.min_bright_share:
            reasons.append("low_bright_share")
        if gray_std < args.min_gray_std:
            reasons.append("near_blank")
        status = "review" if reasons else "check"
        rows.append((path.name, status, ";".join(reasons),
                     f"{bright_share:.3f}", f"{gray_std:.1f}"))

        thumb = cv2.resize(image, (320, 180), interpolation=cv2.INTER_AREA)
        tile = np.full((210, 340, 3), 245, dtype=np.uint8)
        tile[20:200, 10:330] = thumb
        color = (0, 0, 220) if status == "review" else (0, 150, 0)
        cv2.rectangle(tile, (9, 19), (330, 200), color, 3)
        cv2.putText(tile, path.stem.replace("_flat", ""), (10, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 0), 1)
        tiles.append(tile)

    with (args.out / "review_list.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(("output_file", "status", "reason", "bright_share", "gray_std"))
        writer.writerows(rows)

    for start in range(0, len(tiles), 30):
        group = tiles[start:start + 30]
        sheet = np.full((1260, 1700, 3), 245, dtype=np.uint8)
        for index, tile in enumerate(group):
            row, col = divmod(index, 5)
            sheet[row * 210:(row + 1) * 210, col * 340:(col + 1) * 340] = tile
        cv2.imwrite(str(args.out / f"sheet_{start // 30 + 1:02d}.jpg"), sheet)

    flagged = sum(row[1] == "review" for row in rows)
    print(f"{len(rows)} images; {flagged} flagged for priority review; "
          f"contact sheets and CSV in {args.out}")


if __name__ == "__main__":
    main()
