"""Schemas for agent invocation and chat session persistence."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.mcp.schemas import AudioAttachmentSchema
from app.schemas import ChatAttachmentRead, ChatAttachmentReference


class AgentInvokeRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Chat session id")
    patient_id: Optional[str] = Field(None, description="Patient primary id")
    patient_no: Optional[str] = Field(None, description="Patient number")
    visit_no: Optional[str] = Field(None, description="Visit number")
    verify_name: Optional[str] = Field(None, description="Verification name")
    verify_phone: Optional[str] = Field(None, description="Verification phone")
    verify_id_card: Optional[str] = Field(None, description="Verification id card")
    image_id: Optional[str] = Field(None, description="Legacy single image id")
    attachments: List[ChatAttachmentReference] = Field(default_factory=list, description="Bound chat attachments")
    with_audio: bool = Field(True, description="Whether to synthesize audio automatically")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extra metadata")


class AgentStepSchema(BaseModel):
    name: str = Field(..., description="Step name")
    status: str = Field(..., description="Step status")
    detail: Optional[str] = Field(None, description="Step detail")
    tool_name: Optional[str] = Field(None, description="Associated tool name")


class AgentToolCallSchema(BaseModel):
    tool_name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    ok: bool = Field(..., description="Whether the tool call succeeded")
    result: Optional[Dict[str, Any]] = Field(None, description="Tool result")
    error: Optional[str] = Field(None, description="Tool error")


class AgentTraceSchema(BaseModel):
    stage: Optional[str] = Field(None, description="Execution stage")
    event: str = Field(..., description="Trace event")
    status: str = Field(..., description="Trace status")
    detail: str = Field(..., description="Trace detail")
    tool_name: Optional[str] = Field(None, description="Associated tool name")
    arguments: Optional[Dict[str, Any]] = Field(None, description="Associated tool arguments")
    error: Optional[str] = Field(None, description="Error detail")
    created_at: Optional[datetime] = Field(None, description="Event timestamp")


class AgentInvokeResponse(BaseModel):
    session_id: str = Field(..., description="Current chat session id")
    run_id: Optional[str] = Field(None, description="Current execution id")
    intent: Optional[str] = Field(None, description="High level inferred intent")
    plan: List[str] = Field(default_factory=list, description="Execution plan")
    steps: List[AgentStepSchema] = Field(default_factory=list, description="Structured steps")
    tool_calls: List[AgentToolCallSchema] = Field(default_factory=list, description="Tool call records")
    agent_trace: List[AgentTraceSchema] = Field(default_factory=list, description="Agent trace events")
    identity_verification: Optional[Dict[str, Any]] = Field(None, description="Identity verification result")
    final_answer: str = Field(..., description="Final answer")
    audio: Optional[AudioAttachmentSchema] = Field(None, description="Optional generated audio")
    attachments: List[ChatAttachmentRead] = Field(default_factory=list, description="Attachments bound to this request")
    used_models: Dict[str, Optional[str]] = Field(default_factory=dict, description="Model usage details")


class ChatSessionCreateRequest(BaseModel):
    patient_id: Optional[str] = Field(None, description="Bound patient id")
    title: Optional[str] = Field(None, description="Session title")
    status: str = Field("active", description="Session status")


class ChatSessionUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, description="Session title")
    status: Optional[str] = Field(None, description="Session status")


class ChatSessionRead(BaseModel):
    id: str = Field(..., description="Session id")
    patient_id: Optional[str] = Field(None, description="Bound patient id")
    title: Optional[str] = Field(None, description="Session title")
    status: str = Field(..., description="Session status")
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")

    class Config(object):
        orm_mode = True


class ChatSessionListItemRead(BaseModel):
    id: str = Field(..., description="Session id")
    patient_id: Optional[str] = Field(None, description="Bound patient id")
    title: Optional[str] = Field(None, description="Session title")
    status: str = Field(..., description="Session status")
    last_message_preview: Optional[str] = Field(None, description="Last message preview")
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")


class ChatMessageRead(BaseModel):
    id: str = Field(..., description="Message id")
    session_id: str = Field(..., description="Session id")
    sequence_no: int = Field(..., description="Message order number")
    role: str = Field(..., description="Message role")
    message_type: str = Field(..., description="Message type")
    content: Optional[str] = Field(None, description="Visible content")
    tool_name: Optional[str] = Field(None, description="Associated tool name")
    tool_call_id: Optional[str] = Field(None, description="Associated tool call id")
    payload: Optional[Dict[str, Any]] = Field(None, description="Raw structured payload")
    visible_in_context: bool = Field(..., description="Whether visible in restored context")
    created_at: datetime = Field(..., description="Created at")


class ChatSessionContextRead(BaseModel):
    session: ChatSessionRead
    patient: Optional[Dict[str, Any]] = Field(None, description="Patient summary")
    latest_agent_run: Optional[Dict[str, Any]] = Field(None, description="Latest agent run summary")
    attachments: List[ChatAttachmentRead] = Field(default_factory=list, description="Session attachments")
