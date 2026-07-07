"""Shared heuristic tool routing helpers."""

import re
from datetime import date


RECENT_KEYWORDS = ("最近", "最新", "recent", "latest")
VISIT_KEYWORDS = ("就诊", "复诊", "visit", "follow-up", "followup")
RECORD_KEYWORDS = ("病历", "病例", "病史", "诊断", "record", "diagnosis", "medical history")
IMAGE_KEYWORDS = ("图片", "图像", "影像", "image", "photo", "picture", "report", "scan", "x-ray")
IDENTITY_KEYWORDS = ("身份", "验证", "核验", "本人")
SPEECH_KEYWORDS = ("语音", "播报")


def extract_visit_no(message):
    match = re.search(r"\b([A-Z]{1,4}\d{3,})\b", message or "")
    return match.group(1) if match else None


def extract_day_constraint(message):
    if not message:
        return None

    iso_match = re.search(r"(20\d{2}-\d{2}-\d{2})", message)
    if iso_match:
        return iso_match.group(1)

    zh_match = re.search(r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日", message)
    if not zh_match:
        return None

    year = int(zh_match.group(1) or date.today().year)
    month = int(zh_match.group(2))
    day = int(zh_match.group(3))
    return date(year, month, day).isoformat()


def build_heuristic_tool_selection(message, context=None, include_verification_fields=False):
    context = context or {}
    metadata = dict(context.get("metadata") or {})
    arguments = {}

    if context.get("patient_id"):
        arguments["patient_id"] = context["patient_id"]
    if context.get("patient_no"):
        arguments["patient_no"] = context["patient_no"]
    if context.get("visit_no"):
        arguments["visit_no"] = context["visit_no"]

    if include_verification_fields:
        if context.get("verify_name"):
            arguments["name"] = context["verify_name"]
        if context.get("verify_phone"):
            arguments["phone"] = context["verify_phone"]
        if context.get("verify_id_card"):
            arguments["id_card"] = context["verify_id_card"]

    image_id = context.get("image_id") or metadata.get("image_id")
    if any(keyword in (message or "") for keyword in IMAGE_KEYWORDS):
        if image_id:
            return {
                "server_name": "image-resource",
                "tool_name": "image.analyze_uploaded_image",
                "arguments": {
                    "image_id": image_id,
                    "question": message,
                },
                "reason": "image_query",
            }
        image_arguments = dict(arguments)
        if metadata.get("image_url"):
            image_arguments["image_url"] = metadata["image_url"]
        if metadata.get("record_id"):
            image_arguments["record_id"] = metadata["record_id"]
        return {
            "server_name": "case-image-analysis",
            "tool_name": "case_image.analyze_image_relevance",
            "arguments": image_arguments,
            "reason": "image_query",
        }

    if any(keyword in (message or "") for keyword in SPEECH_KEYWORDS):
        return {
            "server_name": "speech-broadcast",
            "tool_name": "speech.generate_audio_file",
            "arguments": {
                "text": metadata.get("text") or message,
                "voice": metadata.get("voice"),
                "file_name": metadata.get("file_name"),
            },
            "reason": "speech_request",
        }

    if any(keyword in (message or "") for keyword in IDENTITY_KEYWORDS):
        return {
            "server_name": "identity-verification",
            "tool_name": "identity.verify_patient_identity",
            "arguments": arguments,
            "reason": "identity_request",
        }

    if any(keyword in (message or "") for keyword in VISIT_KEYWORDS):
        visit_arguments = dict(arguments)
        visit_no = context.get("visit_no") or extract_visit_no(message)
        if visit_no:
            visit_arguments["visit_no"] = visit_no
        day_constraint = extract_day_constraint(message)
        if day_constraint:
            visit_arguments["date_from"] = day_constraint
            visit_arguments["date_to"] = day_constraint
        if any(keyword in (message or "") for keyword in RECENT_KEYWORDS):
            visit_arguments.update({"limit": 1, "sort_by": "visit_time", "sort_order": "desc"})
        return {
            "server_name": "visit-record",
            "tool_name": "visit.search_visits",
            "arguments": visit_arguments,
            "reason": "visit_query",
        }

    if any(keyword in (message or "") for keyword in RECORD_KEYWORDS):
        record_arguments = dict(arguments)
        day_constraint = extract_day_constraint(message)
        if day_constraint:
            record_arguments["date_from"] = day_constraint
            record_arguments["date_to"] = day_constraint
        if any(keyword in (message or "") for keyword in RECENT_KEYWORDS):
            record_arguments.update({"limit": 1, "sort_by": "record_date", "sort_order": "desc"})
        return {
            "server_name": "medical-record",
            "tool_name": "medical_record.search_records",
            "arguments": record_arguments,
            "reason": "record_query",
        }

    return {
        "server_name": "patient-profile",
        "tool_name": "patient.get_patient_profile",
        "arguments": arguments,
        "reason": "patient_profile",
    }
