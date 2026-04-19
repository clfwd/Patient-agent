"""Repositories for patients, visits, images, and chat persistence."""

import json
from datetime import datetime

from sqlalchemy import asc, desc, func, select

from .models import ChatAttachment, ChatSession, MedicalRecord, Message, Patient, UploadedImage, Visit


class PatientRepository(object):
    def __init__(self, session):
        self.session = session

    def create_patient(self, **patient_data):
        patient = Patient(**patient_data)
        self.session.add(patient)
        self.session.commit()
        self.session.refresh(patient)
        return patient

    def get_by_id(self, patient_id):
        return self.session.get(Patient, patient_id)

    def get_by_patient_no(self, patient_no):
        stmt = select(Patient).where(Patient.patient_no == patient_no)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_id_card(self, id_card):
        stmt = select(Patient).where(Patient.id_card == id_card)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_name_and_phone(self, name, phone):
        stmt = select(Patient).where(Patient.name == name, Patient.phone == phone)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_name_and_id_card(self, name, id_card):
        stmt = select(Patient).where(Patient.name == name, Patient.id_card == id_card)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_patients(self, limit=50):
        stmt = select(Patient).order_by(desc(Patient.created_at)).limit(limit)
        return self.session.execute(stmt).scalars().all()

    def update_patient(self, patient_id, **updates):
        patient = self.get_by_id(patient_id)
        if patient is None:
            return None

        for field, value in updates.items():
            if hasattr(patient, field):
                setattr(patient, field, value)

        self.session.commit()
        self.session.refresh(patient)
        return patient


class MedicalRecordRepository(object):
    def __init__(self, session):
        self.session = session

    def create_record(self, **record_data):
        record = MedicalRecord(**record_data)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_by_id(self, record_id):
        return self.session.get(MedicalRecord, record_id)

    def list_by_patient(self, patient_id, limit=50):
        stmt = (
            select(MedicalRecord)
            .where(MedicalRecord.patient_id == patient_id)
            .order_by(desc(MedicalRecord.record_date), desc(MedicalRecord.created_at))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()

    def get_latest_by_patient(self, patient_id):
        stmt = (
            select(MedicalRecord)
            .where(MedicalRecord.patient_id == patient_id)
            .order_by(desc(MedicalRecord.record_date), desc(MedicalRecord.created_at))
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def search_records(
        self,
        patient_id=None,
        record_id=None,
        record_type=None,
        date_from=None,
        date_to=None,
        department=None,
        doctor_name=None,
        diagnosis_keyword=None,
        limit=20,
        sort_by="record_date",
        sort_order="desc",
    ):
        stmt = select(MedicalRecord)

        if patient_id:
            stmt = stmt.where(MedicalRecord.patient_id == patient_id)
        if record_id:
            stmt = stmt.where(MedicalRecord.id == record_id)
        if record_type:
            stmt = stmt.where(MedicalRecord.record_type == record_type)
        if date_from:
            stmt = stmt.where(MedicalRecord.record_date >= date_from)
        if date_to:
            stmt = stmt.where(MedicalRecord.record_date <= date_to)
        if department:
            stmt = stmt.where(MedicalRecord.department == department)
        if doctor_name:
            stmt = stmt.where(MedicalRecord.doctor_name == doctor_name)
        if diagnosis_keyword:
            stmt = stmt.where(MedicalRecord.diagnosis.contains(diagnosis_keyword))

        sort_field_map = {
            "record_date": MedicalRecord.record_date,
            "created_at": MedicalRecord.created_at,
            "updated_at": MedicalRecord.updated_at,
        }
        sort_field = sort_field_map.get(sort_by, MedicalRecord.record_date)
        order_by = asc if str(sort_order).lower() == "asc" else desc
        stmt = stmt.order_by(order_by(sort_field), desc(MedicalRecord.created_at)).limit(limit)
        return self.session.execute(stmt).scalars().all()

    def update_record(self, record_id, **updates):
        record = self.get_by_id(record_id)
        if record is None:
            return None

        for field, value in updates.items():
            if hasattr(record, field):
                setattr(record, field, value)

        self.session.commit()
        self.session.refresh(record)
        return record


class VisitRepository(object):
    def __init__(self, session):
        self.session = session

    def create_visit(self, **visit_data):
        visit = Visit(**visit_data)
        self.session.add(visit)
        self.session.commit()
        self.session.refresh(visit)
        return visit

    def get_by_id(self, visit_id):
        return self.session.get(Visit, visit_id)

    def get_by_visit_no(self, visit_no):
        stmt = select(Visit).where(Visit.visit_no == visit_no)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_by_patient(self, patient_id, limit=50):
        stmt = (
            select(Visit)
            .where(Visit.patient_id == patient_id)
            .order_by(desc(Visit.visit_time), desc(Visit.created_at))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()

    def get_latest_by_patient(self, patient_id):
        stmt = (
            select(Visit)
            .where(Visit.patient_id == patient_id)
            .order_by(desc(Visit.visit_time), desc(Visit.created_at))
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def search_visits(
        self,
        patient_id=None,
        visit_no=None,
        date_from=None,
        date_to=None,
        department=None,
        visit_type=None,
        doctor_name=None,
        status=None,
        limit=20,
        sort_by="visit_time",
        sort_order="desc",
    ):
        stmt = select(Visit)

        if patient_id:
            stmt = stmt.where(Visit.patient_id == patient_id)
        if visit_no:
            stmt = stmt.where(Visit.visit_no == visit_no)
        if date_from:
            stmt = stmt.where(Visit.visit_time >= date_from)
        if date_to:
            stmt = stmt.where(Visit.visit_time <= date_to)
        if department:
            stmt = stmt.where(Visit.department == department)
        if visit_type:
            stmt = stmt.where(Visit.visit_type == visit_type)
        if doctor_name:
            stmt = stmt.where(Visit.doctor_name == doctor_name)
        if status:
            stmt = stmt.where(Visit.status == status)

        sort_field_map = {
            "visit_time": Visit.visit_time,
            "created_at": Visit.created_at,
            "updated_at": Visit.updated_at,
        }
        sort_field = sort_field_map.get(sort_by, Visit.visit_time)
        order_by = asc if str(sort_order).lower() == "asc" else desc
        stmt = stmt.order_by(order_by(sort_field), desc(Visit.created_at)).limit(limit)
        return self.session.execute(stmt).scalars().all()

    def update_visit(self, visit_id, **updates):
        visit = self.get_by_id(visit_id)
        if visit is None:
            return None

        for field, value in updates.items():
            if hasattr(visit, field):
                setattr(visit, field, value)

        self.session.commit()
        self.session.refresh(visit)
        return visit


class UploadedImageRepository(object):
    def __init__(self, session):
        self.session = session

    def create_image(self, **image_data):
        image = UploadedImage(**image_data)
        self.session.add(image)
        self.session.commit()
        self.session.refresh(image)
        return image

    def get_by_id(self, image_id):
        return self.session.get(UploadedImage, image_id)

    def delete_image(self, image_id):
        image = self.get_by_id(image_id)
        if image is None:
            return None
        self.session.delete(image)
        self.session.commit()
        return image

    def list_by_patient(self, patient_id, limit=50):
        stmt = (
            select(UploadedImage)
            .where(UploadedImage.patient_id == patient_id)
            .order_by(desc(UploadedImage.created_at))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()


class ChatSessionRepository(object):
    def __init__(self, session):
        self.session = session

    def create_session(self, **session_data):
        chat_session = ChatSession(**session_data)
        self.session.add(chat_session)
        self.session.commit()
        self.session.refresh(chat_session)
        return chat_session

    def get_by_id(self, session_id):
        return self.session.get(ChatSession, session_id)

    def list_sessions(self, limit=20, cursor=None):
        stmt = select(ChatSession).order_by(desc(ChatSession.updated_at), desc(ChatSession.created_at))
        if cursor:
            chat_session = self.get_by_id(cursor)
            if chat_session is not None:
                stmt = stmt.where(ChatSession.updated_at <= chat_session.updated_at)
        stmt = stmt.limit(limit)
        return self.session.execute(stmt).scalars().all()

    def update_session(self, session_id, **updates):
        chat_session = self.get_by_id(session_id)
        if chat_session is None:
            return None

        for field, value in updates.items():
            if hasattr(chat_session, field):
                setattr(chat_session, field, value)

        self.session.commit()
        self.session.refresh(chat_session)
        return chat_session

    def bind_patient(self, session_id, patient_id):
        chat_session = self.get_by_id(session_id)
        if chat_session is None:
            return None
        if chat_session.patient_id != patient_id:
            chat_session.patient_id = patient_id
            self.session.commit()
            self.session.refresh(chat_session)
        return chat_session

    def to_list_item(self, chat_session):
        preview_stmt = (
            select(Message.content)
            .where(
                Message.session_id == chat_session.id,
                Message.message_type.in_(("user_input", "final_answer")),
                Message.content.isnot(None),
            )
            .order_by(desc(Message.sequence_no), desc(Message.created_at))
            .limit(1)
        )
        last_message_preview = self.session.execute(preview_stmt).scalar_one_or_none()
        return {
            "id": chat_session.id,
            "patient_id": chat_session.patient_id,
            "title": chat_session.title,
            "status": chat_session.status,
            "updated_at": chat_session.updated_at,
            "created_at": chat_session.created_at,
            "last_message_preview": last_message_preview,
        }


class MessageRepository(object):
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _serialize_payload(payload):
        if payload in (None, ""):
            return None
        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def _deserialize_payload(payload_json):
        if not payload_json:
            return None
        try:
            return json.loads(payload_json)
        except (TypeError, ValueError):
            return {"raw": payload_json}

    def _next_sequence_no(self, session_id):
        stmt = select(func.max(Message.sequence_no)).where(Message.session_id == session_id)
        current = self.session.execute(stmt).scalar_one()
        return (current or 0) + 1

    def create_message(self, session_id, role, message_type, content=None, payload=None, **extra_fields):
        chat_session = self.session.get(ChatSession, session_id)
        if chat_session is not None:
            chat_session.updated_at = datetime.utcnow()
        message = Message(
            session_id=session_id,
            role=role,
            message_type=message_type,
            content=content,
            payload_json=self._serialize_payload(payload),
            sequence_no=extra_fields.pop("sequence_no", None) or self._next_sequence_no(session_id),
            **extra_fields
        )
        self.session.add(message)
        self.session.commit()
        self.session.refresh(message)
        return message

    def list_by_session(self, session_id, limit=200):
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(asc(Message.sequence_no), asc(Message.created_at))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()

    def list_context_messages(self, session_id, limit=6):
        stmt = (
            select(Message)
            .where(Message.session_id == session_id, Message.visible_in_context.is_(True))
            .order_by(desc(Message.sequence_no), desc(Message.created_at))
            .limit(limit)
        )
        messages = self.session.execute(stmt).scalars().all()
        return list(reversed(messages))

    def list_by_session_range(self, session_id, from_sequence_no, to_sequence_no):
        stmt = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.sequence_no >= from_sequence_no,
                Message.sequence_no <= to_sequence_no,
            )
            .order_by(asc(Message.sequence_no), asc(Message.created_at))
        )
        return self.session.execute(stmt).scalars().all()

    def list_sequence_numbers_by_type(self, session_id, message_type):
        stmt = (
            select(Message.sequence_no)
            .where(Message.session_id == session_id, Message.message_type == message_type)
            .order_by(asc(Message.sequence_no))
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_latest_sequence_no(self, session_id):
        stmt = select(func.max(Message.sequence_no)).where(Message.session_id == session_id)
        value = self.session.execute(stmt).scalar_one()
        return value or 0

    def to_read_model(self, message):
        return {
            "id": message.id,
            "session_id": message.session_id,
            "sequence_no": message.sequence_no,
            "role": message.role,
            "message_type": message.message_type,
            "content": message.content,
            "tool_name": message.tool_name,
            "tool_call_id": message.tool_call_id,
            "payload": self._deserialize_payload(message.payload_json),
            "visible_in_context": message.visible_in_context,
            "created_at": message.created_at,
        }


class ChatAttachmentRepository(object):
    def __init__(self, session):
        self.session = session

    def create_attachment(self, **attachment_data):
        attachment = ChatAttachment(**attachment_data)
        self.session.add(attachment)
        self.session.commit()
        self.session.refresh(attachment)
        return attachment

    def get_by_id(self, attachment_id):
        return self.session.get(ChatAttachment, attachment_id)

    def list_by_session(self, session_id):
        stmt = (
            select(ChatAttachment)
            .where(ChatAttachment.session_id == session_id)
            .order_by(desc(ChatAttachment.created_at))
        )
        return self.session.execute(stmt).scalars().all()

    def get_latest_by_session(self, session_id):
        stmt = (
            select(ChatAttachment)
            .where(ChatAttachment.session_id == session_id)
            .order_by(desc(ChatAttachment.created_at))
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def update_attachment(self, attachment_id, **updates):
        attachment = self.get_by_id(attachment_id)
        if attachment is None:
            return None
        for field, value in updates.items():
            if hasattr(attachment, field):
                setattr(attachment, field, value)
        self.session.commit()
        self.session.refresh(attachment)
        return attachment

    def delete_attachment(self, attachment_id):
        attachment = self.get_by_id(attachment_id)
        if attachment is None:
            return None
        self.session.delete(attachment)
        self.session.commit()
        return attachment
