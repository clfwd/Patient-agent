"""Agent tool wrappers with validation, normalization, and trusted context injection."""

import json
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, conint

from app.db import MedicalRecordRepository, PatientRepository, UploadedImageRepository, VisitRepository
from app.error_handling import ServiceError

try:
    from langchain_core.tools import StructuredTool
except ImportError:  # pragma: no cover
    StructuredTool = None


DEFAULT_LIMIT = 20
MAX_LIMIT = 50


class AgentToolValidationError(ServiceError):
    """Raised when a tool call is invalid for the current runtime context."""

    def __init__(self, detail, error_code="invalid_tool_arguments", status_code=None):
        super(AgentToolValidationError, self).__init__(detail, error_code=error_code, status_code=status_code)


class _AgentBaseModel(BaseModel):
    class Config:
        extra = "forbid"


class PatientProfileArgs(_AgentBaseModel):
    patient_id: Optional[str] = None
    patient_no: Optional[str] = None
    id_card: Optional[str] = None


class VisitSearchArgs(_AgentBaseModel):
    patient_id: Optional[str] = None
    patient_no: Optional[str] = None
    visit_no: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    department: Optional[str] = None
    visit_type: Optional[str] = None
    doctor_name: Optional[str] = None
    status: Optional[str] = None
    limit: conint(ge=1, le=MAX_LIMIT) = DEFAULT_LIMIT
    sort_by: str = "visit_time"
    sort_order: str = "desc"


class MedicalRecordSearchArgs(_AgentBaseModel):
    patient_id: Optional[str] = None
    patient_no: Optional[str] = None
    record_id: Optional[str] = None
    record_type: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    department: Optional[str] = None
    doctor_name: Optional[str] = None
    diagnosis_keyword: Optional[str] = None
    limit: conint(ge=1, le=MAX_LIMIT) = DEFAULT_LIMIT
    sort_by: str = "record_date"
    sort_order: str = "desc"


class ImageAnalyzeArgs(_AgentBaseModel):
    image_id: Optional[str] = None
    question: str


TOOL_ARGS_SCHEMA = {
    "patient.get_patient_profile": PatientProfileArgs,
    "visit.search_visits": VisitSearchArgs,
    "medical_record.search_records": MedicalRecordSearchArgs,
    "image.analyze_uploaded_image": ImageAnalyzeArgs,
}


def _append_trace(runtime_state, event_type, status, detail, **extra):
    trace = list(runtime_state.get("agent_trace") or [])
    item = {"event": event_type, "status": status, "detail": detail}
    item.update({key: value for key, value in extra.items() if value is not None})
    trace.append(item)
    runtime_state["agent_trace"] = trace
    return trace


def _append_tool_call(runtime_state, tool_name, arguments, ok, result=None, error=None):
    tool_calls = list(runtime_state.get("tool_calls") or [])
    tool_calls.append(
        {
            "tool_name": tool_name,
            "arguments": arguments,
            "ok": ok,
            "result": result,
            "error": error,
        }
    )
    runtime_state["tool_calls"] = tool_calls
    return tool_calls


def _persist_runtime_message(runtime_state, **message_data):
    recorder = runtime_state.get("message_recorder")
    if recorder is None:
        return None
    return recorder.record_message(**message_data)


def _normalize_sort(sort_by, sort_order, allowed_fields, default_field):
    normalized_sort_by = sort_by if sort_by in allowed_fields else default_field
    normalized_sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"
    return normalized_sort_by, normalized_sort_order


def _parse_date(value, field_name):
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise AgentToolValidationError(
            "{0} must use ISO date format like 2026-04-27.".format(field_name),
            error_code="invalid_tool_arguments",
        )


def _parse_datetime_bound(value, field_name, end_of_day=False):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        clock = time(23, 59, 59, 999999) if end_of_day else time.min
        return datetime.combine(value, clock)

    text = str(value)
    try:
        if "T" in text or " " in text:
            return datetime.fromisoformat(text)
        parsed_date = date.fromisoformat(text)
        clock = time(23, 59, 59, 999999) if end_of_day else time.min
        return datetime.combine(parsed_date, clock)
    except ValueError:
        raise AgentToolValidationError(
            "{0} must use ISO date or datetime format.".format(field_name),
            error_code="invalid_tool_arguments",
        )


def _ensure_date_range(date_from, date_to, field_name):
    if date_from and date_to and date_from > date_to:
        raise AgentToolValidationError(
            "{0} start time cannot be later than end time.".format(field_name),
            error_code="invalid_tool_arguments",
        )


def _resolve_patient_id(session_factory, arguments):
    with session_factory() as session:
        patient_repo = PatientRepository(session)
        record_repo = MedicalRecordRepository(session)
        visit_repo = VisitRepository(session)
        image_repo = UploadedImageRepository(session)

        if arguments.get("patient_id"):
            patient = patient_repo.get_by_id(arguments["patient_id"])
            return patient.id if patient else None
        if arguments.get("patient_no"):
            patient = patient_repo.get_by_patient_no(arguments["patient_no"])
            return patient.id if patient else None
        if arguments.get("record_id"):
            record = record_repo.get_by_id(arguments["record_id"])
            return record.patient_id if record else None
        if arguments.get("visit_no"):
            visit = visit_repo.get_by_visit_no(arguments["visit_no"])
            return visit.patient_id if visit else None
        if arguments.get("image_id"):
            image = image_repo.get_by_id(arguments["image_id"])
            return image.patient_id if image else None
    return None


def _inject_verified_patient(arguments, runtime_state):
    if any(arguments.get(field) for field in ("patient_id", "patient_no", "record_id", "visit_no", "image_id", "id_card")):
        return arguments
    allowed_patient_id = runtime_state.get("allowed_patient_id")
    if allowed_patient_id:
        arguments["patient_id"] = allowed_patient_id
    return arguments


def _enforce_patient_scope(arguments, runtime_state, session_factory):
    allowed_patient_id = runtime_state.get("allowed_patient_id")
    if not allowed_patient_id:
        return arguments

    target_patient_id = _resolve_patient_id(session_factory, arguments)
    if target_patient_id is None and arguments.get("patient_id"):
        target_patient_id = arguments.get("patient_id")

    if target_patient_id and target_patient_id != allowed_patient_id:
        raise AgentToolValidationError(
            "Tool arguments point to data outside the currently verified patient scope.",
            error_code="patient_context_mismatch",
        )
    return arguments


def _normalize_visit_arguments(arguments, runtime_state, session_factory):
    parsed = VisitSearchArgs.parse_obj(arguments).dict(exclude_none=True)
    parsed = _inject_verified_patient(parsed, runtime_state)
    parsed = _enforce_patient_scope(parsed, runtime_state, session_factory)

    sort_by, sort_order = _normalize_sort(
        parsed.get("sort_by"),
        parsed.get("sort_order"),
        {"visit_time", "created_at", "updated_at"},
        "visit_time",
    )
    parsed["sort_by"] = sort_by
    parsed["sort_order"] = sort_order
    if parsed.get("visit_no"):
        parsed["limit"] = 1

    date_from = _parse_datetime_bound(parsed.get("date_from"), "date_from")
    date_to = _parse_datetime_bound(parsed.get("date_to"), "date_to", end_of_day=True)
    _ensure_date_range(date_from, date_to, "visit search")
    if date_from:
        parsed["date_from"] = date_from
    else:
        parsed.pop("date_from", None)
    if date_to:
        parsed["date_to"] = date_to
    else:
        parsed.pop("date_to", None)
    return parsed


def _normalize_record_arguments(arguments, runtime_state, session_factory):
    parsed = MedicalRecordSearchArgs.parse_obj(arguments).dict(exclude_none=True)
    parsed = _inject_verified_patient(parsed, runtime_state)
    parsed = _enforce_patient_scope(parsed, runtime_state, session_factory)

    sort_by, sort_order = _normalize_sort(
        parsed.get("sort_by"),
        parsed.get("sort_order"),
        {"record_date", "created_at", "updated_at"},
        "record_date",
    )
    parsed["sort_by"] = sort_by
    parsed["sort_order"] = sort_order
    if parsed.get("record_id"):
        parsed["limit"] = 1

    date_from = _parse_date(parsed.get("date_from"), "date_from")
    date_to = _parse_date(parsed.get("date_to"), "date_to")
    _ensure_date_range(date_from, date_to, "record search")
    if date_from:
        parsed["date_from"] = date_from
    else:
        parsed.pop("date_from", None)
    if date_to:
        parsed["date_to"] = date_to
    else:
        parsed.pop("date_to", None)
    return parsed


def _normalize_patient_profile_arguments(arguments, runtime_state, session_factory):
    parsed = PatientProfileArgs.parse_obj(arguments).dict(exclude_none=True)
    parsed = _inject_verified_patient(parsed, runtime_state)
    parsed = _enforce_patient_scope(parsed, runtime_state, session_factory)
    if "patient_id" not in parsed and runtime_state.get("allowed_patient_id"):
        parsed["patient_id"] = runtime_state["allowed_patient_id"]
    return parsed


def _normalize_image_arguments(arguments, runtime_state, session_factory):
    parsed = ImageAnalyzeArgs.parse_obj(arguments).dict(exclude_none=True)
    parsed["image_id"] = parsed.get("image_id") or runtime_state.get("image_context", {}).get("id") or runtime_state.get("image_id")
    if not parsed.get("image_id"):
        raise AgentToolValidationError("image.analyze_uploaded_image requires image_id.", error_code="invalid_tool_arguments")
    parsed = _enforce_patient_scope(parsed, runtime_state, session_factory)
    if runtime_state.get("verified_patient"):
        parsed["patient_context"] = runtime_state["verified_patient"]
    return parsed


def validate_and_normalize_tool_call(tool_name, arguments, runtime_state, session_factory):
    arguments = dict(arguments or {})
    try:
        if tool_name == "visit.search_visits":
            return _normalize_visit_arguments(arguments, runtime_state, session_factory)
        if tool_name == "medical_record.search_records":
            return _normalize_record_arguments(arguments, runtime_state, session_factory)
        if tool_name == "patient.get_patient_profile":
            return _normalize_patient_profile_arguments(arguments, runtime_state, session_factory)
        if tool_name == "image.analyze_uploaded_image":
            return _normalize_image_arguments(arguments, runtime_state, session_factory)
    except ValidationError as exc:
        raise AgentToolValidationError(str(exc))
    raise AgentToolValidationError("Unsupported Agent tool: {0}".format(tool_name), error_code="tool_not_found")


class AgentToolExecutor(object):
    """Execute MCP tools under the current verified runtime context."""

    def __init__(self, registry, session_factory, runtime_state):
        self.registry = registry
        self.session_factory = session_factory
        self.runtime_state = runtime_state

    def runtime_context(self):
        identity = self.runtime_state.get("identity_verification") or {}
        return {
            "verified_patient_id": self.runtime_state.get("allowed_patient_id"),
            "matched_fields": identity.get("matched_fields") or [],
        }

    def _store_result(self, tool_name, result):
        if tool_name == "patient.get_patient_profile":
            self.runtime_state["patient_profile"] = result.get("patient")
        elif tool_name == "visit.search_visits":
            self.runtime_state["visit_search_result"] = result
        elif tool_name == "medical_record.search_records":
            self.runtime_state["record_search_result"] = result
        elif tool_name == "image.analyze_uploaded_image":
            self.runtime_state["image_analysis"] = result

    def invoke(self, tool_name, arguments, tool_call_id=None):
        normalized_arguments = validate_and_normalize_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            runtime_state=self.runtime_state,
            session_factory=self.session_factory,
        )
        _persist_runtime_message(
            self.runtime_state,
            role="tool",
            message_type="tool_call",
            content=None,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            payload={
                "tool_name": tool_name,
                "arguments": _json_safe(normalized_arguments),
            },
            visible_in_context=False,
        )
        _append_trace(
            self.runtime_state,
            "tool_call",
            "started",
            "Calling tool {0}".format(tool_name),
            tool_name=tool_name,
            arguments=_json_safe(normalized_arguments),
        )
        result = self.registry.invoke_tool(tool_name, normalized_arguments, runtime_context=self.runtime_context())
        if not result["ok"]:
            _append_tool_call(
                self.runtime_state,
                tool_name,
                _json_safe(normalized_arguments),
                False,
                error=result["error"],
            )
            _append_trace(
                self.runtime_state,
                "tool_call",
                "failed",
                "Tool {0} failed".format(tool_name),
                tool_name=tool_name,
                error=result.get("detail") or result["error"],
            )
            _persist_runtime_message(
                self.runtime_state,
                role="tool",
                message_type="tool_result",
                content=None,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                payload={
                    "ok": False,
                    "error": result["error"],
                    "detail": result.get("detail"),
                },
                visible_in_context=False,
            )
            raise AgentToolValidationError(
                result.get("detail") or result["error"],
                error_code=result.get("error") or "tool_execution_failed",
            )

        data = result["data"]
        self._store_result(tool_name, data)
        _append_tool_call(
            self.runtime_state,
            tool_name,
            _json_safe(normalized_arguments),
            True,
            result=_json_safe(data),
        )
        _append_trace(
            self.runtime_state,
            "tool_call",
            "completed",
            "Tool {0} completed".format(tool_name),
            tool_name=tool_name,
        )
        _persist_runtime_message(
            self.runtime_state,
            role="tool",
            message_type="tool_result",
            content=None,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            payload={
                "ok": True,
                "result": _json_safe(data),
            },
            visible_in_context=False,
        )
        return data


def _json_safe(value):
    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {key: _json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_json_safe(item) for item in value]
        return str(value)


def build_agent_tools(registry, session_factory, runtime_state):
    """Build LangChain tools plus a shared executor for runtime-aware invocation."""

    executor = AgentToolExecutor(registry=registry, session_factory=session_factory, runtime_state=runtime_state)
    langchain_tools: List[Any] = []
    tool_by_name: Dict[str, Any] = {}

    for tool_name, args_schema in TOOL_ARGS_SCHEMA.items():
        tool_meta = registry.tool_index[tool_name]

        def _make_func(bound_tool_name):
            def _invoke(**kwargs):
                return executor.invoke(bound_tool_name, kwargs)

            return _invoke

        invoke_func = _make_func(tool_name)
        if StructuredTool is not None:
            tool = StructuredTool.from_function(
                func=invoke_func,
                name=tool_name,
                description=tool_meta.description,
                args_schema=args_schema,
            )
        else:  # pragma: no cover
            tool = None
        if tool is not None:
            langchain_tools.append(tool)
            tool_by_name[tool_name] = tool

    return {
        "executor": executor,
        "langchain_tools": langchain_tools,
        "tool_by_name": tool_by_name,
    }
