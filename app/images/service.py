"""Local file storage service for uploaded images."""

import re
import uuid
from pathlib import Path


class UploadedImageStorageService(object):
    """Persist uploaded image bytes to the local workspace."""

    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir or (Path(__file__).resolve().parents[2] / "uploaded_images"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_file_name(file_name):
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", (file_name or "").strip())
        return safe_name or "image"

    def build_file_name(self, original_file_name):
        safe_name = self._sanitize_file_name(original_file_name)
        suffix = Path(safe_name).suffix or ".bin"
        stem = Path(safe_name).stem or "image"
        return "{0}_{1}{2}".format(stem, uuid.uuid4().hex[:10], suffix.lower())

    def save_file(self, original_file_name, content_bytes):
        stored_file_name = self.build_file_name(original_file_name)
        file_path = self.output_dir / stored_file_name
        file_path.write_bytes(content_bytes)
        return {
            "stored_file_name": stored_file_name,
            "file_path": str(file_path.resolve()),
            "file_size": file_path.stat().st_size,
        }

    def delete_file(self, file_path):
        target = Path(file_path)
        if target.exists():
            target.unlink()
