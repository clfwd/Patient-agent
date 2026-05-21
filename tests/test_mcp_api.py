import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.mcp.qwen_client import QwenClient


class McpApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = TestClient(self.app)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app.state.tts_service.output_dir = Path(self.temp_dir.name)

        patient_response = self.client.post(
            "/api/v1/patients",
            json={
                "patient_no": "PMCP001",
                "name": "MCP测试患者",
                "gender": "男",
                "phone": "13800001111",
                "id_card": "110101199001018888",
                "birth_date": "1990-01-01",
            },
        )
        self.assertEqual(patient_response.status_code, 200)
        self.patient = patient_response.json()

        record_response = self.client.post(
            "/api/v1/patients/{0}/medical-records".format(self.patient["id"]),
            json={
                "record_type": "outpatient",
                "diagnosis": "感冒",
                "chief_complaint": "咳嗽两天",
                "record_date": "2026-04-29",
            },
        )
        self.assertEqual(record_response.status_code, 200)

        visit_response = self.client.post(
            "/api/v1/patients/{0}/visits".format(self.patient["id"]),
            json={
                "visit_no": "VMCP001",
                "visit_type": "outpatient",
                "visit_time": "2026-04-29T09:30:00",
                "department": "呼吸内科",
                "doctor_name": "李医生",
                "status": "已完成",
            },
        )
        self.assertEqual(visit_response.status_code, 200)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_mcp_servers_and_tools(self):
        server_response = self.client.get("/api/v1/mcp/servers")
        tool_response = self.client.get("/api/v1/mcp/tools")

        self.assertEqual(server_response.status_code, 200)
        self.assertEqual(tool_response.status_code, 200)
        self.assertGreaterEqual(len(server_response.json()), 5)

        tool_names = [item["name"] for item in tool_response.json()]
        self.assertIn("patient.get_patient_profile", tool_names)
        self.assertIn("medical_record.search_records", tool_names)
        self.assertIn("visit.search_visits", tool_names)
        self.assertIn("identity.verify_patient_identity", tool_names)
        self.assertIn("speech.generate_audio_file", tool_names)

    def test_invoke_sensitive_tool_requires_identity_verification(self):
        response = self.client.post(
            "/api/v1/mcp/tools/patient.get_patient_profile/invoke",
            json={"arguments": {"patient_no": "PMCP001"}},
        )
        self.assertEqual(response.status_code, 403)

    def test_invoke_patient_profile_tool_with_verification(self):
        response = self.client.post(
            "/api/v1/mcp/tools/patient.get_patient_profile/invoke",
            json={
                "arguments": {"patient_no": "PMCP001"},
                "verify_name": "MCP测试患者",
                "verify_phone": "13800001111",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["data"]["found"])
        self.assertEqual(body["data"]["patient"]["patient_no"], "PMCP001")
        self.assertTrue(body["verification"]["verified"])

    def test_invoke_identity_tool(self):
        response = self.client.post(
            "/api/v1/mcp/tools/identity.verify_patient_identity/invoke",
            json={
                "arguments": {
                    "patient_no": "PMCP001",
                    "name": "MCP测试患者",
                    "phone": "13800001111",
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["data"]["verified"])

    def test_invoke_agent_router_requires_verification(self):
        registry = self.app.state.mcp_registry
        registry.qwen_client.api_key = None

        response = self.client.post(
            "/api/v1/mcp/agent/invoke",
            json={
                "message": "请查询这个患者的就诊记录",
                "patient_id": self.patient["id"],
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_invoke_agent_router_with_heuristic_fallback_and_verification(self):
        registry = self.app.state.mcp_registry
        registry.qwen_client.api_key = None

        response = self.client.post(
            "/api/v1/mcp/agent/invoke",
            json={
                "message": "请查询这个患者最近一次就诊",
                "patient_id": self.patient["id"],
                "verify_name": "MCP测试患者",
                "verify_phone": "13800001111",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["route_source"], "heuristic")
        self.assertEqual(body["tool_name"], "visit.search_visits")
        self.assertEqual(body["arguments"]["limit"], 1)
        self.assertEqual(body["arguments"]["sort_by"], "visit_time")
        self.assertEqual(body["arguments"]["sort_order"], "desc")
        self.assertTrue(body["tool_result"]["found"])
        self.assertEqual(len(body["tool_result"]["visits"]), 1)
        self.assertTrue(body["identity_verification"]["verified"])
        self.assertIsNone(body["audio"])

    def test_case_image_search_query_endpoint_requires_verification(self):
        record_list = self.client.get("/api/v1/patients/{0}/medical-records".format(self.patient["id"]))
        self.assertEqual(record_list.status_code, 200)
        record_id = record_list.json()[0]["id"]

        response = self.client.post(
            "/api/v1/mcp/case-image/search-query",
            json={"record_id": record_id},
        )
        self.assertEqual(response.status_code, 403)

    def test_case_image_search_query_endpoint_with_verification(self):
        record_list = self.client.get("/api/v1/patients/{0}/medical-records".format(self.patient["id"]))
        self.assertEqual(record_list.status_code, 200)
        record_id = record_list.json()[0]["id"]

        response = self.client.post(
            "/api/v1/mcp/case-image/search-query",
            json={
                "record_id": record_id,
                "verify_name": "MCP测试患者",
                "verify_phone": "13800001111",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["found"])
        self.assertGreaterEqual(len(body["suggested_queries"]), 1)
        self.assertTrue(body["identity_verification"]["verified"])

    def test_case_image_analyze_endpoint_with_mocked_qwen(self):
        record_list = self.client.get("/api/v1/patients/{0}/medical-records".format(self.patient["id"]))
        self.assertEqual(record_list.status_code, 200)
        record_id = record_list.json()[0]["id"]

        registry = self.app.state.mcp_registry
        registry.qwen_client.api_key = "mock-key"
        registry.qwen_client.vision_model = "mock-vision-model"

        def mock_analyze_case_image(image_url, case_context, patient_context=None, clinical_question=None):
            return {
                "is_related": True,
                "relevance_level": "medium",
                "visible_findings": ["mock finding"],
                "reasoning": "mocked result",
                "limitations": ["仅用于测试"],
                "suggested_follow_up": ["建议医生复核"],
            }

        registry.qwen_client.analyze_case_image = mock_analyze_case_image

        response = self.client.post(
            "/api/v1/mcp/case-image/analyze",
            json={
                "record_id": record_id,
                "image_url": "https://example.com/case-image.jpg",
                "clinical_question": "这张图是否可能与当前病情相关？",
                "verify_name": "MCP测试患者",
                "verify_phone": "13800001111",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["found"])
        self.assertEqual(body["used_model"], "mock-vision-model")
        self.assertTrue(body["analysis"]["is_related"])
        self.assertTrue(body["identity_verification"]["verified"])

    def test_invoke_speech_tool_generates_mp3(self):
        registry = self.app.state.mcp_registry

        def mock_synthesize_to_file(text, voice=None, file_name=None):
            output_path = self.app.state.tts_service.output_dir / "mcp_audio.mp3"
            output_path.write_bytes(b"ID3mock")
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

        registry.tts_service.synthesize_to_file = mock_synthesize_to_file
        registry.servers["speech-broadcast"].tts_service = registry.tts_service

        response = self.client.post(
            "/api/v1/mcp/tools/speech.generate_audio_file/invoke",
            json={"arguments": {"text": "请按时复诊。"}},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["audio_format"], "mp3")
        self.assertTrue(Path(body["data"]["file_path"]).exists())

    def test_invoke_agent_router_with_audio_output(self):
        registry = self.app.state.mcp_registry
        registry.qwen_client.api_key = None

        def mock_synthesize_to_file(text, voice=None, file_name=None):
            output_path = self.app.state.tts_service.output_dir / "agent_answer.mp3"
            output_path.write_bytes(b"ID3mock")
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

        registry.tts_service.synthesize_to_file = mock_synthesize_to_file
        registry.servers["speech-broadcast"].tts_service = registry.tts_service

        response = self.client.post(
            "/api/v1/mcp/agent/invoke",
            json={
                "message": "请查询这个患者的就诊记录",
                "patient_id": self.patient["id"],
                "verify_name": "MCP测试患者",
                "verify_phone": "13800001111",
                "with_audio": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["audio"]["audio_format"], "mp3")
        self.assertTrue(Path(body["audio"]["file_path"]).exists())

    def test_qwen_case_image_prompt_format_is_safe(self):
        client = QwenClient(api_key="mock-key")

        def mock_post_chat(messages, model=None):
            return (
                '{"is_related": true, "relevance_level": "low", "visible_findings": [], '
                '"reasoning": "ok", "limitations": [], "suggested_follow_up": []}'
            )

        client._post_chat = mock_post_chat
        result = client.analyze_case_image(
            image_url="https://example.com/case.jpg",
            case_context={"diagnosis": "ankle sprain"},
            patient_context={"patient_no": "PMCP001"},
            clinical_question="Is this image related to the case?",
        )
        self.assertTrue(result["is_related"])
