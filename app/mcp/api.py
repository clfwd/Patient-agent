"""FastAPI route registration for MCP-style modular tool servers."""

from typing import List

from fastapi import Depends, Query, Request

from app.error_handling import raise_http_for_mcp_result
from app.tts.service import TtsSynthesisError

from .schemas import (
    CaseImageAnalyzeRequest,
    CaseImageAnalyzeResponse,
    CaseImageSearchRequest,
    CaseImageSearchResponse,
    McpAgentRequest,
    McpAgentResponse,
    McpServerSchema,
    McpToolInvokeRequest,
    McpToolInvokeResponse,
    McpToolSchema,
)


def _merge_verification_fields(arguments, verify_name=None, verify_phone=None, verify_id_card=None):
    merged = dict(arguments or {})
    if verify_name:
        merged["name"] = verify_name
    if verify_phone:
        merged["phone"] = verify_phone
    if verify_id_card:
        merged["id_card"] = verify_id_card
    return merged


def _raise_for_mcp_error(result):
    raise_http_for_mcp_result(result)


def register_mcp_routes(app):
    """Register MCP-style routes on an existing FastAPI app."""

    def get_registry(request: Request):
        return request.app.state.mcp_registry

    @app.get("/api/v1/mcp/servers", response_model=List[McpServerSchema], tags=["MCP"], summary="列出 MCP Server")
    def list_mcp_servers(registry=Depends(get_registry)):
        return registry.list_servers()

    @app.get("/api/v1/mcp/tools", response_model=List[McpToolSchema], tags=["MCP"], summary="列出 MCP 工具")
    def list_mcp_tools(
        server_name: str = Query(None, description="按 server 名称过滤"),
        registry=Depends(get_registry),
    ):
        return registry.list_tools(server_name=server_name)

    @app.post(
        "/api/v1/mcp/tools/{tool_name}/invoke",
        response_model=McpToolInvokeResponse,
        tags=["MCP"],
        summary="直接调用指定 MCP 工具",
    )
    def invoke_mcp_tool(tool_name: str, payload: McpToolInvokeRequest, registry=Depends(get_registry)):
        merged_arguments = _merge_verification_fields(
            payload.arguments,
            verify_name=payload.verify_name,
            verify_phone=payload.verify_phone,
            verify_id_card=payload.verify_id_card,
        )
        result = registry.invoke_tool(tool_name, merged_arguments)
        if not result["ok"]:
            _raise_for_mcp_error(result)
        return result

    @app.post(
        "/api/v1/mcp/agent/invoke",
        response_model=McpAgentResponse,
        tags=["MCP"],
        summary="通过 Qwen 或启发式路由调用 MCP 工具，可选同步生成语音",
    )
    def invoke_mcp_agent(payload: McpAgentRequest, registry=Depends(get_registry)):
        try:
            result = registry.route_and_invoke(payload)
        except TtsSynthesisError as exc:
            raise_http_for_mcp_result({"error": "tool_execution_failed", "detail": str(exc)})

        tool_error = result.get("tool_result", {}).get("error")
        if tool_error:
            _raise_for_mcp_error(
                {
                    "ok": False,
                    "error": tool_error,
                    "detail": result.get("tool_result", {}).get("detail"),
                    "verification": result.get("identity_verification"),
                }
            )
        return result

    @app.post(
        "/api/v1/mcp/case-image/search-query",
        response_model=CaseImageSearchResponse,
        tags=["MCP"],
        summary="根据已有病历生成病例图片搜图关键词",
    )
    def case_image_search_query(payload: CaseImageSearchRequest, registry=Depends(get_registry)):
        result = registry.invoke_tool(
            "case_image.build_search_query",
            _merge_verification_fields(
                {
                    "record_id": payload.record_id,
                    "patient_id": payload.patient_id,
                    "patient_no": payload.patient_no,
                },
                verify_name=payload.verify_name,
                verify_phone=payload.verify_phone,
                verify_id_card=payload.verify_id_card,
            ),
        )
        if not result["ok"]:
            _raise_for_mcp_error(result)
        data = dict(result["data"])
        data["identity_verification"] = result.get("verification")
        return data

    @app.post(
        "/api/v1/mcp/case-image/analyze",
        response_model=CaseImageAnalyzeResponse,
        tags=["MCP"],
        summary="基于已有病历和网络图片做相关性分析",
    )
    def case_image_analyze(payload: CaseImageAnalyzeRequest, registry=Depends(get_registry)):
        result = registry.invoke_tool(
            "case_image.analyze_image_relevance",
            _merge_verification_fields(
                {
                    "record_id": payload.record_id,
                    "patient_id": payload.patient_id,
                    "patient_no": payload.patient_no,
                    "image_url": str(payload.image_url),
                    "clinical_question": payload.clinical_question,
                },
                verify_name=payload.verify_name,
                verify_phone=payload.verify_phone,
                verify_id_card=payload.verify_id_card,
            ),
        )
        if not result["ok"]:
            _raise_for_mcp_error(result)
        data = dict(result["data"])
        data["identity_verification"] = result.get("verification")
        return data
