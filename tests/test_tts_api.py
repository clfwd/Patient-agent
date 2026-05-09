import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


class TtsApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = TestClient(self.app)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app.state.tts_service.output_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_synthesize_tts_file(self):
        service = self.app.state.tts_service

        def mock_synthesize_to_file(text, voice=None, file_name=None):
            output_path = service.output_dir / "tts_mock.mp3"
            output_path.write_bytes(b"ID3mockmp3")
            return {
                "file_name": output_path.name,
                "file_path": str(output_path.resolve()),
                "download_url": "/api/v1/tts/files/{0}".format(output_path.name),
                "transcript": text,
                "voice": voice or "Cherry",
                "model": "qwen3-omni-flash",
                "audio_format": "mp3",
                "sample_rate": 24000,
                "file_size": output_path.stat().st_size,
            }

        service.synthesize_to_file = mock_synthesize_to_file

        response = self.client.post(
            "/api/v1/tts/synthesize",
            json={"text": "请按时复诊。", "voice": "Cherry"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["file_name"], "tts_mock.mp3")
        self.assertTrue(Path(body["file_path"]).exists())
        self.assertEqual(body["transcript"], "请按时复诊。")
        self.assertEqual(body["audio_format"], "mp3")

    def test_download_tts_file(self):
        output_path = self.app.state.tts_service.output_dir / "tts_download.mp3"
        output_path.write_bytes(b"ID3mockmp3")

        response = self.client.get("/api/v1/tts/files/tts_download.mp3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertEqual(response.content, b"ID3mockmp3")
