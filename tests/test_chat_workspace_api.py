import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class ChatWorkspaceApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:", start_memory_worker=False)
        self.client = TestClient(self.app)

    def test_chat_session_listing_update_and_context(self):
        created = self.client.post(
            "/api/v1/chat/sessions",
            json={"title": "First workspace session", "status": "active"},
        )
        self.assertEqual(created.status_code, 200)
        session = created.json()

        listed = self.client.get("/api/v1/chat/sessions")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["id"], session["id"])

        updated = self.client.patch(
            f"/api/v1/chat/sessions/{session['id']}",
            json={"title": "Updated workspace session"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["title"], "Updated workspace session")

        context = self.client.get(f"/api/v1/chat/sessions/{session['id']}/context")
        self.assertEqual(context.status_code, 200)
        self.assertEqual(context.json()["session"]["id"], session["id"])
        self.assertEqual(context.json()["attachments"], [])

    def test_chat_attachment_upload_preview_and_delete(self):
        created = self.client.post(
            "/api/v1/chat/sessions",
            json={"title": "Attachment session", "status": "active"},
        )
        session_id = created.json()["id"]

        upload = self.client.post(
            "/api/v1/chat/attachments/upload",
            data={"session_id": session_id},
            files={"file": ("scan.png", b"fake-image-bytes", "image/png")},
        )
        self.assertEqual(upload.status_code, 200)
        attachment = upload.json()
        self.assertEqual(attachment["session_id"], session_id)

        preview = self.client.get(attachment["preview_url"])
        download = self.client.get(attachment["download_url"])
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(download.status_code, 200)

        deleted = self.client.delete(f"/api/v1/chat/attachments/{attachment['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])
