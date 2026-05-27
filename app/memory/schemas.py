"""Schemas for long-term memory APIs."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EventMemoryRead(BaseModel):
    id: str = Field(..., description="事件记忆 ID")
    patient_id: str = Field(..., description="患者 ID")
    category: str = Field(..., description="事件分类")
    summary: str = Field(..., description="事件摘要")
    payload: Optional[Dict[str, Any]] = Field(None, description="结构化事件详情")
    confidence_score: float = Field(..., description="置信度")
    search_text: Optional[str] = Field(None, description="关键词检索文本")
    has_embedding: bool = Field(..., description="是否已生成事件向量")
    embedding_model: Optional[str] = Field(None, description="事件向量使用的模型")
    embedding_dimensions: Optional[int] = Field(None, description="事件向量维度")
    embedding_generated_at: Optional[datetime] = Field(None, description="事件向量生成时间")
    source_session_id: Optional[str] = Field(None, description="来源会话 ID")
    source_message_ids: Optional[List[str]] = Field(None, description="来源消息 ID 列表")
    occurred_at: Optional[datetime] = Field(None, description="事件发生时间")
    last_seen_at: datetime = Field(..., description="最近观测时间")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class ProfileMemoryRead(BaseModel):
    id: str = Field(..., description="画像记忆 ID")
    patient_id: str = Field(..., description="患者 ID")
    key: str = Field(..., description="画像键")
    value: str = Field(..., description="画像值")
    summary: str = Field(..., description="画像摘要")
    confidence_score: float = Field(..., description="置信度")
    source_session_id: Optional[str] = Field(None, description="来源会话 ID")
    last_seen_at: datetime = Field(..., description="最近观测时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class MemoryExtractionJobRead(BaseModel):
    id: str = Field(..., description="任务 ID")
    patient_id: str = Field(..., description="患者 ID")
    session_id: str = Field(..., description="会话 ID")
    from_sequence_no: int = Field(..., description="窗口起始消息序号")
    to_sequence_no: int = Field(..., description="窗口结束消息序号")
    status: str = Field(..., description="任务状态")
    retry_count: int = Field(..., description="当前重试次数")
    max_retries: int = Field(..., description="最大重试次数")
    next_retry_at: Optional[datetime] = Field(None, description="下次可重试时间")
    error_message: Optional[str] = Field(None, description="失败原因")
    created_at: datetime = Field(..., description="创建时间")
    started_at: Optional[datetime] = Field(None, description="开始执行时间")
    finished_at: Optional[datetime] = Field(None, description="结束时间")


class MemoryRecallRequest(BaseModel):
    query: str = Field(..., description="用于召回长期记忆的当前问题")


class EventMemoryRecallHitRead(BaseModel):
    memory: EventMemoryRead
    score: float = Field(..., description="当前检索源的分数")
    rank: int = Field(..., description="当前检索源中的名次")
    source: str = Field(..., description="命中来源：dense / keyword / rrf")


class MemoryRecallRead(BaseModel):
    profiles: List[ProfileMemoryRead]
    dense_hits: List[EventMemoryRecallHitRead]
    keyword_hits: List[EventMemoryRecallHitRead]
    fused_hits: List[EventMemoryRecallHitRead]
