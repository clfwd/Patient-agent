"""Extraction logic for turning recent dialogue windows into long-term memories."""

import json
import re
from datetime import datetime, timedelta


class MemoryExtractionError(Exception):
    """Raised when LLM extraction fails."""

    def __init__(self, message, retryable=True):
        super(MemoryExtractionError, self).__init__(message)
        self.retryable = retryable


class LongTermMemoryExtractor(object):
    """Extract structured event and profile memories from a message window."""

    def __init__(self, llm=None):
        self.llm = llm

    @staticmethod
    def _serialize_messages(messages):
        items = []
        for message in messages:
            items.append(
                {
                    "id": message.get("id"),
                    "sequence_no": message.get("sequence_no"),
                    "role": message.get("role"),
                    "message_type": message.get("message_type"),
                    "content": message.get("content"),
                    "tool_name": message.get("tool_name"),
                    "payload": message.get("payload"),
                }
            )
        return items

    def build_prompt(self, patient_id, session_id, messages):
        return (
            "You extract long-term patient memories from recent dialogue.\n"
            "Return valid JSON only with keys `events` and `profiles`.\n"
            "Only keep durable, reusable information.\n"
            "Event schema: category, summary, payload, confidence_score, occurred_at, source_message_ids.\n"
            "Profile schema: key, value, summary, confidence_score.\n"
            "Rules:\n"
            "- Ignore identity verification boilerplate.\n"
            "- Do not extract demographics, identifiers, age, sex, birth date, patient name, phone, or id numbers.\n"
            "- Do not restate visit records or medical records as long-term memory.\n"
            "- Only keep dialogue-derived incremental memory useful for future personalization or cross-session recall.\n"
            "- Prefer symptom progression, medication adherence, follow-up commitment, care context, temporary risk signal, and communication preferences.\n"
            "- For profiles, prefer canonical keys: preferred_summary_length, communication_style, explanation_preference, caregiver_role, response_language_preference.\n"
            "- If the user asks for shorter or conclusion-first answers, use key `preferred_summary_length` with value `concise`.\n"
            "- Only include event memories when confidence_score >= 0.75.\n"
            "- Only include profile memories when confidence_score >= 0.80.\n"
            "- `source_message_ids` must reference user or assistant messages from the window.\n"
            "- Output empty arrays when no memory should be stored.\n"
            "Patient ID: {0}\n"
            "Session ID: {1}\n"
            "Window messages:\n{2}"
        ).format(patient_id, session_id, json.dumps(self._serialize_messages(messages), ensure_ascii=False, default=str))

    @staticmethod
    def _extract_json_block(text):
        text = (text or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            pass
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        return json.loads(match.group(0))

    @staticmethod
    def _fallback_extract(messages):
        events = []
        profiles = []
        user_inputs = [item for item in messages if item.get("role") == "user" and item.get("content")]
        for item in user_inputs:
            content = item["content"]
            if "一句话" in content or "简短" in content or "简洁" in content:
                profiles.append(
                    {
                        "key": "preferred_summary_length",
                        "value": "concise",
                        "summary": "用户偏好简短、高信号的总结。",
                        "confidence_score": 0.82,
                    }
                )
            if "最近一次就诊" in content or "就诊情况" in content or "继续跟进" in content:
                events.append(
                    {
                        "category": "followup_commitment",
                        "summary": "用户连续追问近期病情和就诊背景，后续仍可能围绕同一问题继续咨询。",
                        "payload": {"topic": "recent_visit_follow_up"},
                        "confidence_score": 0.76,
                        "occurred_at": None,
                        "source_message_ids": [item.get("id")] if item.get("id") else [],
                    }
                )
        return {"events": events[:3], "profiles": profiles[:3]}

    def extract(self, patient_id, session_id, messages):
        if not messages:
            raise MemoryExtractionError("No messages were found for the extraction window.", retryable=False)

        if self.llm is None or not hasattr(self.llm, "invoke"):
            return self._fallback_extract(messages)

        prompt = self.build_prompt(patient_id, session_id, messages)
        try:
            response = self.llm.invoke(prompt)
        except Exception as exc:
            raise MemoryExtractionError(str(exc), retryable=True)

        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in content)
        result = self._extract_json_block(content)
        if not isinstance(result, dict):
            raise MemoryExtractionError("Extractor output was not valid JSON.", retryable=False)
        result.setdefault("events", [])
        result.setdefault("profiles", [])
        return result

    @staticmethod
    def compute_expiration(category, occurred_at=None):
        base_time = occurred_at or datetime.utcnow()
        if category == "symptom_progression":
            return base_time + timedelta(days=14)
        if category == "medication_adherence":
            return base_time + timedelta(days=30)
        if category == "followup_commitment":
            return base_time + timedelta(days=7)
        if category == "care_context":
            return base_time + timedelta(days=30)
        return base_time + timedelta(days=30)
