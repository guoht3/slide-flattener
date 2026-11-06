"""Local browser editor for versioned, manual slide-corner corrections.

Only listens on 127.0.0.1. Original and automatic images are read-only; every
manual save creates a new image and a JSON record under manual_corrections/.
"""

import argparse
import csv
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import cv2
import numpy as np

import flatten_slides as fs


ASPECTS = {"16:9", "4:3", "3:2", "auto"}
VERSION_ID = re.compile(r"^\d{8}T\d{12}Z_[0-9a-f]{8}$")
HTML_FILE = Path(__file__).with_name("manual_editor.html")


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def encode_jpg(image, quality=92):
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return encoded.tobytes()


class EditorData:
    def __init__(self, package, data_dir=None):
        self.package = Path(package).resolve()
        self.data_dir = (Path(data_dir) if data_dir else Path(__file__).resolve().parent / "manual_corrections").resolve()
        self.lock = threading.Lock()
        self.auto_cache = {}
        manifest = self.package / "manifest.csv"
        if not manifest.is_file() or not HTML_FILE.is_file():
            raise FileNotFoundError("package manifest or manual_editor.html is missing")
        with manifest.open(newline="", encoding="utf-8-sig") as file:
            rows = list(csv.DictReader(file))
        self.rows = {}
        for row in rows:
            name = row["filename"]
            if name in self.rows or Path(name).name != name:
                raise ValueError(f"duplicate or invalid filename: {name}")
            for field in ("original", "processed"):
                path = (self.package / row[field]).resolve()
                if not path.is_relative_to(self.package) or not path.is_file():
                    raise ValueError(f"missing or unsafe {field} for {name}")
            self.rows[name] = row

    def row(self, name):
        try:
            return self.rows[name]
        except KeyError as exc:
            raise ValueError(f"unknown image: {name}") from exc

    def path_for(self, name, field):
        return self.package / self.row(name)[field]

    def versions(self, name):
        self.row(name)
        folder = self.data_dir / Path(name).stem
        versions = []
        if folder.is_dir():
            for path in sorted(folder.glob("*.json")):
                if not VERSION_ID.fullmatch(path.stem):
                    continue
                image = path.with_suffix(".jpg")
                if not image.is_file():
                    continue
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, OSError, KeyError):
                    continue
                versions.append({
                    "id": path.stem,
                    "created_at": record["created_at"],
                    "aspect": record["aspect"],
                    "url": f"/api/version/{name}/{path.stem}",
                    "corners": record["corners"],
                })
        return versions

    def flagged(self):
        path = self.data_dir / "flags.jsonl"
        names = set()
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    name = json.loads(line)["filename"]
                except (ValueError, KeyError):
                    continue
                if name in self.rows:
                    names.add(name)
        return names

    def items(self):
        flagged = self.flagged()
        result = []
        for name, row in self.rows.items():
            versions = self.versions(name)
            manual = row["status"] == "manual_review" or name in flagged or bool(versions)
            result.append({
                "filename": name,
                "status": "manual_review" if manual else "auto_checked",
                "reason": row["reason"] or ("用户在编辑界面标记" if name in flagged else ""),
                "version_count": len(versions),
            })
        return result

    def original(self, name):
        image = cv2.imread(str(self.path_for(name, "original")))
        if image is None:
            raise ValueError(f"cannot read original: {name}")
        return image

    def automatic_corners(self, name, image):
        with self.lock:
            if name not in self.auto_cache:
                quad = fs.detect_slide_quad(image)
                h, w = image.shape[:2]
                if quad is None:
                    quad = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
                self.auto_cache[name] = fs.order_points(quad).tolist()
            return self.auto_cache[name]

    def item(self, name):
        image = self.original(name)
        h, w = image.shape[:2]
        versions = self.versions(name)
        latest = versions[-1] if versions else None
        row = self.row(name)
        manual = row["status"] == "manual_review" or name in self.flagged() or bool(versions)
        return {
            "filename": name,
            "status": "manual_review" if manual else "auto_checked",
            "reason": row["reason"] or ("用户在编辑界面标记" if manual else ""),
            "width": w,
            "height": h,
            "automatic_corners": self.automatic_corners(name, image),
            "corners": latest["corners"] if latest else self.automatic_corners(name, image),
            "aspect": latest["aspect"] if latest else "16:9",
            "original_url": f"/api/image/{name}/original",
            "attempt_url": f"/api/image/{name}/attempt",
            "latest_url": latest["url"] if latest else None,
            "versions": list(reversed(versions)),
        }

    def checked_corners(self, image, points):
        if not isinstance(points, list) or len(points) != 4:
            raise ValueError("select exactly four corners")
        try:
            corners = np.asarray(points, dtype=np.float32).reshape(4, 2)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid corner coordinates") from exc
        h, w = image.shape[:2]
        if not np.isfinite(corners).all():
            raise ValueError("corner coordinates must be finite")
        if (corners[:, 0] < 0).any() or (corners[:, 0] > w - 1).any() or (corners[:, 1] < 0).any() or (corners[:, 1] > h - 1).any():
            raise ValueError("corners must stay within the original image")
        ordered = fs.order_points(corners)
        if len({tuple(p) for p in ordered.tolist()}) != 4:
            raise ValueError("corners must be distinct")
        if not cv2.isContourConvex(ordered.reshape(4, 1, 2)):
            raise ValueError("corners must form a convex quadrilateral")
        if cv2.contourArea(ordered) < 0.002 * w * h:
            raise ValueError("selected area is too small")
        return ordered

    def warped(self, payload, preview):
        name = payload.get("filename")
        image = self.original(name)
        corners = self.checked_corners(image, payload.get("corners"))
        aspect_name = payload.get("aspect", "16:9")
        if aspect_name not in ASPECTS:
            raise ValueError("unsupported aspect ratio")
        aspect = fs.parse_aspect(aspect_name)
        if preview:
            scale = min(1.0, 1400.0 / max(image.shape[:2]))
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            corners = corners * scale
        out_w, out_h = fs.output_size(corners, aspect)
        limit = 1100 if preview else 8000
        factor = min(1.0, limit / max(out_w, out_h))
        out_w = max(1, int(round(out_w * factor)))
        out_h = max(1, int(round(out_h * factor)))
        result = fs.four_point_transform(image, corners, out_w, out_h)
        return name, result, fs.order_points(payload["corners"]).tolist(), aspect_name

    def save(self, payload):
        name, result, corners, aspect = self.warped(payload, preview=False)
        stamp = utc_stamp()
        version_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
        folder = self.data_dir / Path(name).stem
        folder.mkdir(parents=True, exist_ok=True)
        jpg = folder / f"{version_id}.jpg"
        record = folder / f"{version_id}.json"
        data = {
            "filename": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "aspect": aspect,
            "corners": corners,
            "image": jpg.name,
        }
        with jpg.open("xb") as file:
            file.write(encode_jpg(result, quality=95))
        with record.open("x", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        return {"id": version_id, "url": f"/api/version/{name}/{version_id}",
                "version_count": len(self.versions(name))}

    def flag(self, name):
        self.row(name)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        event = {"filename": name, "at": datetime.now(timezone.utc).isoformat()}
        with self.lock:
            with (self.data_dir / "flags.jsonl").open("a", encoding="utf-8") as file:
                file.write(json.dumps(event, ensure_ascii=False) + "\n")
        return {"filename": name, "status": "manual_review"}


class EditorHandler(BaseHTTPRequestHandler):
    data = None

    def log_message(self, format, *args):
        if args and str(args[1] if len(args) > 1 else "").startswith("5"):
            super().log_message(format, *args)

    def send_bytes(self, body, content_type="application/octet-stream", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=200):
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8", status)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        try:
            if path == "/":
                return self.send_bytes(HTML_FILE.read_bytes(), "text/html; charset=utf-8")
            if path == "/api/health":
                return self.send_json({"ok": True, "images": len(self.data.rows)})
            if path == "/api/items":
                return self.send_json(self.data.items())
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["api", "item"]:
                return self.send_json(self.data.item(parts[2]))
            if len(parts) == 3 and parts[:2] == ["api", "thumb"]:
                row = self.data.row(parts[2])
                image = cv2.imread(str(self.data.package / row["processed"]))
                if image is None:
                    raise ValueError("cannot read thumbnail source")
                h, w = image.shape[:2]
                thumbnail = cv2.resize(image, (220, max(1, round(h * 220 / w))), interpolation=cv2.INTER_AREA)
                return self.send_bytes(encode_jpg(thumbnail, 78), "image/jpeg")
            if len(parts) == 4 and parts[:2] == ["api", "image"]:
                name, kind = parts[2:]
                field = {"original": "original", "attempt": "processed"}.get(kind)
                if field is None:
                    raise ValueError("unknown image kind")
                return self.send_bytes(self.data.path_for(name, field).read_bytes(), "image/jpeg")
            if len(parts) == 4 and parts[:2] == ["api", "version"]:
                name, version_id = parts[2:]
                self.data.row(name)
                if not VERSION_ID.fullmatch(version_id):
                    raise ValueError("invalid version ID")
                path = self.data.data_dir / Path(name).stem / f"{version_id}.jpg"
                if not path.is_file():
                    raise ValueError("version not found")
                return self.send_bytes(path.read_bytes(), "image/jpeg")
            self.send_error(404, "Not found")
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except (OSError, KeyError) as exc:
            self.send_json({"error": str(exc)}, 500)

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ValueError("invalid request length")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("request body must be an object")
            if path == "/api/preview":
                _, result, _, _ = self.data.warped(payload, preview=True)
                return self.send_bytes(encode_jpg(result, 82), "image/jpeg")
            if path == "/api/save":
                return self.send_json(self.data.save(payload))
            if path == "/api/flag":
                return self.send_json(self.data.flag(payload.get("filename")))
            self.send_error(404, "Not found")
        except (ValueError, TypeError, KeyError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except OSError as exc:
            self.send_json({"error": str(exc)}, 500)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    data = EditorData(args.package, args.data_dir)
    handler = type("BoundEditorHandler", (EditorHandler,), {"data": data})
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    server.daemon_threads = True
    print(f"Manual editor: http://127.0.0.1:{args.port}/ ({len(data.rows)} images)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
