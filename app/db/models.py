"""Database models for patients, records, visits, images, and chat sessions."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from .database import Base


def _uuid():
    return str(uuid.uuid4())


class FlexibleDateTime(TypeDecorator):
    """Handle multiple SQLite datetime string formats."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S.%f")
        raise TypeError("datetime fields only support datetime values")

    def process_result_value(self, value, dialect):
        if value is None or isinstance(value, datetime):
            return value

        formats = [
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
        ]
        for time_format in formats:
            try:
                return datetime.strptime(value, time_format)
            except ValueError:
                continue
        raise ValueError("unable to parse datetime value: {0}".format(value))


class TimestampMixin(object):
    created_at = Column(FlexibleDateTime(), default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(
        FlexibleDateTime(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )


class Patient(TimestampMixin, Base):
    __tablename__ = "patients"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_no = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    gender = Column(String(16))
    birth_date = Column(Date)
    phone = Column(String(32))
    id_card = Column(String(64), unique=True, index=True)
    emergency_contact_name = Column(String(128))
    emergency_contact_phone = Column(String(32))
    address = Column(String(255))

    medical_records = relationship("MedicalRecord", back_populates="patient", cascade="all, delete-orphan")
    visits = relationship("Visit", back_populates="patient", cascade="all, delete-orphan")
    uploaded_images = relationship("UploadedImage", back_populates="patient", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="patient")


class MedicalRecord(TimestampMixin, Base):
    __tablename__ = "medical_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), index=True, nullable=False)
    record_type = Column(String(64), nullable=False, default="outpatient")
    diagnosis = Column(String(255))
    chief_complaint = Column(Text)
    present_illness = Column(Text)
    past_history = Column(Text)
    allergy_history = Column(Text)
    medications = Column(Text)
    doctor_name = Column(String(128))
    department = Column(String(128))
    notes = Column(Text)
    record_date = Column(Date)

    patient = relationship("Patient", back_populates="medical_records")
    uploaded_images = relationship("UploadedImage", back_populates="medical_record")


class Visit(TimestampMixin, Base):
    __tablename__ = "visits"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), index=True, nullable=False)
    visit_no = Column(String(64), unique=True, index=True)
    visit_type = Column(String(64), nullable=False, default="outpatient")
    department = Column(String(128))
    doctor_name = Column(String(128))
    visit_time = Column(FlexibleDateTime(), nullable=False)
    status = Column(String(32))
    complaint = Column(Text)
    diagnosis_summary = Column(Text)
    treatment_plan = Column(Text)

    patient = relationship("Patient", back_populates="visits")
    uploaded_images = relationship("UploadedImage", back_populates="visit")


class UploadedImage(TimestampMixin, Base):
    __tablename__ = "uploaded_images"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), index=True)
    record_id = Column(String(36), ForeignKey("medical_records.id"), index=True)
    visit_id = Column(String(36), ForeignKey("visits.id"), index=True)
    image_type = Column(String(64), default="general", nullable=False)
    original_file_name = Column(String(255), nullable=False)
    stored_file_name = Column(String(255), unique=True, nullable=False)
    file_path = Column(String(512), nullable=False)
    mime_type = Column(String(128), nullable=False)
    file_size = Column(Integer, nullable=False)
    source = Column(String(64), default="upload", nullable=False)
    notes = Column(Text)

    patient = relationship("Patient", back_populates="uploaded_images")
    medical_record = relationship("MedicalRecord", back_populates="uploaded_images")
    visit = relationship("Visit", back_populates="uploaded_images")
    chat_attachment = relationship("ChatAttachment", back_populates="image", uselist=False, cascade="all, delete-orphan")


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), index=True)
    title = Column(String(255))
    status = Column(String(32), nullable=False, default="active")

    patient = relationship("Patient", back_populates="chat_sessions")
    messages = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.sequence_no",
    )
    attachments = relationship("ChatAttachment", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), index=True, nullable=False)
    sequence_no = Column(Integer, nullable=False)
    role = Column(String(32), nullable=False)
    message_type = Column(String(64), nullable=False)
    content = Column(Text)
    tool_name = Column(String(128))
    tool_call_id = Column(String(128))
    payload_json = Column(Text)
    visible_in_context = Column(Boolean, nullable=False, default=False)
    created_at = Column(FlexibleDateTime(), default=datetime.utcnow, server_default=func.now(), nullable=False)

    session = relationship("ChatSession", back_populates="messages")


class ChatAttachment(TimestampMixin, Base):
    __tablename__ = "chat_attachments"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), index=True)
    record_id = Column(String(36), ForeignKey("medical_records.id"), index=True)
    visit_id = Column(String(36), ForeignKey("visits.id"), index=True)
    image_id = Column(String(36), ForeignKey("uploaded_images.id"), index=True, unique=True, nullable=False)
    kind = Column(String(32), nullable=False, default="image")
    status = Column(String(32), nullable=False, default="ready")
    file_name = Column(String(255), nullable=False)
    mime_type = Column(String(128), nullable=False)
    file_size = Column(Integer, nullable=False)
    width = Column(Integer)
    height = Column(Integer)
    source = Column(String(64), nullable=False, default="chat_input")

    session = relationship("ChatSession", back_populates="attachments")
    patient = relationship("Patient")
    medical_record = relationship("MedicalRecord")
    visit = relationship("Visit")
    image = relationship("UploadedImage", back_populates="chat_attachment")
