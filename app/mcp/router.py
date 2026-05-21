"""MCP-style modular tool registry and business-domain servers."""

import base64
from contextlib import contextmanager
from pathlib import Path

from app.db import MedicalRecordRepository, PatientRepository, UploadedImageRepository, VisitRepository
from app.tool_routing import build_heuristic_tool_selection
from app.tts.service import TtsSynthesisError

from .qwen_client import QwenClient, QwenToolSelectionError


VERIFICATION_FIELDS = ("name", "phone", "id_card")
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
DEFAULT_SORT_ORDER = "desc"


def _mask_phone(phone):
    if not phone or len(phone) < 7:
        return phone
    return "{0}****{1}".format(phone[:3], phone[-4:])


def _mask_id_card(id_card):
    if not id_card or len(id_card) < 8:
        return id_card
    return "{0}********{1}".format(id_card[:4], id_card[-4:])


def _patient_to_dict(patient):
    if patient is None:
        return None
    return {
        "id": patient.id,
        "patient_no": patient.patient_no,
        "name": patient.name,
        "gender": patient.gender,
        "birth_date": patient.birth_date.isoformat() if patient.birth_date else None,
        "phone": _mask_phone(patient.phone),
        "id_card": _mask_id_card(patient.id_card),
        "address": patient.address,
    }


def _record_to_dict(record):
    if record is None:
        return None
    return {
        "id": record.id,
        "patient_id": record.patient_id,
        "record_type": record.record_type,
        "diagnosis": record.diagnosis,
        "chief_complaint": record.chief_complaint,
        "present_illness": record.present_illness,
        "past_history": record.past_history,
        "allergy_history": record.allergy_history,
        "medications": record.medications,
        "doctor_name": record.doctor_name,
        "department": record.department,
        "notes": record.notes,
        "record_date": record.record_date.isoformat() if record.record_date else None,
    }


def _visit_to_dict(visit):
    if visit is None:
        return None
    return {
        "id": visit.id,
        "patient_id": visit.patient_id,
        "visit_no": visit.visit_no,
        "visit_type": visit.visit_type,
        "department": visit.department,
        "doctor_name": visit.doctor_name,
        "visit_time": visit.visit_time.isoformat() if visit.visit_time else None,
        "status": visit.status,
        "complaint": visit.complaint,
        "diagnosis_summary": visit.diagnosis_summary,
        "treatment_plan": visit.treatment_plan,
    }


def _image_to_dict(image):
    if image is None:
        return None
    return {
        "id": image.id,
        "patient_id": image.patient_id,
        "record_id": image.record_id,
        "visit_id": image.visit_id,
        "image_type": image.image_type,
        "original_file_name": image.original_file_name,
        "stored_file_name": image.stored_file_name,
        "file_path": image.file_path,
        "mime_type": image.mime_type,
        "file_size": image.file_size,
        "source": image.source,
        "notes": image.notes,
        "created_at": image.created_at.isoformat() if image.created_at else None,
    }


def _collect_verification_fields(arguments):
    verification = {}
    for field in VERIFICATION_FIELDS:
        value = arguments.get(field)
        if value not in (None, ""):
            verification[field] = str(value)
    return verification


def _build_search_schema(extra_properties, required=None):
    properties = {
        "patient_id": {"type": "string", "description": "患者主键 ID"},
        "patient_no": {"type": "string", "description": "患者编号"},
        "date_from": {"type": "string", "description": "起始日期，ISO 格式"},
        "date_to": {"type": "string", "description": "结束日期，ISO 格式"},
        "sort_by": {"type": "string", "description": "排序字段"},
        "sort_order": {"type": "string", "enum": ["asc", "desc"], "default": DEFAULT_SORT_ORDER},
        "limit": {"type": "integer", "default": DEFAULT_LIMIT},
        "name": {"type": "string", "description": "身份核验姓名"},
        "phone": {"type": "string", "description": "身份核验手机号"},
        "id_card": {"type": "string", "description": "身份核验身份证号"},
    }
    properties.update(extra_properties)
    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


class DomainTool(object):
    """Represents a single callable tool under one MCP domain server."""

    def __init__(self, server_name, name, description, input_schema, handler):
        self.server_name = server_name
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler

    def to_dict(self):
        return {
            "server_name": self.server_name,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class BaseDomainServer(object):
    name = ""
    description = ""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    @contextmanager
    def session_scope(self):
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def list_tools(self):
        raise NotImplementedError

    def metadata(self):
        return {
            "name": self.name,
            "description": self.description,
            "tools": [tool.to_dict() for tool in self.list_tools()],
        }


class PatientProfileServer(BaseDomainServer):
    name = "patient-profile"
    description = "患者基础信息查询工具。"

    def list_tools(self):
        return [
            DomainTool(
                self.name,
                "patient.get_patient_profile",
                "查询已核验患者的基础档案信息，支持 patient_id、patient_no 或 id_card 定位。",
                {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string"},
                        "patient_no": {"type": "string"},
                        "id_card": {"type": "string"},
                        "name": {"type": "string", "description": "身份核验姓名"},
                        "phone": {"type": "string", "description": "身份核验手机号"},
                    },
                },
                self.get_patient_profile,
            )
        ]

    def get_patient_profile(self, arguments):
        patient_id = arguments.get("patient_id")
        patient_no = arguments.get("patient_no")
        id_card = arguments.get("id_card")

        with self.session_scope() as session:
            repo = PatientRepository(session)
            patient = None
            if patient_id:
                patient = repo.get_by_id(patient_id)
            elif patient_no:
                patient = repo.get_by_patient_no(patient_no)
            elif id_card:
                patient = repo.get_by_id_card(id_card)

            if patient is None:
                return {"found": False, "patient": None}
            return {"found": True, "patient": _patient_to_dict(patient)}


class MedicalRecordServer(BaseDomainServer):
    name = "medical-record"
    description = "病历搜索工具。"

    def list_tools(self):
        return [
            DomainTool(
                self.name,
                "medical_record.search_records",
                (
                    "按患者、病历编号、时间范围、科室、医生、诊断关键词等条件搜索病历。"
                    "同一个工具可覆盖最近病历、某次病历、某天病历和某科病历查询。"
                ),
                _build_search_schema(
                    {
                        "record_id": {"type": "string", "description": "病历记录 ID"},
                        "record_type": {"type": "string", "description": "病历类型"},
                        "department": {"type": "string", "description": "科室"},
                        "doctor_name": {"type": "string", "description": "医生姓名"},
                        "diagnosis_keyword": {"type": "string", "description": "诊断关键词"},
                    }
                ),
                self.search_records,
            )
        ]

    def _resolve_patient_id(self, session, patient_id=None, patient_no=None):
        if patient_id:
            return patient_id
        if patient_no:
            patient = PatientRepository(session).get_by_patient_no(patient_no)
            return patient.id if patient else None
        return None

    def search_records(self, arguments):
        with self.session_scope() as session:
            patient_id = self._resolve_patient_id(
                session,
                patient_id=arguments.get("patient_id"),
                patient_no=arguments.get("patient_no"),
            )
            records = MedicalRecordRepository(session).search_records(
                patient_id=patient_id,
                record_id=arguments.get("record_id"),
                record_type=arguments.get("record_type"),
                date_from=arguments.get("date_from"),
                date_to=arguments.get("date_to"),
                department=arguments.get("department"),
                doctor_name=arguments.get("doctor_name"),
                diagnosis_keyword=arguments.get("diagnosis_keyword"),
                limit=arguments.get("limit", DEFAULT_LIMIT),
                sort_by=arguments.get("sort_by") or "record_date",
                sort_order=arguments.get("sort_order") or DEFAULT_SORT_ORDER,
            )
            return {
                "found": bool(records),
                "records": [_record_to_dict(record) for record in records],
                "total": len(records),
            }


class VisitRecordServer(BaseDomainServer):
    name = "visit-record"
    description = "就诊搜索工具。"

    def list_tools(self):
        return [
            DomainTool(
                self.name,
                "visit.search_visits",
                (
                    "按患者、就诊流水号、时间范围、科室、就诊类型、医生、状态等条件搜索就诊记录。"
                    "同一个工具可覆盖最近一次、某一次、某个时间段和某科复诊查询。"
                ),
                _build_search_schema(
                    {
                        "visit_no": {"type": "string", "description": "就诊流水号"},
                        "department": {"type": "string", "description": "科室"},
                        "visit_type": {"type": "string", "description": "就诊类型"},
                        "doctor_name": {"type": "string", "description": "医生姓名"},
                        "status": {"type": "string", "description": "就诊状态"},
                    }
                ),
                self.search_visits,
            )
        ]

    def _resolve_patient_id(self, session, patient_id=None, patient_no=None):
        if patient_id:
            return patient_id
        if patient_no:
            patient = PatientRepository(session).get_by_patient_no(patient_no)
            return patient.id if patient else None
        return None

    def search_visits(self, arguments):
        with self.session_scope() as session:
            patient_id = self._resolve_patient_id(
                session,
                patient_id=arguments.get("patient_id"),
                patient_no=arguments.get("patient_no"),
            )
            visits = VisitRepository(session).search_visits(
                patient_id=patient_id,
                visit_no=arguments.get("visit_no"),
                date_from=arguments.get("date_from"),
                date_to=arguments.get("date_to"),
                department=arguments.get("department"),
                visit_type=arguments.get("visit_type"),
                doctor_name=arguments.get("doctor_name"),
                status=arguments.get("status"),
                limit=arguments.get("limit", DEFAULT_LIMIT),
                sort_by=arguments.get("sort_by") or "visit_time",
                sort_order=arguments.get("sort_order") or DEFAULT_SORT_ORDER,
            )
            return {
                "found": bool(visits),
                "visits": [_visit_to_dict(visit) for visit in visits],
                "total": len(visits),
            }


class IdentityVerificationServer(BaseDomainServer):
    name = "identity-verification"
    description = "患者身份核验工具。"

    def list_tools(self):
        return [
            DomainTool(
                self.name,
                "identity.verify_patient_identity",
                "根据 patient_id、patient_no 或身份字段组合校验患者身份。",
                {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string"},
                        "patient_no": {"type": "string"},
                        "name": {"type": "string"},
                        "phone": {"type": "string"},
                        "id_card": {"type": "string"},
                    },
                },
                self.verify_patient_identity,
            )
        ]

    @staticmethod
    def _resolve_patient(repo, arguments):
        if arguments.get("patient_id"):
            return repo.get_by_id(arguments.get("patient_id"))
        if arguments.get("patient_no"):
            return repo.get_by_patient_no(arguments.get("patient_no"))
        name = arguments.get("name")
        phone = arguments.get("phone")
        id_card = arguments.get("id_card")
        if name and phone:
            return repo.get_by_name_and_phone(name, phone)
        if name and id_card:
            return repo.get_by_name_and_id_card(name, id_card)
        if phone and id_card:
            patient = repo.get_by_id_card(id_card)
            if patient and str(patient.phone or "") == str(phone):
                return patient
        return None

    def verify_patient_identity(self, arguments):
        with self.session_scope() as session:
            repo = PatientRepository(session)
            patient = self._resolve_patient(repo, arguments)

            if patient is None:
                return {"verified": False, "matched_fields": [], "patient": None, "reason": "patient_not_found"}

            checks = []
            for field in VERIFICATION_FIELDS:
                provided = arguments.get(field)
                if provided is not None:
                    checks.append((field, str(getattr(patient, field) or "") == str(provided)))

            if not checks:
                return {
                    "verified": False,
                    "matched_fields": [],
                    "patient": _patient_to_dict(patient),
                    "reason": "missing_verification_fields",
                }

            matched_fields = [field for field, matched in checks if matched]
            verified = len(matched_fields) == len(checks)
            return {
                "verified": verified,
                "matched_fields": matched_fields,
                "patient": _patient_to_dict(patient) if verified else None,
                "reason": "verified" if verified else "verification_failed",
            }


class ImageResourceServer(BaseDomainServer):
    name = "image-resource"
    description = "已上传图片读取与分析工具。"

    def __init__(self, session_factory, qwen_client):
        super(ImageResourceServer, self).__init__(session_factory)
        self.qwen_client = qwen_client

    def list_tools(self):
        return [
            DomainTool(
                self.name,
                "image.get_uploaded_image",
                "根据 image_id 查询已上传图片的元数据。",
                {
                    "type": "object",
                    "properties": {
                        "image_id": {"type": "string"},
                    },
                    "required": ["image_id"],
                },
                self.get_uploaded_image,
            ),
            DomainTool(
                self.name,
                "image.analyze_uploaded_image",
                "根据 image_id 和问题调用视觉模型分析图片内容。",
                {
                    "type": "object",
                    "properties": {
                        "image_id": {"type": "string"},
                        "question": {"type": "string"},
                        "patient_context": {"type": "object"},
                    },
                    "required": ["image_id", "question"],
                },
                self.analyze_uploaded_image,
            ),
        ]

    def _resolve_image(self, session, image_id):
        return UploadedImageRepository(session).get_by_id(image_id)

    @staticmethod
    def _to_data_url(image):
        image_path = Path(image.file_path)
        image_bytes = image_path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        return "data:{0};base64,{1}".format(image.mime_type, encoded)

    def get_uploaded_image(self, arguments):
        with self.session_scope() as session:
            image = self._resolve_image(session, arguments.get("image_id"))
            return {"found": image is not None, "image": _image_to_dict(image)}

    def analyze_uploaded_image(self, arguments):
        if not self.qwen_client.is_configured():
            raise ValueError("Qwen API key 未配置，无法解析已上传图片。")

        with self.session_scope() as session:
            image = self._resolve_image(session, arguments.get("image_id"))
            if image is None:
                return {"found": False, "image": None, "analysis": {"error": "image_not_found"}}

            data_url = self._to_data_url(image)
            analysis = self.qwen_client.analyze_case_image(
                image_url=data_url,
                case_context={"image_type": image.image_type, "notes": image.notes},
                patient_context=arguments.get("patient_context") or {},
                clinical_question=arguments.get("question"),
            )
            return {
                "found": True,
                "image": _image_to_dict(image),
                "analysis": analysis,
                "used_model": self.qwen_client.vision_model,
            }


class CaseImageAnalysisServer(BaseDomainServer):
    name = "case-image-analysis"
    description = "基于病历和公开图片做相关性分析。"

    def __init__(self, session_factory, qwen_client):
        super(CaseImageAnalysisServer, self).__init__(session_factory)
        self.qwen_client = qwen_client

    def list_tools(self):
        return [
            DomainTool(
                self.name,
                "case_image.build_search_query",
                "根据病历摘要生成公开图片检索关键词。",
                {
                    "type": "object",
                    "properties": {
                        "record_id": {"type": "string"},
                        "patient_id": {"type": "string"},
                        "patient_no": {"type": "string"},
                        "name": {"type": "string"},
                        "phone": {"type": "string"},
                        "id_card": {"type": "string"},
                    },
                },
                self.build_search_query,
            ),
            DomainTool(
                self.name,
                "case_image.analyze_image_relevance",
                "结合病历摘要与公开图片 URL 判断图片是否与当前病情相关。",
                {
                    "type": "object",
                    "properties": {
                        "record_id": {"type": "string"},
                        "patient_id": {"type": "string"},
                        "patient_no": {"type": "string"},
                        "image_url": {"type": "string"},
                        "clinical_question": {"type": "string"},
                        "name": {"type": "string"},
                        "phone": {"type": "string"},
                        "id_card": {"type": "string"},
                    },
                    "required": ["image_url"],
                },
                self.analyze_image_relevance,
            ),
        ]

    def _load_record_and_patient(self, arguments):
        with self.session_scope() as session:
            record_repo = MedicalRecordRepository(session)
            patient_repo = PatientRepository(session)

            record = None
            if arguments.get("record_id"):
                record = record_repo.get_by_id(arguments.get("record_id"))
            elif arguments.get("patient_id"):
                record = record_repo.get_latest_by_patient(arguments.get("patient_id"))
            elif arguments.get("patient_no"):
                patient = patient_repo.get_by_patient_no(arguments.get("patient_no"))
                if patient is not None:
                    record = record_repo.get_latest_by_patient(patient.id)

            if record is None:
                return None, None

            patient = patient_repo.get_by_id(record.patient_id)
            return record, patient

    @staticmethod
    def _search_queries_from_record(record_summary):
        diagnosis = record_summary.get("diagnosis") or ""
        chief_complaint = record_summary.get("chief_complaint") or ""
        department = record_summary.get("department") or ""

        zh_parts = [part for part in [diagnosis, chief_complaint, department, "病例图片"] if part]
        en_parts = [part for part in [diagnosis, chief_complaint, "clinical image case"] if part]

        queries = []
        if zh_parts:
            queries.append(" ".join(zh_parts))
        if diagnosis:
            queries.append("{0} 医学影像".format(diagnosis))
        if chief_complaint:
            queries.append("{0} 临床表现 图片".format(chief_complaint))
        if en_parts:
            queries.append(" ".join(en_parts))

        deduped = []
        for query in queries:
            if query and query not in deduped:
                deduped.append(query)
        return deduped

    def build_search_query(self, arguments):
        record, patient = self._load_record_and_patient(arguments)
        if record is None:
            return {
                "found": False,
                "record_summary": None,
                "suggested_queries": [],
                "notes": "未找到可用于搜图的病历记录。",
            }

        record_summary = _record_to_dict(record)
        return {
            "found": True,
            "record_summary": record_summary,
            "suggested_queries": self._search_queries_from_record(record_summary),
            "notes": "可先用这些关键词查找公开图片，再将图片 URL 传入分析接口。",
        }

    def analyze_image_relevance(self, arguments):
        record, patient = self._load_record_and_patient(arguments)
        if record is None:
            return {
                "found": False,
                "record_summary": None,
                "patient_summary": None,
                "image_url": arguments.get("image_url"),
                "analysis": {"error": "未找到对应病历"},
                "used_model": None,
            }

        if not self.qwen_client.is_configured():
            raise ValueError("Qwen API key 未配置，无法进行图片相关性分析。")

        record_summary = _record_to_dict(record)
        patient_summary = _patient_to_dict(patient)
        analysis = self.qwen_client.analyze_case_image(
            image_url=arguments.get("image_url"),
            case_context=record_summary,
            patient_context=patient_summary,
            clinical_question=arguments.get("clinical_question"),
        )
        return {
            "found": True,
            "record_summary": record_summary,
            "patient_summary": patient_summary,
            "image_url": arguments.get("image_url"),
            "analysis": analysis,
            "used_model": self.qwen_client.vision_model,
        }


class SpeechBroadcastServer(BaseDomainServer):
    name = "speech-broadcast"
    description = "语音播报工具。"

    def __init__(self, session_factory, tts_service):
        super(SpeechBroadcastServer, self).__init__(session_factory)
        self.tts_service = tts_service

    def list_tools(self):
        return [
            DomainTool(
                self.name,
                "speech.generate_audio_file",
                "根据文本生成本地 mp3 语音文件，适合播报问答结果。",
                {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "voice": {"type": "string"},
                        "file_name": {"type": "string"},
                    },
                    "required": ["text"],
                },
                self.generate_audio_file,
            )
        ]

    def generate_audio_file(self, arguments):
        return self.tts_service.synthesize_to_file(
            text=arguments.get("text"),
            voice=arguments.get("voice"),
            file_name=arguments.get("file_name"),
        )


class HeuristicToolRouter(object):
    """Fallback router when Qwen is not configured."""

    @staticmethod
    def route(message, context):
        preferred_tool = context.get("prefer_tool")
        if preferred_tool:
            return {
                "tool_name": preferred_tool,
                "server_name": context.get("prefer_server"),
                "arguments": context.get("metadata", {}),
            }

        metadata = context.get("metadata", {})
        arguments = {}
        if context.get("patient_id"):
            arguments["patient_id"] = context["patient_id"]
        if context.get("patient_no"):
            arguments["patient_no"] = context["patient_no"]
        if context.get("visit_no"):
            arguments["visit_no"] = context["visit_no"]

        for field in VERIFICATION_FIELDS:
            if context.get(field):
                arguments[field] = context[field]
            elif field in metadata and metadata.get(field):
                arguments[field] = metadata[field]

        if "图片" in message or "图像" in message or "影像" in message:
            if metadata.get("image_id"):
                return {
                    "server_name": "image-resource",
                    "tool_name": "image.analyze_uploaded_image",
                    "arguments": {
                        "image_id": metadata["image_id"],
                        "question": message,
                    },
                }
            if metadata.get("image_url"):
                arguments["image_url"] = metadata["image_url"]
            if metadata.get("record_id"):
                arguments["record_id"] = metadata["record_id"]
            return {
                "server_name": "case-image-analysis",
                "tool_name": "case_image.analyze_image_relevance",
                "arguments": arguments,
            }

        if "语音" in message or "播报" in message:
            return {
                "server_name": "speech-broadcast",
                "tool_name": "speech.generate_audio_file",
                "arguments": {
                    "text": metadata.get("text") or message,
                    "voice": metadata.get("voice"),
                    "file_name": metadata.get("file_name"),
                },
            }

        if "身份" in message or "验证" in message or "核验" in message or "本人" in message:
            return {
                "server_name": "identity-verification",
                "tool_name": "identity.verify_patient_identity",
                "arguments": arguments,
            }

        if "就诊" in message or "复诊" in message:
            visit_arguments = dict(arguments)
            if "最近" in message or "最新" in message:
                visit_arguments.update({"limit": 1, "sort_by": "visit_time", "sort_order": "desc"})
            return {
                "server_name": "visit-record",
                "tool_name": "visit.search_visits",
                "arguments": visit_arguments,
            }

        if "病历" in message or "病例" in message or "病史" in message or "诊断" in message:
            record_arguments = dict(arguments)
            if "最近" in message or "最新" in message:
                record_arguments.update({"limit": 1, "sort_by": "record_date", "sort_order": "desc"})
            return {
                "server_name": "medical-record",
                "tool_name": "medical_record.search_records",
                "arguments": record_arguments,
            }

        return {
            "server_name": "patient-profile",
            "tool_name": "patient.get_patient_profile",
            "arguments": arguments,
        }


class HeuristicToolRouter(object):
    """Fallback router when Qwen is not configured."""

    @staticmethod
    def route(message, context):
        preferred_tool = context.get("prefer_tool")
        if preferred_tool:
            return {
                "tool_name": preferred_tool,
                "server_name": context.get("prefer_server"),
                "arguments": context.get("metadata", {}),
            }
        return build_heuristic_tool_selection(message, context, include_verification_fields=True)


class McpRegistry(object):
    """Registry and execution entrypoint for modular MCP-style tools."""

    def __init__(self, session_factory, servers, qwen_client=None, tts_service=None):
        self.session_factory = session_factory
        self.qwen_client = qwen_client or QwenClient()
        self.tts_service = tts_service
        self.servers = {server.name: server for server in servers}
        self.tool_index = {}
        for server in servers:
            for tool in server.list_tools():
                self.tool_index[tool.name] = tool

    @contextmanager
    def session_scope(self):
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    @staticmethod
    def _tool_requires_identity_verification(tool_name):
        if tool_name.startswith("identity.") or tool_name.startswith("speech."):
            return False
        sensitive_prefixes = ("patient.", "medical_record.", "visit.", "case_image.", "image.")
        return tool_name.startswith(sensitive_prefixes)

    def _resolve_patient_for_verification(self, session, arguments):
        patient_repo = PatientRepository(session)
        record_repo = MedicalRecordRepository(session)
        visit_repo = VisitRepository(session)
        image_repo = UploadedImageRepository(session)

        if arguments.get("patient_id"):
            return patient_repo.get_by_id(arguments.get("patient_id")), "patient_id"
        if arguments.get("patient_no"):
            return patient_repo.get_by_patient_no(arguments.get("patient_no")), "patient_no"
        if arguments.get("record_id"):
            record = record_repo.get_by_id(arguments.get("record_id"))
            if record is None:
                return None, "record_id"
            return patient_repo.get_by_id(record.patient_id), "record_id"
        if arguments.get("visit_no"):
            visit = visit_repo.get_by_visit_no(arguments.get("visit_no"))
            if visit is None:
                return None, "visit_no"
            return patient_repo.get_by_id(visit.patient_id), "visit_no"
        if arguments.get("image_id"):
            image = image_repo.get_by_id(arguments.get("image_id"))
            if image is None or not image.patient_id:
                return None, "image_id"
            return patient_repo.get_by_id(image.patient_id), "image_id"
        if arguments.get("id_card"):
            return patient_repo.get_by_id_card(arguments.get("id_card")), "id_card"
        return None, None

    def _verify_against_explicit_fields(self, patient, source, provided_fields):
        if not provided_fields:
            return {
                "required": True,
                "verified": False,
                "matched_fields": [],
                "reason": "identity_verification_required",
                "message": "敏感 MCP 工具调用前至少需要一个身份核验字段。",
                "patient_id": patient.id,
                "patient_no": patient.patient_no,
            }

        if source == "id_card" and len(provided_fields) == 1 and "id_card" in provided_fields:
            return {
                "required": True,
                "verified": False,
                "matched_fields": [],
                "reason": "identity_verification_required",
                "message": "仅使用身份证号定位患者时，还需要额外提供姓名或手机号作为第二因子。",
                "patient_id": patient.id,
                "patient_no": patient.patient_no,
            }

        matched_fields = []
        for field, provided in provided_fields.items():
            current_value = str(getattr(patient, field) or "")
            if current_value == str(provided):
                matched_fields.append(field)

        verified = len(matched_fields) == len(provided_fields)
        return {
            "required": True,
            "verified": verified,
            "matched_fields": matched_fields,
            "reason": "verified" if verified else "identity_verification_failed",
            "message": "身份核验通过。" if verified else "身份核验失败，提供的信息与患者档案不匹配。",
            "patient_id": patient.id,
            "patient_no": patient.patient_no,
        }

    def _verify_sensitive_tool_access(self, tool_name, arguments, runtime_context=None):
        if not self._tool_requires_identity_verification(tool_name):
            return None

        runtime_context = runtime_context or {}
        provided_fields = _collect_verification_fields(arguments)
        verified_patient_id = runtime_context.get("verified_patient_id")

        with self.session_scope() as session:
            patient, source = self._resolve_patient_for_verification(session, arguments)
            if patient is None and verified_patient_id:
                patient = PatientRepository(session).get_by_id(verified_patient_id)
                source = source or "agent_context"

            if patient is None:
                return {
                    "required": True,
                    "verified": False,
                    "matched_fields": [],
                    "reason": "patient_not_found",
                    "message": "未找到需要访问的患者记录。",
                }

            if verified_patient_id:
                if patient.id != verified_patient_id:
                    return {
                        "required": True,
                        "verified": False,
                        "matched_fields": [],
                        "reason": "patient_context_mismatch",
                        "message": "工具访问的患者与当前已核验患者不一致。",
                        "patient_id": patient.id,
                        "patient_no": patient.patient_no,
                    }
                return {
                    "required": True,
                    "verified": True,
                    "matched_fields": runtime_context.get("matched_fields") or [],
                    "reason": "agent_context_verified",
                    "message": "已使用 Agent 入口完成身份核验。",
                    "patient_id": patient.id,
                    "patient_no": patient.patient_no,
                }

            return self._verify_against_explicit_fields(patient, source, provided_fields)

    def _build_agent_audio(self, final_answer, request):
        if not request.with_audio:
            return None
        if self.tts_service is None:
            raise TtsSynthesisError("语音服务未初始化。")
        return self.tts_service.synthesize_to_file(
            text=final_answer,
            voice=(request.metadata or {}).get("voice"),
            file_name=(request.metadata or {}).get("audio_file_name"),
        )

    def list_servers(self):
        return [server.metadata() for server in self.servers.values()]

    def list_tools(self, server_name=None):
        if server_name:
            server = self.servers.get(server_name)
            if server is None:
                return []
            return [tool.to_dict() for tool in server.list_tools()]
        return [tool.to_dict() for tool in self.tool_index.values()]

    def invoke_tool(self, tool_name, arguments, runtime_context=None):
        tool = self.tool_index.get(tool_name)
        if tool is None:
            return {
                "ok": False,
                "server_name": "",
                "tool_name": tool_name,
                "data": None,
                "error": "tool_not_found",
                "detail": "Requested MCP tool does not exist.",
                "verification": None,
            }

        verification = self._verify_sensitive_tool_access(tool_name, arguments or {}, runtime_context=runtime_context)
        if verification and not verification.get("verified"):
            return {
                "ok": False,
                "server_name": tool.server_name,
                "tool_name": tool.name,
                "data": None,
                "error": verification["reason"],
                "detail": verification.get("message"),
                "verification": verification,
            }

        try:
            result = tool.handler(arguments or {})
            return {
                "ok": True,
                "server_name": tool.server_name,
                "tool_name": tool.name,
                "data": result,
                "error": None,
                "verification": verification,
            }
        except Exception as exc:
            return {
                "ok": False,
                "server_name": tool.server_name,
                "tool_name": tool.name,
                "data": None,
                "error": "tool_execution_failed",
                "detail": str(exc),
                "verification": verification,
            }

    def route_and_invoke(self, request):
        context = {
            "patient_id": request.patient_id,
            "patient_no": request.patient_no,
            "visit_no": request.visit_no,
            "verify_name": request.verify_name,
            "verify_phone": request.verify_phone,
            "verify_id_card": request.verify_id_card,
            "name": request.verify_name,
            "phone": request.verify_phone,
            "id_card": request.verify_id_card,
            "prefer_server": request.prefer_server,
            "prefer_tool": request.prefer_tool,
            "metadata": request.metadata,
            "with_audio": request.with_audio,
        }

        route_source = "heuristic"
        if self.qwen_client.is_configured():
            try:
                selection = self.qwen_client.select_tool(request.message, self.list_tools(), context)
                route_source = "qwen"
            except QwenToolSelectionError:
                if not request.allow_fallback:
                    raise
                selection = HeuristicToolRouter.route(request.message, context)
        else:
            selection = HeuristicToolRouter.route(request.message, context)

        arguments = dict(selection.get("arguments") or {})
        if request.patient_id and "patient_id" not in arguments:
            arguments["patient_id"] = request.patient_id
        if request.patient_no and "patient_no" not in arguments:
            arguments["patient_no"] = request.patient_no
        if request.visit_no and "visit_no" not in arguments:
            arguments["visit_no"] = request.visit_no
        if request.verify_name and "name" not in arguments:
            arguments["name"] = request.verify_name
        if request.verify_phone and "phone" not in arguments:
            arguments["phone"] = request.verify_phone
        if request.verify_id_card and "id_card" not in arguments:
            arguments["id_card"] = request.verify_id_card

        invoke_result = self.invoke_tool(selection["tool_name"], arguments)
        try:
            final_answer = self.qwen_client.summarize(
                request.message,
                selection["tool_name"],
                (
                    invoke_result.get("data")
                    if invoke_result["ok"]
                    else {"error": invoke_result["error"], "detail": invoke_result.get("detail")}
                ),
            )
        except QwenToolSelectionError:
            final_answer = self.qwen_client._fallback_summary(
                request.message,
                selection["tool_name"],
                (
                    invoke_result.get("data")
                    if invoke_result["ok"]
                    else {"error": invoke_result["error"], "detail": invoke_result.get("detail")}
                ),
            )

        audio = None
        if invoke_result["ok"] and request.with_audio:
            audio = self._build_agent_audio(final_answer, request)

        return {
            "route_source": route_source,
            "server_name": selection.get("server_name") or invoke_result["server_name"],
            "tool_name": selection["tool_name"],
            "arguments": arguments,
            "tool_result": (
                invoke_result.get("data")
                if invoke_result["ok"]
                else {"error": invoke_result["error"], "detail": invoke_result.get("detail")}
            ),
            "identity_verification": invoke_result.get("verification"),
            "final_answer": final_answer,
            "audio": audio,
            "used_model": self.qwen_client.model if route_source == "qwen" else None,
        }


def build_mcp_registry(session_factory, tts_service=None):
    qwen_client = QwenClient()
    return McpRegistry(
        session_factory=session_factory,
        servers=[
            PatientProfileServer(session_factory),
            MedicalRecordServer(session_factory),
            VisitRecordServer(session_factory),
            IdentityVerificationServer(session_factory),
            ImageResourceServer(session_factory, qwen_client),
            CaseImageAnalysisServer(session_factory, qwen_client),
            SpeechBroadcastServer(session_factory, tts_service),
        ],
        qwen_client=qwen_client,
        tts_service=tts_service,
    )
