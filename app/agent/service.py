"""LangChain tool-calling-first patient agent service."""

import json
import os
import uuid
from datetime import datetime
from typing import Callable, Dict, List, Optional

import httpx

from app.db import ChatAttachmentRepository, ChatSessionRepository, MessageRepository, UploadedImageRepository
from app.error_handling import ServiceError
from app.tool_routing import build_heuristic_tool_selection

from .state import AgentState
from .tools import AgentToolValidationError, build_agent_tools

try:
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
except ImportError:  # pragma: no cover
    AgentExecutor = None
    create_tool_calling_agent = None
    ChatPromptTemplate = None
    MessagesPlaceholder = None

try:
    from langchain_core.messages import AIMessage as LangchainAIMessage
    from langchain_core.messages import HumanMessage
except ImportError:  # pragma: no cover
    LangchainAIMessage = None
    HumanMessage = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover
    ChatOpenAI = None

try:
    from langgraph.graph import StateGraph as LangGraphStateGraph
except ImportError:  # pragma: no cover
    LangGraphStateGraph = None


MAX_TOOL_CALLS = 6
DEFAULT_CONTEXT_MESSAGE_LIMIT = 6
TRUE_ENV_VALUES = ("1", "true", "yes", "on")
IMAGE_REFERENCE_KEYWORDS = (
    "这张图",
    "这个图",
    "图里",
    "图片里",
    "这份报告",
    "这个报告",
    "报告里",
    "检查报告",
    "片子",
    "影像",
    "刚才那张",
    "刚上传",
    "上一张图",
    "上一个报告",
)
IMAGE_REFERENCE_KEYWORDS_EN = (
    "this image",
    "this photo",
    "this picture",
    "this report",
    "uploaded image",
    "uploaded report",
    "lab report",
    "x-ray",
    "scan",
)


class AgentExecutionError(ServiceError):
    """Raised when agent execution fails."""


class ChatSessionRecorder(object):
    """Persist chat sessions and message events for one Agent invocation."""

    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session_id = None

    @staticmethod
    def _build_title(message, explicit_title=None):
        if explicit_title:
            return explicit_title[:255]
        text = (message or "").strip()
        return (text[:60] or "患者智能辅助会话")[:255]

    def ensure_session(self, session_id=None, patient_id=None, title=None, seed_message=None, status="active"):
        with self.session_factory() as session:
            repo = ChatSessionRepository(session)
            if session_id:
                chat_session = repo.get_by_id(session_id)
                if chat_session is None:
                    raise AgentExecutionError("Chat session was not found.", error_code="session_not_found")
            else:
                chat_session = repo.create_session(
                    patient_id=patient_id,
                    title=self._build_title(seed_message, explicit_title=title),
                    status=status,
                )
            self.session_id = chat_session.id
            return chat_session

    def bind_patient(self, patient_id):
        if not self.session_id or not patient_id:
            return None
        with self.session_factory() as session:
            return ChatSessionRepository(session).bind_patient(self.session_id, patient_id)

    def record_message(
        self,
        role,
        message_type,
        content=None,
        payload=None,
        visible_in_context=False,
        tool_name=None,
        tool_call_id=None,
    ):
        if not self.session_id:
            return None
        with self.session_factory() as session:
            return MessageRepository(session).create_message(
                session_id=self.session_id,
                role=role,
                message_type=message_type,
                content=content,
                payload=payload,
                visible_in_context=visible_in_context,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            )


class PatientAgentService(object):
    """Single-agent orchestration around generalized MCP tools."""

    def __init__(
        self,
        session_factory,
        mcp_registry,
        model=None,
        llm=None,
        memory_service=None,
        medical_knowledge_service=None,
    ):
        self.session_factory = session_factory
        self.mcp_registry = mcp_registry
        self.memory_service = memory_service
        self.medical_knowledge_service = medical_knowledge_service
        self._http_client = None
        self._http_async_client = None
        self.graph_enabled = self._env_flag("AGENT_GRAPH_ENABLED", default=False)
        self.graph_require_langgraph = self._env_flag("AGENT_GRAPH_REQUIRE_LANGGRAPH", default=False)
        self.graph_available = LangGraphStateGraph is not None
        self.graph_runtime_status = self._resolve_graph_runtime_status()
        self.requested_model = model
        self.model_name = model or os.getenv("AGENT_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o"
        self.tool_calling_backend = None
        self.llm_provider = None
        self.llm = llm or self._build_llm()
        if llm is not None and self.tool_calling_backend is None:
            self.tool_calling_backend = "custom_llm"

    @staticmethod
    def _env_flag(name, default=False):
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        return raw_value.strip().lower() in TRUE_ENV_VALUES

    def _resolve_graph_runtime_status(self):
        if not self.graph_enabled:
            return "disabled"
        if self.graph_available:
            return "available"
        if self.graph_require_langgraph:
            raise AgentExecutionError(
                "LangGraph mode requires the langgraph package, but it is not installed.",
                error_code="langgraph_dependency_missing",
                status_code=500,
            )
        return "missing_dependency_fallback"

    def _build_llm(self):
        if ChatOpenAI is None:
            return None

        provider = (os.getenv("AGENT_LLM_PROVIDER") or "").strip().lower()
        if not provider:
            if os.getenv("AGENT_LLM_API_KEY") or os.getenv("AGENT_LLM_MODEL") or os.getenv("AGENT_LLM_BASE_URL"):
                provider = "openai"
            elif os.getenv("OPENAI_API_KEY"):
                provider = "openai"
            elif os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"):
                provider = "qwen"
            else:
                return None

        if provider == "openai":
            api_key = os.getenv("AGENT_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("AGENT_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
            model_name = self.requested_model or os.getenv("AGENT_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o"
            backend = "langchain_openai"
        elif provider == "qwen":
            api_key = os.getenv("AGENT_LLM_API_KEY") or os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
            base_url = os.getenv("AGENT_LLM_BASE_URL") or os.getenv("QWEN_BASE_URL") or self.mcp_registry.qwen_client.base_url
            model_name = self.requested_model or os.getenv("AGENT_LLM_MODEL") or os.getenv("QWEN_MODEL") or self.mcp_registry.qwen_client.model
            backend = "langchain_qwen"
        else:
            return None

        if not api_key or not model_name:
            return None

        try:
            self._http_client = httpx.Client(trust_env=False)
            self._http_async_client = httpx.AsyncClient(trust_env=False)
            llm = ChatOpenAI(
                model=model_name,
                temperature=0.1,
                api_key=api_key,
                base_url=base_url,
                http_client=self._http_client,
                http_async_client=self._http_async_client,
            )
        except Exception:
            if self._http_client is not None:
                self._http_client.close()
                self._http_client = None
            if self._http_async_client is not None:
                try:
                    import asyncio

                    asyncio.run(self._http_async_client.aclose())
                except Exception:
                    pass
                self._http_async_client = None
            return None

        self.llm_provider = provider
        self.tool_calling_backend = backend
        self.model_name = model_name
        return llm

    def close(self):
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None
        if self._http_async_client is not None:
            try:
                import asyncio

                asyncio.run(self._http_async_client.aclose())
            except Exception:
                pass
            self._http_async_client = None

    def _attachment_to_read_model(self, attachment):
        return {
            "id": attachment.id,
            "kind": attachment.kind,
            "status": attachment.status,
            "session_id": attachment.session_id,
            "patient_id": attachment.patient_id,
            "record_id": attachment.record_id,
            "visit_id": attachment.visit_id,
            "image_id": attachment.image_id,
            "file_name": attachment.file_name,
            "mime_type": attachment.mime_type,
            "file_size": attachment.file_size,
            "width": attachment.width,
            "height": attachment.height,
            "preview_url": "/api/v1/chat/attachments/{0}/preview".format(attachment.id),
            "download_url": "/api/v1/chat/attachments/{0}/file".format(attachment.id),
            "source": attachment.source,
            "created_at": attachment.created_at,
        }

    @staticmethod
    def _should_reuse_latest_attachment(message):
        text = (message or "").strip()
        if not text:
            return False
        if any(keyword in text for keyword in IMAGE_REFERENCE_KEYWORDS):
            return True
        lowered = text.lower()
        return any(keyword in lowered for keyword in IMAGE_REFERENCE_KEYWORDS_EN)

    def _resolve_request_attachments(self, session_id, attachment_refs, message=None, image_id=None):
        refs = list(attachment_refs or [])
        resolved = []
        with self.session_factory() as session:
            attachment_repo = ChatAttachmentRepository(session)
            for ref in refs:
                attachment_id = ref.get("id") if isinstance(ref, dict) else getattr(ref, "id", None)
                if not attachment_id:
                    continue
                attachment = attachment_repo.get_by_id(attachment_id)
                if attachment is None:
                    raise AgentExecutionError("Chat attachment was not found.", error_code="image_not_found")
                if session_id and attachment.session_id != session_id:
                    attachment = attachment_repo.update_attachment(attachment.id, session_id=session_id)
                resolved.append(self._attachment_to_read_model(attachment))
            if not resolved and not image_id and session_id and self._should_reuse_latest_attachment(message):
                latest_attachment = attachment_repo.get_latest_by_session(session_id)
                if latest_attachment is not None:
                    resolved.append(self._attachment_to_read_model(latest_attachment))

        resolved_image_id = image_id
        if not resolved_image_id and resolved:
            resolved_image_id = resolved[0].get("image_id")
        return resolved, resolved_image_id

    def _build_initial_state(self, request, recorder, chat_session, attachments, resolved_image_id, event_callback=None):
        return AgentState(
            run_id=uuid.uuid4().hex,
            message=request.message,
            session_id=chat_session.id,
            session_patient_id=chat_session.patient_id,
            patient_id=request.patient_id,
            patient_no=request.patient_no,
            visit_no=request.visit_no,
            verify_name=request.verify_name,
            verify_phone=request.verify_phone,
            verify_id_card=request.verify_id_card,
            image_id=resolved_image_id,
            attachments=attachments,
            with_audio=request.with_audio,
            metadata=request.metadata,
            conversation_history=[],
            conversation_context_summary={},
            message_recorder=recorder,
            event_callback=event_callback,
            plan=["preflight", "tool_calling", "postprocess"],
            task_board=[],
            current_task=None,
            dispatched_tasks=[],
            task_results={},
            worker_events=[],
            proposed_tasks=[],
            suggested_followups=[],
            evidence_items=[],
            risk_flags=[],
            safety_level="normal",
            urgent_flags=[],
            answer_constraints=[],
            forbidden_claims=[],
            finish_reason=None,
            join_summary={},
            need_more_tasks=False,
            dispatch_round=0,
            max_dispatch_rounds=2,
            max_tasks=8,
            max_new_tasks_per_round=2,
            max_parallel_tasks=4,
            steps=[],
            tool_calls=[],
            agent_trace=[],
            attachments_result=attachments,
            knowledge_hits=[],
            knowledge_sources_text=None,
            planner_mode=None,
            planner_output_mode=None,
            replanner_mode=None,
            replanner_output_mode=None,
            errors=[],
        )

    def _record_user_message(self, state):
        recorder = state.get("message_recorder")
        if recorder is None:
            return None
        return recorder.record_message(
            role="user",
            message_type="user_input",
            content=state.get("message"),
            payload={
                "metadata": state.get("metadata") or {},
                "image_id": state.get("image_id"),
                "attachments": state.get("attachments") or [],
            },
            visible_in_context=True,
        )

    def _build_response(self, state):
        return {
            "session_id": state.get("session_id"),
            "run_id": state.get("run_id"),
            "intent": self._infer_intent(state),
            "plan": state.get("plan") or [],
            "steps": state.get("steps") or [],
            "tool_calls": state.get("tool_calls") or [],
            "agent_trace": state.get("agent_trace") or [],
            "identity_verification": state.get("identity_verification"),
            "final_answer": state.get("final_answer") or "",
            "audio": state.get("audio"),
            "attachments": state.get("attachments_result") or [],
            "used_models": {
                "tool_calling": self.model_name if state.get("tool_calling_mode") == "llm" else "heuristic-fallback",
                "tool_calling_mode": self.tool_calling_backend if state.get("tool_calling_mode") == "llm" else "heuristic-fallback",
                "vision": self.mcp_registry.qwen_client.vision_model if state.get("image_analysis") else None,
                "speech": self.mcp_registry.tts_service.model if state.get("audio") else None,
                "graph_mode": self.graph_runtime_status,
                "knowledge_retrieval_mode": state.get("knowledge_retrieval_mode") or "disabled",
                "planner_mode": state.get("planner_mode"),
                "planner_output_mode": state.get("planner_output_mode"),
                "replanner_mode": state.get("replanner_mode"),
                "replanner_output_mode": state.get("replanner_output_mode"),
            },
        }

    def _persist_final_answer(self, recorder, response):
        recorder.record_message(
            role="assistant",
            message_type="final_answer",
            content=response["final_answer"],
            payload={
                "intent": response["intent"],
                "audio": response["audio"],
                "run_id": response["run_id"],
                "attachments": response["attachments"],
            },
            visible_in_context=True,
        )

    def _run_legacy_pipeline(self, state):
        current_state = dict(state)
        current_state.update(self._preflight_node(current_state))
        current_state["conversation_history"] = self._load_conversation_history(current_state.get("session_id"))
        self._record_user_message(current_state)
        current_state.update(self._tool_calling_node(current_state))
        current_state.update(self._postprocess_node(current_state))
        return current_state

    def _run_graph_pipeline(self, state):
        from app.agent.graph.graph import run_agent_graph

        return run_agent_graph(self, state)

    def invoke(self, request, event_callback: Optional[Callable[[str, dict], None]] = None):
        recorder = ChatSessionRecorder(self.session_factory)
        session_title = (request.metadata or {}).get("session_title")
        chat_session = recorder.ensure_session(
            session_id=request.session_id,
            patient_id=request.patient_id,
            title=session_title,
            seed_message=request.message,
        )
        attachments, resolved_image_id = self._resolve_request_attachments(
            chat_session.id,
            request.attachments,
            message=request.message,
            image_id=request.image_id,
        )
        state = self._build_initial_state(request, recorder, chat_session, attachments, resolved_image_id, event_callback)
        if event_callback is not None:
            event_callback(
                "session.created",
                {
                    "session_id": chat_session.id,
                    "run_id": state.get("run_id"),
                },
            )

        try:
            if self.graph_runtime_status == "available":
                state = self._run_graph_pipeline(state)
            else:
                state = self._run_legacy_pipeline(state)
        except AgentExecutionError as exc:
            recorder.record_message(
                role="assistant",
                message_type="error",
                content=exc.detail,
                payload={"error_code": exc.error_code},
                visible_in_context=False,
            )
            raise

        response = self._build_response(state)
        self._persist_final_answer(recorder, response)
        if self.memory_service is not None:
            self.memory_service.maybe_create_extraction_job(
                session_id=state.get("session_id"),
                patient_id=state.get("patient_id"),
            )
        return response

    @staticmethod
    def _append_step(state, name, status, detail=None, tool_name=None):
        steps = list(state.get("steps") or [])
        step = {"name": name, "status": status}
        if detail:
            step["detail"] = detail
        if tool_name:
            step["tool_name"] = tool_name
        steps.append(step)
        return steps

    @staticmethod
    def _append_trace(state, event, status, detail, stage=None, **extra):
        trace = list(state.get("agent_trace") or [])
        item = {
            "stage": stage,
            "event": event,
            "status": status,
            "detail": detail,
            "created_at": datetime.utcnow(),
        }
        item.update({key: value for key, value in extra.items() if value is not None})
        trace.append(item)
        event_callback = state.get("event_callback")
        if event_callback is not None and stage:
            event_callback(
                "agent.phase",
                {
                    "run_id": state.get("run_id"),
                    "stage": stage,
                    "event": event,
                    "status": status,
                    "detail": detail,
                    "created_at": item["created_at"],
                },
            )
        return trace

    @staticmethod
    def _stringify_content(content):
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(str(item))
            return "".join(parts).strip()
        if content is None:
            return ""
        return str(content).strip()

    @staticmethod
    def _infer_intent(state):
        tool_calls = state.get("tool_calls") or []
        if tool_calls:
            tool_name = tool_calls[0].get("tool_name")
            if tool_name == "visit.search_visits":
                return "visit_query"
            if tool_name == "medical_record.search_records":
                return "record_query"
            if tool_name == "image.analyze_uploaded_image":
                return "image_analysis"
            if tool_name == "patient.get_patient_profile":
                return "patient_profile"
        if state.get("image_id"):
            return "image_analysis"
        return "general_assistant"

    def _load_conversation_history(self, session_id, limit=DEFAULT_CONTEXT_MESSAGE_LIMIT):
        with self.session_factory() as session:
            repo = MessageRepository(session)
            messages = repo.list_context_messages(session_id, limit=limit)
            history = []
            for item in messages:
                if item.role not in ("user", "assistant") or not item.content:
                    continue
                history.append({"role": item.role, "content": item.content})
            return history

    @staticmethod
    def _history_as_langchain_messages(state):
        if HumanMessage is None or LangchainAIMessage is None:
            return []
        messages = []
        for item in state.get("conversation_history") or []:
            role = item.get("role")
            content = item.get("content") or ""
            if not content:
                continue
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(LangchainAIMessage(content=content))
        return messages

    @staticmethod
    def _history_as_compat_messages(state):
        messages = []
        for item in state.get("conversation_history") or []:
            role = item.get("role")
            content = item.get("content") or ""
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        return messages

    def _load_image_context(self, image_id):
        if not image_id:
            return None
        with self.session_factory() as session:
            image = UploadedImageRepository(session).get_by_id(image_id)
            if image is None:
                raise AgentExecutionError("Uploaded image was not found.", error_code="image_not_found")
            return {
                "id": image.id,
                "patient_id": image.patient_id,
                "record_id": image.record_id,
                "visit_id": image.visit_id,
                "image_type": image.image_type,
                "original_file_name": image.original_file_name,
            }

    @staticmethod
    def _format_profile_memory_lines(memories):
        lines = []
        for item in memories or []:
            summary = (item or {}).get("summary")
            if summary:
                lines.append("- {0}".format(summary))
        return lines

    @staticmethod
    def _format_event_memory_lines(hit_items):
        lines = []
        for item in hit_items or []:
            memory = (item or {}).get("memory") or {}
            summary = memory.get("summary")
            if summary:
                lines.append("- {0}".format(summary))
        return lines

    def _preflight_node(self, state: AgentState):
        current_state = dict(state)
        metadata = dict(state.get("metadata") or {})
        if state.get("image_id") and "image_id" not in metadata:
            metadata["image_id"] = state["image_id"]

        current_state["steps"] = self._append_step(state, "preflight", "in_progress", "Starting identity verification and context loading.")
        current_state["agent_trace"] = self._append_trace(
            state,
            "system",
            "started",
            "Entering preflight stage.",
            stage="preflight",
        )
        current_state["metadata"] = metadata

        image_context = self._load_image_context(state.get("image_id"))
        if image_context and not current_state.get("patient_id"):
            current_state["patient_id"] = image_context.get("patient_id")
        if image_context and image_context.get("record_id") and "record_id" not in metadata:
            metadata["record_id"] = image_context["record_id"]

        verify_arguments = {
            "patient_id": current_state.get("patient_id"),
            "patient_no": current_state.get("patient_no"),
            "name": current_state.get("verify_name"),
            "phone": current_state.get("verify_phone"),
            "id_card": current_state.get("verify_id_card"),
        }
        if not any(verify_arguments.get(field) for field in ("patient_id", "patient_no", "name", "phone", "id_card")):
            raise AgentExecutionError(
                "Please provide patient locator fields or identity verification information before invoking the Agent.",
                error_code="invalid_tool_arguments",
            )

        result = self.mcp_registry.invoke_tool("identity.verify_patient_identity", verify_arguments)
        if not result.get("ok"):
            raise AgentExecutionError(
                result.get("detail") or result.get("error") or "Identity verification failed.",
                error_code=result.get("error") or "identity_verification_failed",
            )

        data = result.get("data") or {}
        if not data.get("verified"):
            reason = data.get("reason")
            error_code = {
                "patient_not_found": "patient_not_found",
                "missing_verification_fields": "identity_verification_required",
                "verification_failed": "identity_verification_failed",
            }.get(reason, "identity_verification_failed")
            raise AgentExecutionError(
                data.get("message") or reason or "Identity verification failed.",
                error_code=error_code,
            )

        patient = data.get("patient") or {}
        session_patient_id = current_state.get("session_patient_id")
        if session_patient_id and session_patient_id != patient.get("id"):
            raise AgentExecutionError(
                "Chat session belongs to a different patient.",
                error_code="patient_context_mismatch",
            )
        recorder = current_state.get("message_recorder")
        if recorder is not None:
            recorder.bind_patient(patient.get("id"))
            recorder.record_message(
                role="system",
                message_type="identity_verification",
                content="Identity verification passed.",
                payload=data,
                visible_in_context=False,
            )

        current_state["identity_verification"] = data
        current_state["verified_patient"] = patient
        current_state["allowed_patient_id"] = patient.get("id")
        current_state["patient_id"] = patient.get("id")
        current_state["patient_no"] = patient.get("patient_no")
        current_state["image_context"] = image_context
        if current_state.get("skip_long_term_memory_preflight"):
            recalled = {
                "profiles": [],
                "dense_hits": [],
                "keyword_hits": [],
                "fused_hits": [],
            }
        elif self.memory_service is not None:
            try:
                recalled = self.memory_service.recall_long_term_memories(patient.get("id"), current_state.get("message") or "")
            except Exception:
                recalled = {
                    "profiles": [],
                    "dense_hits": [],
                    "keyword_hits": [],
                    "fused_hits": [],
                }
        else:
            recalled = {
                "profiles": [],
                "dense_hits": [],
                "keyword_hits": [],
                "fused_hits": [],
            }
        current_state["long_term_profile_memories"] = recalled.get("profiles") or []
        current_state["long_term_event_memories"] = recalled.get("fused_hits") or []
        current_state["steps"] = self._append_step(
            current_state,
            "preflight",
            "completed",
            "Identity verification and patient context are ready.",
        )
        current_state["agent_trace"] = self._append_trace(
            current_state,
            "system",
            "completed",
            "Preflight completed.",
            stage="preflight",
        )
        return {
            "metadata": metadata,
            "steps": current_state["steps"],
            "agent_trace": current_state["agent_trace"],
            "identity_verification": current_state["identity_verification"],
            "verified_patient": current_state["verified_patient"],
            "allowed_patient_id": current_state["allowed_patient_id"],
            "patient_id": current_state["patient_id"],
            "patient_no": current_state["patient_no"],
            "image_context": current_state["image_context"],
            "long_term_profile_memories": current_state["long_term_profile_memories"],
            "long_term_event_memories": current_state["long_term_event_memories"],
        }

    def _tool_calling_system_prompt(self, state):
        patient_context = json.dumps(state.get("verified_patient") or {}, ensure_ascii=False)
        image_context = json.dumps(state.get("image_context") or {}, ensure_ascii=False)
        profile_memory_lines = self._format_profile_memory_lines(state.get("long_term_profile_memories") or [])
        event_memory_lines = self._format_event_memory_lines(state.get("long_term_event_memories") or [])
        profile_memory_text = "\n".join(profile_memory_lines) if profile_memory_lines else "- none"
        event_memory_text = "\n".join(event_memory_lines) if event_memory_lines else "- none"
        return (
            "You are the internal tool-calling coordinator for a patient assistant. "
            "Use tools to retrieve grounded data instead of inventing facts. "
            "Prefer the generalized search tools visit.search_visits and medical_record.search_records. "
            "Do not call speech.generate_audio_file because audio is handled in postprocess. "
            "Conversation history only contains user and assistant messages; tool traces are persisted separately. "
            "If information is missing, call tools first and then answer.\n"
            "Verified patient context: {0}\n"
            "Image context: {1}\n"
            "Relevant long-term profile memory:\n{2}\n"
            "Relevant long-term event memory:\n{3}"
        ).format(patient_context, image_context, profile_memory_text, event_memory_text)

    @staticmethod
    def _escape_prompt_template_text(text):
        return str(text).replace("{", "{{").replace("}", "}}")

    def _run_langchain_agent_executor(self, state, toolset):
        if self.llm is not None and self.tool_calling_backend is None:
            self.tool_calling_backend = "custom_llm"
        if self.llm is not None and hasattr(self.llm, "bind_tools") and not hasattr(self.llm, "invoke"):
            return self._run_compat_tool_loop(state, toolset)

        if (
            self.llm is None
            or AgentExecutor is None
            or create_tool_calling_agent is None
            or ChatPromptTemplate is None
            or MessagesPlaceholder is None
            or not toolset["langchain_tools"]
        ):
            return None

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self._escape_prompt_template_text(self._tool_calling_system_prompt(state))),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
        try:
            agent = create_tool_calling_agent(self.llm, toolset["langchain_tools"], prompt)
            executor = AgentExecutor(
                agent=agent,
                tools=toolset["langchain_tools"],
                return_intermediate_steps=True,
                max_iterations=MAX_TOOL_CALLS,
                handle_parsing_errors=True,
            )
            state["agent_trace"] = self._append_trace(
                state,
                "llm",
                "started",
                "Starting LangChain tool-calling agent.",
                stage="tool_calling",
            )
            result = executor.invoke(
                {
                    "input": state.get("message") or "",
                    "chat_history": self._history_as_langchain_messages(state),
                }
            )
            state["agent_trace"] = self._append_trace(
                state,
                "llm",
                "completed",
                "LangChain tool-calling agent produced a final answer.",
                stage="tool_calling",
            )
            return self._stringify_content(result.get("output"))
        except AgentToolValidationError as exc:
            state["errors"] = list(state.get("errors") or []) + [str(exc)]
            raise AgentExecutionError(str(exc), error_code=exc.error_code, status_code=exc.status_code)
        except Exception as exc:
            state["agent_trace"] = self._append_trace(
                state,
                "llm",
                "failed",
                "LangChain tool-calling agent failed and will fall back to heuristics.",
                stage="tool_calling",
                error=str(exc),
            )
            return None

    def _run_compat_tool_loop(self, state, toolset):
        bound_llm = self.llm.bind_tools(toolset["langchain_tools"])
        messages = [{"role": "system", "content": self._tool_calling_system_prompt(state)}]
        messages.extend(self._history_as_compat_messages(state))
        messages.append({"role": "user", "content": state.get("message") or ""})
        total_calls = 0
        state["agent_trace"] = self._append_trace(
            state,
            "llm",
            "started",
            "Starting compatibility tool-calling loop.",
            stage="tool_calling",
        )

        while total_calls < MAX_TOOL_CALLS:
            ai_message = bound_llm.invoke(messages)
            content = self._stringify_content(getattr(ai_message, "content", ""))
            tool_calls = getattr(ai_message, "tool_calls", None) or []
            messages.append(ai_message)

            if not tool_calls:
                state["agent_trace"] = self._append_trace(
                    state,
                    "llm",
                    "completed",
                    "Compatibility tool-calling loop produced a final answer.",
                    stage="tool_calling",
                )
                return content

            for tool_call in tool_calls:
                tool_name = tool_call.get("name")
                arguments = tool_call.get("args") or {}
                try:
                    result = toolset["executor"].invoke(tool_name, arguments, tool_call_id=tool_call.get("id"))
                except AgentToolValidationError as exc:
                    state["errors"] = list(state.get("errors") or []) + [str(exc)]
                    raise AgentExecutionError(str(exc), error_code=exc.error_code, status_code=exc.status_code)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
                total_calls += 1

        raise AgentExecutionError("Tool calls exceeded the maximum iteration limit.", error_code="invalid_tool_arguments")

    def _heuristic_tool_plan(self, state):
        selection = build_heuristic_tool_selection(
            state.get("message") or "",
            {
                "patient_id": state.get("patient_id"),
                "patient_no": state.get("patient_no"),
                "visit_no": state.get("visit_no"),
                "image_id": state.get("image_id"),
                "metadata": state.get("metadata") or {},
            },
            include_verification_fields=False,
        )
        return [{"tool_name": selection["tool_name"], "arguments": selection.get("arguments") or {}}]

    def _run_heuristic_tool_loop(self, state, toolset):
        for item in self._heuristic_tool_plan(state):
            toolset["executor"].invoke(item["tool_name"], item.get("arguments") or {})
        return None

    def _tool_calling_node(self, state: AgentState):
        current_state = dict(state)
        current_state["steps"] = self._append_step(state, "tool_calling", "in_progress", "Starting tool selection and execution.")
        current_state["agent_trace"] = self._append_trace(
            state,
            "system",
            "started",
            "Entering tool_calling stage.",
            stage="tool_calling",
        )
        toolset = build_agent_tools(self.mcp_registry, self.session_factory, current_state)

        final_answer = self._run_langchain_agent_executor(current_state, toolset)
        tool_calling_mode = "llm"
        if not final_answer:
            tool_calling_mode = "heuristic"
            self._run_heuristic_tool_loop(current_state, toolset)

        current_state["tool_calling_mode"] = tool_calling_mode
        current_state["final_answer"] = final_answer
        current_state["steps"] = self._append_step(current_state, "tool_calling", "completed", "Tool execution finished.")
        current_state["agent_trace"] = self._append_trace(
            current_state,
            "system",
            "completed",
            "tool_calling completed.",
            stage="tool_calling",
        )
        return {
            "steps": current_state["steps"],
            "tool_calls": current_state.get("tool_calls") or [],
            "agent_trace": current_state["agent_trace"],
            "patient_profile": current_state.get("patient_profile"),
            "visit_search_result": current_state.get("visit_search_result"),
            "record_search_result": current_state.get("record_search_result"),
            "image_analysis": current_state.get("image_analysis"),
            "final_answer": current_state.get("final_answer"),
            "errors": current_state.get("errors") or [],
            "tool_calling_mode": tool_calling_mode,
        }

    def _build_fallback_answer(self, state):
        patient = state.get("verified_patient") or {}

        if state.get("image_analysis"):
            analysis = (state["image_analysis"].get("analysis") or {}).get("reasoning")
            if analysis:
                return analysis

        if state.get("visit_search_result"):
            visits = state["visit_search_result"].get("visits") or []
            if not visits:
                return "Identity verification passed, but no matching visit records were found."
            if len(visits) == 1:
                visit = visits[0]
                return "Found one visit for {0}: department={1}, time={2}, status={3}.".format(
                    patient.get("name") or patient.get("patient_no"),
                    visit.get("department") or "unknown",
                    visit.get("visit_time") or "unknown",
                    visit.get("status") or "unknown",
                )
            return "Found {0} matching visit records. You can narrow the date or department further.".format(len(visits))

        if state.get("record_search_result"):
            records = state["record_search_result"].get("records") or []
            if not records:
                return "Identity verification passed, but no matching medical records were found."
            if len(records) == 1:
                record = records[0]
                return "Found one medical record: diagnosis={0}, record_date={1}.".format(
                    record.get("diagnosis") or "unknown",
                    record.get("record_date") or "unknown",
                )
            return "Found {0} matching medical records. You can narrow the date or department further.".format(len(records))

        if state.get("patient_profile"):
            profile = state["patient_profile"]
            return "Found patient profile: name={0}, patient_no={1}.".format(
                profile.get("name") or "unknown",
                profile.get("patient_no") or "unknown",
            )

        return "The request was processed, but there was not enough tool output to generate a more specific answer."

    def _postprocess_node(self, state: AgentState):
        current_state = dict(state)
        current_state["steps"] = self._append_step(state, "postprocess", "in_progress", "Formatting the final answer and audio.")
        current_state["agent_trace"] = self._append_trace(
            state,
            "system",
            "started",
            "Entering postprocess stage.",
            stage="postprocess",
        )

        final_answer = (state.get("final_answer") or "").strip() or self._build_fallback_answer(current_state)
        knowledge_sources_text = (state.get("knowledge_sources_text") or "").strip()
        if knowledge_sources_text and knowledge_sources_text not in final_answer:
            final_answer = "{0}\n\n{1}".format(final_answer, knowledge_sources_text)
        current_state["final_answer"] = final_answer

        audio = None
        if state.get("with_audio"):
            result = self.mcp_registry.invoke_tool(
                "speech.generate_audio_file",
                {
                    "text": final_answer,
                    "voice": (state.get("metadata") or {}).get("voice"),
                    "file_name": (state.get("metadata") or {}).get("audio_file_name"),
                },
            )
            if not result.get("ok"):
                raise AgentExecutionError(
                    result.get("detail") or result.get("error") or "Audio generation failed.",
                    error_code=result.get("error") or "tool_execution_failed",
                )
            audio = result.get("data")

        current_state["steps"] = self._append_step(current_state, "postprocess", "completed", "Final answer and postprocess completed.")
        current_state["agent_trace"] = self._append_trace(
            current_state,
            "system",
            "completed",
            "postprocess completed.",
            stage="postprocess",
        )
        return {
            "steps": current_state["steps"],
            "agent_trace": current_state["agent_trace"],
            "final_answer": final_answer,
            "audio": audio,
        }
