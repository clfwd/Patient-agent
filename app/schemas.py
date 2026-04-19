"""Pydantic schemas for core API resources."""

import base64
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PatientBase(BaseModel):
    patient_no: str = Field(..., description="患者编号")
    name: str = Field(..., description="患者姓名")
    gender: Optional[str] = Field(None, description="性别")
    birth_date: Optional[date] = Field(None, description="出生日期")
    phone: Optional[str] = Field(None, description="手机号")
    id_card: Optional[str] = Field(None, description="身份证号")
    emergency_contact_name: Optional[str] = Field(None, description="紧急联系人姓名")
    emergency_contact_phone: Optional[str] = Field(None, description="紧急联系人电话")
    address: Optional[str] = Field(None, description="联系地址")


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    patient_no: Optional[str] = Field(None, description="患者编号")
    name: Optional[str] = Field(None, description="患者姓名")
    gender: Optional[str] = Field(None, description="性别")
    birth_date: Optional[date] = Field(None, description="出生日期")
    phone: Optional[str] = Field(None, description="手机号")
    id_card: Optional[str] = Field(None, description="身份证号")
    emergency_contact_name: Optional[str] = Field(None, description="紧急联系人姓名")
    emergency_contact_phone: Optional[str] = Field(None, description="紧急联系人电话")
    address: Optional[str] = Field(None, description="联系地址")


class PatientRead(PatientBase):
    id: str = Field(..., description="主键 ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config(object):
        orm_mode = True


class MedicalRecordBase(BaseModel):
    record_type: str = Field("outpatient", description="病历类型")
    diagnosis: Optional[str] = Field(None, description="诊断结果")
    chief_complaint: Optional[str] = Field(None, description="主诉")
    present_illness: Optional[str] = Field(None, description="现病史")
    past_history: Optional[str] = Field(None, description="既往史")
    allergy_history: Optional[str] = Field(None, description="过敏史")
    medications: Optional[str] = Field(None, description="用药信息")
    doctor_name: Optional[str] = Field(None, description="医生姓名")
    department: Optional[str] = Field(None, description="科室")
    notes: Optional[str] = Field(None, description="补充说明")
    record_date: Optional[date] = Field(None, description="病历日期")


class MedicalRecordCreate(MedicalRecordBase):
    pass


class MedicalRecordUpdate(BaseModel):
    record_type: Optional[str] = Field(None, description="病历类型")
    diagnosis: Optional[str] = Field(None, description="诊断结果")
    chief_complaint: Optional[str] = Field(None, description="主诉")
    present_illness: Optional[str] = Field(None, description="现病史")
    past_history: Optional[str] = Field(None, description="既往史")
    allergy_history: Optional[str] = Field(None, description="过敏史")
    medications: Optional[str] = Field(None, description="用药信息")
    doctor_name: Optional[str] = Field(None, description="医生姓名")
    department: Optional[str] = Field(None, description="科室")
    notes: Optional[str] = Field(None, description="补充说明")
    record_date: Optional[date] = Field(None, description="病历日期")


class MedicalRecordRead(MedicalRecordBase):
    id: str = Field(..., description="病历 ID")
    patient_id: str = Field(..., description="患者 ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config(object):
        orm_mode = True


class VisitBase(BaseModel):
    visit_no: Optional[str] = Field(None, description="就诊流水号")
    visit_type: str = Field("outpatient", description="就诊类型")
    department: Optional[str] = Field(None, description="就诊科室")
    doctor_name: Optional[str] = Field(None, description="接诊医生")
    visit_time: datetime = Field(..., description="就诊时间")
    status: Optional[str] = Field(None, description="就诊状态")
    complaint: Optional[str] = Field(None, description="本次主诉")
    diagnosis_summary: Optional[str] = Field(None, description="诊断摘要")
    treatment_plan: Optional[str] = Field(None, description="治疗方案")


class VisitCreate(VisitBase):
    pass


class VisitUpdate(BaseModel):
    visit_no: Optional[str] = Field(None, description="就诊流水号")
    visit_type: Optional[str] = Field(None, description="就诊类型")
    department: Optional[str] = Field(None, description="就诊科室")
    doctor_name: Optional[str] = Field(None, description="接诊医生")
    visit_time: Optional[datetime] = Field(None, description="就诊时间")
    status: Optional[str] = Field(None, description="就诊状态")
    complaint: Optional[str] = Field(None, description="本次主诉")
    diagnosis_summary: Optional[str] = Field(None, description="诊断摘要")
    treatment_plan: Optional[str] = Field(None, description="治疗方案")


class VisitRead(VisitBase):
    id: str = Field(..., description="就诊记录 ID")
    patient_id: str = Field(..., description="患者 ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config(object):
        orm_mode = True


class UploadedImageRead(BaseModel):
    id: str = Field(..., description="图片 ID")
    patient_id: Optional[str] = Field(None, description="患者 ID")
    record_id: Optional[str] = Field(None, description="病历 ID")
    visit_id: Optional[str] = Field(None, description="就诊 ID")
    image_type: str = Field(..., description="图片类型")
    original_file_name: str = Field(..., description="原始文件名")
    stored_file_name: str = Field(..., description="存储文件名")
    file_path: str = Field(..., description="本地绝对路径")
    mime_type: str = Field(..., description="MIME 类型")
    file_size: int = Field(..., description="文件大小")
    source: str = Field(..., description="来源")
    notes: Optional[str] = Field(None, description="备注")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config(object):
        orm_mode = True


class UploadedImageUploadRequest(BaseModel):
    file_name: str = Field(..., description="原始文件名")
    content_base64: str = Field(..., description="图片的 Base64 内容，不含 data URL 头")
    mime_type: str = Field(..., description="图片 MIME 类型，例如 image/png")
    patient_id: Optional[str] = Field(None, description="患者 ID")
    record_id: Optional[str] = Field(None, description="病历 ID")
    visit_id: Optional[str] = Field(None, description="就诊 ID")
    image_type: str = Field("general", description="图片类型")
    source: str = Field("upload", description="来源")
    notes: Optional[str] = Field(None, description="备注")

    def decode_content(self) -> bytes:
        return base64.b64decode(self.content_base64)


class ChatAttachmentReference(BaseModel):
    id: str = Field(..., description="附件 ID")
    kind: str = Field("image", description="附件类型")
    image_id: Optional[str] = Field(None, description="关联图片 ID")


class ChatAttachmentRead(BaseModel):
    id: str = Field(..., description="附件 ID")
    kind: str = Field(..., description="附件类型")
    status: str = Field(..., description="附件状态")
    session_id: Optional[str] = Field(None, description="会话 ID")
    patient_id: Optional[str] = Field(None, description="患者 ID")
    record_id: Optional[str] = Field(None, description="病历 ID")
    visit_id: Optional[str] = Field(None, description="就诊 ID")
    image_id: str = Field(..., description="关联图片 ID")
    file_name: str = Field(..., description="文件名")
    mime_type: str = Field(..., description="MIME 类型")
    file_size: int = Field(..., description="文件大小")
    width: Optional[int] = Field(None, description="图片宽度")
    height: Optional[int] = Field(None, description="图片高度")
    preview_url: str = Field(..., description="缩略图预览地址")
    download_url: str = Field(..., description="原文件下载地址")
    source: str = Field(..., description="附件来源")
    created_at: datetime = Field(..., description="创建时间")

    class Config(object):
        orm_mode = True


class ChatAttachmentDeleteResponse(BaseModel):
    deleted: bool = Field(..., description="是否删除成功")
    attachment_id: str = Field(..., description="附件 ID")


class ApiErrorDetail(BaseModel):
    code: str = Field(..., description="稳定错误码")
    message: str = Field(..., description="错误说明")
    retryable: bool = Field(False, description="是否可重试")
    verification_required: bool = Field(False, description="是否需要重新进行身份核验")
    extra: Dict[str, Any] = Field(default_factory=dict, description="额外错误上下文")
