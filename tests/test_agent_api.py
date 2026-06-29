import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent.service import AgentExecutionError, PatientAgentService
from app.knowledge.repositories import MedicalKnowledgeRepository
from app.main import create_app
import app.agent.service as agent_service_module


class FakeBoundLLM(object):
    def __init__(self, responses):
        self.responses = list(responses)

    def invoke(self, messages):
        if not self.responses:
            raise AssertionError("No more fake LLM responses configured")
        return self.responses.pop(0)


class FakeToolCallingLLM(object):
    def __init__(self, responses):
        self.responses = responses

    def bind_tools(self, tools):
        return FakeBoundLLM(self.responses)


class RecordingBoundLLM(FakeBoundLLM):
    def __init__(self, responses):
        super(RecordingBoundLLM, self).__init__(responses)
        self.invocations = []

    def invoke(self, messages):
        self.invocations.append(messages)
        return super(RecordingBoundLLM, self).invoke(messages)


class RecordingToolCallingLLM(FakeToolCallingLLM):
    def __init__(self, responses):
        super(RecordingToolCallingLLM, self).__init__(responses)
        self.bound = None

    def bind_tools(self, tools):
        self.bound = RecordingBoundLLM(self.responses)
        return self.bound


class DummyChatOpenAI(object):
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class AgentApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            "sqlite:///:memory:",
            memory_database_url="sqlite:///:memory:",
            start_memory_worker=False,
        )
        self.client = TestClient(self.app)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app.state.image_storage_service.output_dir = Path(self.temp_dir.name)
        self.app.state.tts_service.output_dir = Path(self.temp_dir.name)

        patient_response = self.client.post(
            "/api/v1/patients",
            json={
                "patient_no": "PAG001",
                "name": "Liu Yang",
                "gender": "male",
                "phone": "13900000005",
                "id_card": "340101200106180015",
                "birth_date": "2001-06-18",
            },
        )
        self.assertEqual(patient_response.status_code, 200)
        self.patient = patient_response.json()

        record_response = self.client.post(
            "/api/v1/patients/{0}/medical-records".format(self.patient["id"]),
            json={
                "record_type": "followup",
                "diagnosis": "Right ankle sprain recovery",
                "chief_complaint": "Follow-up evaluation",
                "present_illness": "Swelling has improved but pain remains while walking.",
                "record_date": "2026-04-27",
            },
        )
        self.assertEqual(record_response.status_code, 200)
        self.record = record_response.json()

        visit_response = self.client.post(
            "/api/v1/patients/{0}/visits".format(self.patient["id"]),
            json={
                "visit_no": "VAG001",
                "visit_type": "outpatient",
                "visit_time": "2026-04-27T10:30:00",
                "department": "Orthopedics",
                "doctor_name": "Dr Wu",
                "status": "completed",
            },
        )
        self.assertEqual(visit_response.status_code, 200)

        image_bytes = b"\x89PNG\r\n\x1a\nmock-image"
        upload_response = self.client.post(
            "/api/v1/images/upload",
            json={
                "file_name": "ankle.png",
                "content_base64": base64.b64encode(image_bytes).decode("ascii"),
                "mime_type": "image/png",
                "patient_id": self.patient["id"],
                "record_id": self.record["id"],
                "image_type": "followup",
                "source": "test",
            },
        )
        self.assertEqual(upload_response.status_code, 200)
        self.image = upload_response.json()

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def _mock_audio(self):
        registry = self.app.state.mcp_registry

        def mock_synthesize_to_file(text, voice=None, file_name=None):
            output_path = self.app.state.tts_service.output_dir / "agent_result.mp3"
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

    def _set_fake_llm(self, responses):
        self.app.state.agent_service.llm = FakeToolCallingLLM(responses)
        self.app.state.agent_service.tool_calling_backend = "custom_llm"

    def _set_recording_llm(self, responses):
        llm = RecordingToolCallingLLM(responses)
        self.app.state.agent_service.llm = llm
        self.app.state.agent_service.tool_calling_backend = "custom_llm"
        return llm

    def _seed_medical_knowledge(self):
        with self.app.state.SessionLocal() as session:
            repo = MedicalKnowledgeRepository(session)
            document = repo.create_document(
                title="Blood Sugar Basics",
                source="test-fixture:diabetes-education",
                source_type="fixture",
                content="Blood sugar refers to glucose in the blood.",
            )
            repo.create_chunks(
                document.id,
                [
                    {
                        "content": "Blood sugar refers to glucose in the blood and is commonly reviewed with fasting glucose or HbA1c results.",
                        "search_text": "blood sugar glucose HbA1c fasting glucose 血糖 指标 检查",
                    }
                ],
            )

    def test_agent_graph_mode_defaults_to_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            service = PatientAgentService(
                self.app.state.SessionLocal,
                self.app.state.mcp_registry,
                llm=FakeToolCallingLLM([]),
            )

        self.assertFalse(service.graph_enabled)
        self.assertFalse(service.graph_require_langgraph)
        self.assertEqual(service.graph_runtime_status, "disabled")

    def test_agent_graph_require_langgraph_fails_when_dependency_missing(self):
        with patch.object(agent_service_module, "LangGraphStateGraph", None):
            with patch.dict(
                os.environ,
                {
                    "AGENT_GRAPH_ENABLED": "true",
                    "AGENT_GRAPH_REQUIRE_LANGGRAPH": "true",
                },
                clear=True,
            ):
                with self.assertRaises(AgentExecutionError) as error:
                    PatientAgentService(
                        self.app.state.SessionLocal,
                        self.app.state.mcp_registry,
                        llm=FakeToolCallingLLM([]),
                    )

        self.assertEqual(error.exception.error_code, "langgraph_dependency_missing")
        self.assertEqual(error.exception.status_code, 500)

    def test_agent_graph_mode_runs_task_board_patient_data_worker(self):
        self._mock_audio()
        self.app.state.agent_service.graph_enabled = True
        self.app.state.agent_service.graph_runtime_status = "available"
        registry = self.app.state.mcp_registry
        call_counter = {}
        original_invoke_tool = registry.invoke_tool

        def counting_invoke(tool_name, arguments, runtime_context=None):
            call_counter[tool_name] = call_counter.get(tool_name, 0) + 1
            return original_invoke_tool(tool_name, arguments, runtime_context=runtime_context)

        registry.invoke_tool = counting_invoke
        self._set_fake_llm([AIMessage(content="The graph latest visit summary is ready.", tool_calls=[])])

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Summarize my latest visit.",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertTrue(
            {
                "graph_preflight",
                "graph_planner",
                "graph_dispatcher",
                "graph_memory_agent",
                "graph_patient_data_agent",
                "graph_join",
                "graph_gap_checker",
                "graph_composer",
                "graph_postprocess",
            }.issubset(set(body["plan"]))
        )
        self.assertEqual(call_counter["identity.verify_patient_identity"], 1)
        self.assertEqual(call_counter["visit.search_visits"], 1)
        self.assertEqual(body["tool_calls"][0]["tool_name"], "visit.search_visits")
        self.assertIn("Found one visit", body["final_answer"])
        self.assertEqual(body["used_models"]["graph_mode"], "available")
        stages = {item.get("stage") for item in body["agent_trace"]}
        self.assertTrue(
            {
                "graph_preflight",
                "graph_planner",
                "graph_dispatcher",
                "graph_memory_agent",
                "graph_patient_data_agent",
                "graph_join",
                "graph_gap_checker",
                "graph_composer",
                "graph_postprocess",
            }.issubset(stages)
        )
        self.assertEqual(body["audio"]["audio_format"], "mp3")

    def test_agent_graph_patient_data_worker_calls_visit_and_record_for_complex_question(self):
        self.app.state.agent_service.graph_enabled = True
        self.app.state.agent_service.graph_runtime_status = "available"
        registry = self.app.state.mcp_registry
        call_counter = {}
        original_invoke_tool = registry.invoke_tool

        def counting_invoke(tool_name, arguments, runtime_context=None):
            call_counter[tool_name] = call_counter.get(tool_name, 0) + 1
            return original_invoke_tool(tool_name, arguments, runtime_context=runtime_context)

        registry.invoke_tool = counting_invoke
        self._set_fake_llm([])

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Summarize my latest visit and medical record.",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(call_counter["visit.search_visits"], 1)
        self.assertEqual(call_counter["medical_record.search_records"], 1)
        tool_names = [item["tool_name"] for item in body["tool_calls"]]
        self.assertIn("visit.search_visits", tool_names)
        self.assertIn("medical_record.search_records", tool_names)

    def test_agent_graph_image_worker_uses_uploaded_image_tool(self):
        self.app.state.agent_service.graph_enabled = True
        self.app.state.agent_service.graph_runtime_status = "available"
        registry = self.app.state.mcp_registry
        registry.qwen_client.api_key = "mock-key"
        registry.qwen_client.vision_model = "mock-vision-model"

        def mock_analyze_case_image(image_url, case_context, patient_context=None, clinical_question=None):
            return {
                "is_related": True,
                "relevance_level": "high",
                "visible_findings": ["Right ankle image"],
                "reasoning": "The image is highly relevant to the current ankle recovery case.",
                "limitations": ["For test only"],
                "suggested_follow_up": ["Combine with the in-person follow-up result"],
            }

        registry.qwen_client.analyze_case_image = mock_analyze_case_image
        self._set_fake_llm([AIMessage(content="This image is highly relevant to the current condition.", tool_calls=[])])

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Is this uploaded image related to the current condition?",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "image_id": self.image["id"],
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertIn("graph_image_analysis_agent", body["plan"])
        self.assertEqual(body["tool_calls"][0]["tool_name"], "image.analyze_uploaded_image")
        stages = {item.get("stage") for item in body["agent_trace"]}
        self.assertIn("graph_image_analysis_agent", stages)

    def test_agent_graph_high_risk_question_adds_warning_note(self):
        self.app.state.agent_service.graph_enabled = True
        self.app.state.agent_service.graph_runtime_status = "available"
        self._set_fake_llm([AIMessage(content="Blood pressure can be affected by many factors.", tool_calls=[])])

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "I have chest pain. What is blood pressure?",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertIn("graph_medical_knowledge_agent", body["plan"])
        self.assertIn("较高风险", body["final_answer"])

    def test_agent_graph_missing_dependency_falls_back_to_legacy_pipeline(self):
        self.app.state.agent_service.graph_enabled = True
        self.app.state.agent_service.graph_runtime_status = "missing_dependency_fallback"
        self._set_fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "patient.get_patient_profile",
                            "args": {},
                            "id": "call_profile_fallback",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Fallback profile summary is ready.", tool_calls=[]),
            ]
        )

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Show my patient profile.",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["plan"], ["preflight", "tool_calling", "postprocess"])
        self.assertEqual(body["used_models"]["graph_mode"], "missing_dependency_fallback")
        stages = {item.get("stage") for item in body["agent_trace"]}
        self.assertNotIn("graph_router", stages)
        self.assertIn("preflight", stages)

    def test_agent_graph_mode_identity_failure_keeps_403_semantics(self):
        self.app.state.agent_service.graph_enabled = True
        self.app.state.agent_service.graph_runtime_status = "available"

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Summarize my latest visit.",
                "patient_id": self.patient["id"],
                "verify_name": "Wrong Name",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers["X-Error-Code"], "identity_verification_failed")

    def test_agent_graph_medical_knowledge_adds_source_summary(self):
        self._seed_medical_knowledge()
        self.app.state.agent_service.graph_enabled = True
        self.app.state.agent_service.graph_runtime_status = "available"
        self._set_fake_llm([AIMessage(content="Blood sugar is glucose in the blood.", tool_calls=[])])

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "What is blood sugar?",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertIn("graph_medical_knowledge_agent", body["plan"])
        self.assertIn("Blood Sugar Basics", body["final_answer"])
        self.assertIn("参考来源", body["final_answer"])
        self.assertEqual(body["used_models"]["knowledge_retrieval_mode"], "keyword")
        stages = {item.get("stage") for item in body["agent_trace"]}
        self.assertIn("graph_medical_knowledge_agent", stages)

    def test_agent_graph_medical_knowledge_no_hit_does_not_fake_source(self):
        self._seed_medical_knowledge()
        self.app.state.agent_service.graph_enabled = True
        self.app.state.agent_service.graph_runtime_status = "available"
        self._set_fake_llm([AIMessage(content="No local source was found for this topic.", tool_calls=[])])

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "What is asthma?",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertIn("graph_medical_knowledge_agent", body["plan"])
        self.assertNotIn("参考来源", body["final_answer"])
        self.assertEqual(body["used_models"]["knowledge_retrieval_mode"], "keyword")

    def test_agent_legacy_path_does_not_trigger_medical_knowledge(self):
        self._seed_medical_knowledge()
        self._set_fake_llm([AIMessage(content="Blood sugar is glucose in the blood.", tool_calls=[])])

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "What is blood sugar?",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertNotIn("graph_medical_knowledge", body["plan"])
        self.assertNotIn("参考来源", body["final_answer"])
        self.assertEqual(body["used_models"]["knowledge_retrieval_mode"], "disabled")

    def test_agent_recent_visit_uses_search_tool_with_limit_one_and_single_identity_check(self):
        self._mock_audio()
        registry = self.app.state.mcp_registry
        call_counter = {}
        original_invoke_tool = registry.invoke_tool

        def counting_invoke(tool_name, arguments, runtime_context=None):
            call_counter[tool_name] = call_counter.get(tool_name, 0) + 1
            return original_invoke_tool(tool_name, arguments, runtime_context=runtime_context)

        registry.invoke_tool = counting_invoke
        self._set_fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "visit.search_visits",
                            "args": {"limit": 1, "sort_by": "visit_time", "sort_order": "desc"},
                            "id": "call_recent_visit",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="The latest visit summary is ready.", tool_calls=[]),
            ]
        )

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Summarize my latest visit.",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["intent"], "visit_query")
        self.assertTrue(body["session_id"])
        self.assertEqual(body["tool_calls"][0]["tool_name"], "visit.search_visits")
        self.assertEqual(body["tool_calls"][0]["arguments"]["limit"], 1)
        self.assertEqual(body["tool_calls"][0]["arguments"]["sort_by"], "visit_time")
        self.assertEqual(body["tool_calls"][0]["arguments"]["sort_order"], "desc")
        self.assertEqual(call_counter["identity.verify_patient_identity"], 1)
        self.assertEqual(call_counter["visit.search_visits"], 1)
        self.assertEqual(body["used_models"]["tool_calling"], self.app.state.agent_service.model_name)
        self.assertEqual(body["used_models"]["tool_calling_mode"], "custom_llm")
        self.assertEqual(body["audio"]["audio_format"], "mp3")
        self.assertTrue(Path(body["audio"]["file_path"]).exists())

    def test_agent_specific_date_followup_normalizes_date_filters(self):
        self._set_fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "visit.search_visits",
                            "args": {
                                "date_from": "2026-04-27",
                                "date_to": "2026-04-27",
                                "department": "Orthopedics",
                            },
                            "id": "call_date_visit",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="I found the follow-up visit on April 27.", tool_calls=[]),
            ]
        )

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Find the follow-up visit on April 27.",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        arguments = body["tool_calls"][0]["arguments"]
        self.assertEqual(body["tool_calls"][0]["tool_name"], "visit.search_visits")
        self.assertTrue(arguments["date_from"].startswith("2026-04-27T00:00:00"))
        self.assertTrue(arguments["date_to"].startswith("2026-04-27T23:59:59"))
        self.assertEqual(arguments["department"], "Orthopedics")
        self.assertIn("April 27", body["final_answer"])

    def test_agent_visit_no_query_uses_visit_no_lookup_with_search_tool(self):
        self._set_fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "visit.search_visits",
                            "args": {"visit_no": "VAG001"},
                            "id": "call_visit_no",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="I found visit VAG001.", tool_calls=[]),
            ]
        )

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Find visit VAG001.",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        arguments = body["tool_calls"][0]["arguments"]
        self.assertEqual(body["tool_calls"][0]["tool_name"], "visit.search_visits")
        self.assertEqual(arguments["visit_no"], "VAG001")
        self.assertEqual(arguments["limit"], 1)
        self.assertIsNone(body["audio"])

    def test_agent_invalid_patient_scope_returns_403(self):
        second_patient_response = self.client.post(
            "/api/v1/patients",
            json={
                "patient_no": "PAG002",
                "name": "Zhang Min",
                "gender": "female",
                "phone": "13800000009",
                "id_card": "110101199301018888",
            },
        )
        self.assertEqual(second_patient_response.status_code, 200)
        second_patient = second_patient_response.json()

        self._set_fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "visit.search_visits",
                            "args": {"patient_id": second_patient["id"]},
                            "id": "call_bad_scope",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        )

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Check my latest visit.",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("outside the currently verified patient scope", response.json()["detail"])

    def test_agent_image_query_uses_uploaded_image_tool(self):
        self._mock_audio()
        registry = self.app.state.mcp_registry
        registry.qwen_client.api_key = "mock-key"
        registry.qwen_client.vision_model = "mock-vision-model"

        def mock_analyze_case_image(image_url, case_context, patient_context=None, clinical_question=None):
            return {
                "is_related": True,
                "relevance_level": "high",
                "visible_findings": ["Right ankle image"],
                "reasoning": "The image is highly relevant to the current ankle recovery case.",
                "limitations": ["For test only"],
                "suggested_follow_up": ["Combine with the in-person follow-up result"],
            }

        registry.qwen_client.analyze_case_image = mock_analyze_case_image
        self._set_fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "image.analyze_uploaded_image",
                            "args": {"image_id": self.image["id"], "question": "Is this image related to the current condition?"},
                            "id": "call_image",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="This image is highly relevant to the current condition.", tool_calls=[]),
            ]
        )

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Is this uploaded image related to the current condition?",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "image_id": self.image["id"],
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["intent"], "image_analysis")
        self.assertTrue(body["session_id"])
        self.assertEqual(body["tool_calls"][0]["tool_name"], "image.analyze_uploaded_image")
        self.assertEqual(body["tool_calls"][0]["arguments"]["image_id"], self.image["id"])
        self.assertIn("relevant", body["final_answer"])

    def test_agent_followup_reuses_latest_session_attachment_when_request_has_no_image(self):
        registry = self.app.state.mcp_registry
        registry.qwen_client.api_key = "mock-key"
        registry.qwen_client.vision_model = "mock-vision-model"

        def mock_analyze_case_image(image_url, case_context, patient_context=None, clinical_question=None):
            return {
                "is_related": True,
                "relevance_level": "high",
                "visible_findings": ["Lab report image"],
                "reasoning": "The uploaded report image is available for follow-up analysis.",
                "limitations": ["For test only"],
                "suggested_follow_up": ["Review the report values in detail"],
            }

        registry.qwen_client.analyze_case_image = mock_analyze_case_image

        create_session_response = self.client.post(
            "/api/v1/chat/sessions",
            json={
                "patient_id": self.patient["id"],
                "title": "Image follow-up",
                "status": "active",
            },
        )
        self.assertEqual(create_session_response.status_code, 200)
        session_id = create_session_response.json()["id"]

        attachment_upload = self.client.post(
            "/api/v1/chat/attachments/upload",
            files={"file": ("report.png", b"\x89PNG\r\n\x1a\nmock-report", "image/png")},
            data={"session_id": session_id, "patient_id": self.patient["id"]},
        )
        self.assertEqual(attachment_upload.status_code, 200)
        attachment = attachment_upload.json()

        self._set_fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "image.analyze_uploaded_image",
                            "args": {"question": "Please analyze the uploaded report."},
                            "id": "call_followup_image",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="I analyzed the uploaded report image.", tool_calls=[]),
            ]
        )

        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "session_id": session_id,
                "message": "This is a lab report. Please analyze it.",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["tool_calls"][0]["tool_name"], "image.analyze_uploaded_image")
        self.assertEqual(body["tool_calls"][0]["arguments"]["image_id"], attachment["image_id"])
        self.assertEqual(body["attachments"][0]["id"], attachment["id"])
        self.assertIn("uploaded report image", body["final_answer"])

    def test_agent_unrelated_followup_does_not_reuse_latest_session_attachment(self):
        create_session_response = self.client.post(
            "/api/v1/chat/sessions",
            json={
                "patient_id": self.patient["id"],
                "title": "No sticky image",
                "status": "active",
            },
        )
        self.assertEqual(create_session_response.status_code, 200)
        session_id = create_session_response.json()["id"]

        attachment_upload = self.client.post(
            "/api/v1/chat/attachments/upload",
            files={"file": ("report.png", b"\x89PNG\r\n\x1a\nmock-report", "image/png")},
            data={"session_id": session_id, "patient_id": self.patient["id"]},
        )
        self.assertEqual(attachment_upload.status_code, 200)
        attachment = attachment_upload.json()

        recording_llm = self._set_recording_llm([AIMessage(content="This follow-up is unrelated to the image.", tool_calls=[])])
        response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "session_id": session_id,
                "message": "I caught a cold recently.",
                "verify_name": "Liu Yang",
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(recording_llm.bound)

        system_prompt = recording_llm.bound.invocations[0][0]["content"]
        self.assertIn("Image context: {}", system_prompt)
        self.assertNotIn(attachment["image_id"], system_prompt)
        self.assertEqual(response.json()["attachments"], [])

    def test_agent_persists_messages_and_restores_only_dialogue_history(self):
        self._set_fake_llm(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "visit.search_visits",
                            "args": {"limit": 1, "sort_by": "visit_time", "sort_order": "desc"},
                            "id": "call_history_visit",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="This is the previous visit summary.", tool_calls=[]),
            ]
        )

        first_response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "message": "Summarize the latest visit for me.",
                "patient_id": self.patient["id"],
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(first_response.status_code, 200)
        session_id = first_response.json()["session_id"]

        session_response = self.client.get("/api/v1/chat/sessions/{0}".format(session_id))
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.json()["id"], session_id)

        messages_response = self.client.get("/api/v1/chat/sessions/{0}/messages".format(session_id))
        self.assertEqual(messages_response.status_code, 200)
        messages = messages_response.json()
        message_types = [item["message_type"] for item in messages]
        self.assertIn("user_input", message_types)
        self.assertIn("identity_verification", message_types)
        self.assertIn("tool_call", message_types)
        self.assertIn("tool_result", message_types)
        self.assertIn("final_answer", message_types)

        visible_message_types = [item["message_type"] for item in messages if item["visible_in_context"]]
        self.assertEqual(visible_message_types, ["user_input", "final_answer"])

        recording_llm = self._set_recording_llm([AIMessage(content="Here is a shorter version.", tool_calls=[])])
        second_response = self.client.post(
            "/api/v1/agent/invoke",
            json={
                "session_id": session_id,
                "message": "Say that again in a shorter way.",
                "patient_id": self.patient["id"],
                "verify_phone": "13900000005",
                "with_audio": False,
            },
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertIsNotNone(recording_llm.bound)
        history_messages = recording_llm.bound.invocations[0]

        self.assertEqual(history_messages[0]["role"], "system")
        self.assertTrue(any(item.get("content") == "Summarize the latest visit for me." for item in history_messages if isinstance(item, dict)))
        self.assertTrue(any(item.get("content") == "This is the previous visit summary." for item in history_messages if isinstance(item, dict)))
        self.assertFalse(any(item.get("role") == "tool" for item in history_messages if isinstance(item, dict)))

    def test_build_llm_uses_explicit_qwen_provider_configuration(self):
        original_chat_openai = agent_service_module.ChatOpenAI
        env_backup = {
            key: os.environ.get(key)
            for key in [
                "AGENT_LLM_PROVIDER",
                "AGENT_LLM_MODEL",
                "AGENT_LLM_API_KEY",
                "AGENT_LLM_BASE_URL",
                "OPENAI_API_KEY",
                "OPENAI_MODEL",
                "QWEN_API_KEY",
                "QWEN_MODEL",
                "QWEN_BASE_URL",
                "DASHSCOPE_API_KEY",
            ]
        }
        try:
            agent_service_module.ChatOpenAI = DummyChatOpenAI
            os.environ["AGENT_LLM_PROVIDER"] = "qwen"
            os.environ["QWEN_API_KEY"] = "mock-qwen-key"
            os.environ["QWEN_MODEL"] = "qwen-plus"
            os.environ["QWEN_BASE_URL"] = "https://dashscope.example.test/compatible-mode/v1"
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("OPENAI_MODEL", None)
            os.environ.pop("AGENT_LLM_MODEL", None)
            os.environ.pop("AGENT_LLM_API_KEY", None)
            os.environ.pop("AGENT_LLM_BASE_URL", None)
            os.environ.pop("DASHSCOPE_API_KEY", None)

            service = PatientAgentService(self.app.state.SessionLocal, self.app.state.mcp_registry)

            self.assertIsInstance(service.llm, DummyChatOpenAI)
            self.assertEqual(service.model_name, "qwen-plus")
            self.assertEqual(service.tool_calling_backend, "langchain_qwen")
            self.assertEqual(service.llm.kwargs["base_url"], "https://dashscope.example.test/compatible-mode/v1")
            self.assertEqual(service.llm.kwargs["api_key"], "mock-qwen-key")
        finally:
            agent_service_module.ChatOpenAI = original_chat_openai
            for key, value in env_backup.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
