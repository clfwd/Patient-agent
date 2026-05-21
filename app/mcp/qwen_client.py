"""Qwen client and multimodal routing helpers."""

import json
import os

import httpx


class QwenToolSelectionError(Exception):
    """Raised when the Qwen client cannot produce a valid tool selection."""


class QwenClient(object):
    """Minimal OpenAI-compatible Qwen HTTP client."""

    def __init__(self, api_key=None, base_url=None, model=None, timeout=30.0):
        self.api_key = (
            api_key
            or os.getenv("QWEN_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        self.base_url = (
            base_url
            or os.getenv("QWEN_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        self.model = model or os.getenv("QWEN_MODEL") or os.getenv("OPENAI_MODEL") or "qwen3-max"
        self.vision_model = os.getenv("QWEN_VISION_MODEL") or "qwen-vl-max-latest"
        self.timeout = timeout

    def is_configured(self):
        return bool(self.api_key)

    def _post_chat(self, messages, model=None):
        if not self.is_configured():
            raise QwenToolSelectionError("Qwen API key is not configured.")

        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": 0.1,
        }
        headers = {
            "Authorization": "Bearer {0}".format(self.api_key),
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout, trust_env=False) as client:
            try:
                response = client.post(
                    "{0}/chat/completions".format(self.base_url),
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise QwenToolSelectionError("Qwen request failed: {0}".format(exc))

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise QwenToolSelectionError("Qwen response format is invalid: {0}".format(data))

    @staticmethod
    def _extract_json(content):
        try:
            return json.loads(content)
        except ValueError:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(content[start : end + 1])
            raise QwenToolSelectionError("Failed to parse Qwen JSON response: {0}".format(content))

    def select_tool(self, message, tools, context):
        tool_lines = []
        for tool in tools:
            tool_lines.append(
                "- {0} | server={1} | desc={2} | input={3}".format(
                    tool["name"],
                    tool["server_name"],
                    tool["description"],
                    json.dumps(tool["input_schema"], ensure_ascii=False),
                )
            )

        prompt = (
            "你是一个医疗内部工具路由器，只能从给定工具中选择一个最合适的工具。\n"
            "请严格返回 JSON，不要输出其他内容。\n"
            '返回格式: {{"server_name":"...", "tool_name":"...", "arguments": {{}}, "reasoning":"..."}}\n'
            "如果上下文已有 patient_id、patient_no、visit_no 等信息，请尽量补全到 arguments。\n"
            "可用工具如下:\n{0}\n"
            "上下文:\n{1}\n"
            "用户请求:\n{2}"
        ).format("\n".join(tool_lines), json.dumps(context, ensure_ascii=False), message)

        content = self._post_chat(
            [
                {"role": "system", "content": "你负责为医疗系统选择内部工具。"},
                {"role": "user", "content": prompt},
            ]
        )
        return self._extract_json(content)

    def summarize(self, user_message, tool_name, tool_result):
        if not self.is_configured():
            return self._fallback_summary(user_message, tool_name, tool_result)

        prompt = (
            "你是患者智能辅助 Agent 的内部工具解释器。\n"
            "请基于用户请求和工具结果，给出简洁、结构化、面向研发调试的中文说明。\n"
            "不要编造工具结果中没有的信息。\n"
            "用户请求: {0}\n"
            "工具名: {1}\n"
            "工具结果: {2}"
        ).format(user_message, tool_name, json.dumps(tool_result, ensure_ascii=False))

        return self._post_chat(
            [
                {"role": "system", "content": "你负责解释工具调用结果。"},
                {"role": "user", "content": prompt},
            ]
        )

    def analyze_case_image(self, image_url, case_context, patient_context=None, clinical_question=None):
        if not self.is_configured():
            raise QwenToolSelectionError("Qwen API key is not configured.")

        prompt = (
            "你是医疗图像相关性分析助手。请结合给定病历上下文和一张网络图片，判断图片内容是否可能与该患者当前病情有关。\n"
            "注意：这里只做相关性判断，不做最终诊断，也不要编造图片中看不到的内容。\n"
            "请严格返回 JSON，字段如下：\n"
            "{{"
            '"is_related": true/false, '
            '"relevance_level": "high|medium|low|uncertain", '
            '"visible_findings": ["..."], '
            '"reasoning": "...", '
            '"limitations": ["..."], '
            '"suggested_follow_up": ["..."]'
            "}}\n"
            "患者信息摘要: {0}\n"
            "病历摘要: {1}\n"
            "补充问题: {2}"
        ).format(
            json.dumps(patient_context or {}, ensure_ascii=False),
            json.dumps(case_context or {}, ensure_ascii=False),
            clinical_question or "请判断图片与该病情是否可能相关。",
        )

        content = self._post_chat(
            [
                {"role": "system", "content": "你负责医疗图像与病历之间的相关性判断。"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            model=self.vision_model,
        )

        return self._extract_json(content)

    @staticmethod
    def _fallback_summary(user_message, tool_name, tool_result):
        return "已通过 {0} 执行请求“{1}”，返回结果: {2}".format(
            tool_name,
            user_message,
            json.dumps(tool_result, ensure_ascii=False),
        )
