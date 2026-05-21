"""MCP schemas for tool listing, invocation, image analysis, and speech output."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class AudioAttachmentSchema(BaseModel):
    file_name: str = Field(..., description="生成的音频文件名")
    file_path: str = Field(..., description="本地绝对路径")
    download_url: str = Field(..., description="下载地址")
    transcript: str = Field(..., description="实际播报文本")
    voice: str = Field(..., description="使用的音色")
    model: str = Field(..., description="使用的模型")
    audio_format: str = Field(..., description="音频格式，固定为 mp3")
    sample_rate: int = Field(..., description="采样率，固定为 24000")
    file_size: int = Field(..., description="文件大小，单位字节")


class McpToolSchema(BaseModel):
    name: str = Field(..., description="工具名称")
    server_name: str = Field(..., description="所属 server 名称")
    description: str = Field(..., description="工具描述")
    input_schema: Dict[str, Any] = Field(..., description="工具入参 schema")


class McpServerSchema(BaseModel):
    name: str = Field(..., description="Server 名称")
    description: str = Field(..., description="Server 描述")
    tools: List[McpToolSchema] = Field(default_factory=list, description="工具列表")


class McpToolInvokeRequest(BaseModel):
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具入参")
    verify_name: Optional[str] = Field(None, description="身份核验姓名")
    verify_phone: Optional[str] = Field(None, description="身份核验手机号")
    verify_id_card: Optional[str] = Field(None, description="身份核验身份证号")


class McpToolInvokeResponse(BaseModel):
    ok: bool = Field(..., description="是否执行成功")
    server_name: str = Field(..., description="所属 server 名称")
    tool_name: str = Field(..., description="工具名称")
    data: Optional[Dict[str, Any]] = Field(None, description="工具返回数据")
    error: Optional[str] = Field(None, description="错误信息")
    verification: Optional[Dict[str, Any]] = Field(None, description="身份核验结果")


class McpAgentRequest(BaseModel):
    message: str = Field(..., description="自然语言请求")
    patient_id: Optional[str] = Field(None, description="患者主键 ID")
    patient_no: Optional[str] = Field(None, description="患者业务编号")
    visit_no: Optional[str] = Field(None, description="就诊流水号")
    verify_name: Optional[str] = Field(None, description="身份核验姓名")
    verify_phone: Optional[str] = Field(None, description="身份核验手机号")
    verify_id_card: Optional[str] = Field(None, description="身份核验身份证号")
    prefer_server: Optional[str] = Field(None, description="优先使用的 server")
    prefer_tool: Optional[str] = Field(None, description="优先使用的工具")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外上下文")
    allow_fallback: bool = Field(True, description="Qwen 不可用时是否允许启发式回退")
    with_audio: bool = Field(False, description="是否将最终答复同步生成本地 mp3 音频")


class McpAgentResponse(BaseModel):
    route_source: str = Field(..., description="路由来源：qwen 或 heuristic")
    server_name: str = Field(..., description="选中的 server")
    tool_name: str = Field(..., description="选中的工具")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="最终工具参数")
    tool_result: Dict[str, Any] = Field(default_factory=dict, description="工具执行结果")
    identity_verification: Optional[Dict[str, Any]] = Field(None, description="身份核验结果")
    final_answer: str = Field(..., description="返回给调用方的总结")
    audio: Optional[AudioAttachmentSchema] = Field(None, description="最终答复对应的音频文件")
    used_model: Optional[str] = Field(None, description="实际使用的大模型")


class CaseImageSearchRequest(BaseModel):
    record_id: Optional[str] = Field(None, description="病历记录 ID")
    patient_id: Optional[str] = Field(None, description="患者主键 ID")
    patient_no: Optional[str] = Field(None, description="患者业务编号")
    verify_name: Optional[str] = Field(None, description="身份核验姓名")
    verify_phone: Optional[str] = Field(None, description="身份核验手机号")
    verify_id_card: Optional[str] = Field(None, description="身份核验身份证号")


class CaseImageSearchResponse(BaseModel):
    found: bool = Field(..., description="是否找到对应病历")
    record_summary: Optional[Dict[str, Any]] = Field(None, description="病历摘要")
    suggested_queries: List[str] = Field(default_factory=list, description="建议的搜图关键词")
    notes: Optional[str] = Field(None, description="补充说明")
    identity_verification: Optional[Dict[str, Any]] = Field(None, description="身份核验结果")


class CaseImageAnalyzeRequest(BaseModel):
    image_url: HttpUrl = Field(..., description="网络图片 URL")
    record_id: Optional[str] = Field(None, description="病历记录 ID")
    patient_id: Optional[str] = Field(None, description="患者主键 ID")
    patient_no: Optional[str] = Field(None, description="患者业务编号")
    clinical_question: Optional[str] = Field(None, description="补充问题")
    verify_name: Optional[str] = Field(None, description="身份核验姓名")
    verify_phone: Optional[str] = Field(None, description="身份核验手机号")
    verify_id_card: Optional[str] = Field(None, description="身份核验身份证号")


class CaseImageAnalyzeResponse(BaseModel):
    found: bool = Field(..., description="是否找到对应病历")
    record_summary: Optional[Dict[str, Any]] = Field(None, description="病历摘要")
    patient_summary: Optional[Dict[str, Any]] = Field(None, description="患者摘要")
    image_url: str = Field(..., description="分析图片 URL")
    analysis: Dict[str, Any] = Field(default_factory=dict, description="大模型分析结果")
    identity_verification: Optional[Dict[str, Any]] = Field(None, description="身份核验结果")
    used_model: Optional[str] = Field(None, description="使用的视觉模型")
