"""Schemas for text-to-speech APIs."""

from typing import Optional

from pydantic import BaseModel, Field


class TtsSynthesizeRequest(BaseModel):
    text: str = Field(..., description="需要播报的文本内容")
    voice: Optional[str] = Field(None, description="音色名称，默认使用服务端配置")
    file_name: Optional[str] = Field(None, description="可选文件名，不带路径")


class TtsSynthesizeResponse(BaseModel):
    file_name: str = Field(..., description="生成的音频文件名")
    file_path: str = Field(..., description="本地绝对路径")
    download_url: str = Field(..., description="下载接口地址")
    transcript: str = Field(..., description="实际播报文本")
    voice: str = Field(..., description="实际使用音色")
    model: str = Field(..., description="实际使用模型")
    audio_format: str = Field(..., description="音频格式")
    sample_rate: int = Field(..., description="采样率")
    file_size: int = Field(..., description="文件大小，单位字节")
