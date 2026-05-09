import base64
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


class ImageApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = TestClient(self.app)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app.state.image_storage_service.output_dir = Path(self.temp_dir.name)

        patient_response = self.client.post(
            "/api/v1/patients",
            json={
                "patient_no": "PIMG001",
                "name": "图片测试患者",
                "gender": "男",
                "phone": "13812340001",
                "id_card": "110101199101011111",
            },
        )
        self.assertEqual(patient_response.status_code, 200)
        self.patient = patient_response.json()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_upload_and_get_uploaded_image(self):
        image_bytes = b"\x89PNG\r\n\x1a\nmock-image"
        payload = {
            "file_name": "ankle.png",
            "content_base64": base64.b64encode(image_bytes).decode("ascii"),
            "mime_type": "image/png",
            "patient_id": self.patient["id"],
            "image_type": "followup",
            "source": "test",
            "notes": "上传测试",
        }

        upload_response = self.client.post("/api/v1/images/upload", json=payload)
        self.assertEqual(upload_response.status_code, 200)
        uploaded = upload_response.json()

        self.assertEqual(uploaded["patient_id"], self.patient["id"])
        self.assertEqual(uploaded["mime_type"], "image/png")
        self.assertTrue(Path(uploaded["file_path"]).exists())

        detail_response = self.client.get("/api/v1/images/{0}".format(uploaded["id"]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["stored_file_name"], uploaded["stored_file_name"])
