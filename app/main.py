"""FastAPI application entrypoint for the patient agent backend."""

import json
import os
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent import PatientAgentService, register_agent_routes
from app.agent.schemas import (
    AgentInvokeRequest,
    ChatMessageRead,
    ChatSessionContextRead,
    ChatSessionCreateRequest,
    ChatSessionListItemRead,
    ChatSessionRead,
    ChatSessionUpdateRequest,
)
from app.db import (
    ChatAttachmentRepository,
    ChatSessionRepository,
    MedicalRecordRepository,
    MessageRepository,
    PatientRepository,
    UploadedImageRepository,
    VisitRepository,
    init_database,
)
from app.images import UploadedImageStorageService
from app.memory import LongTermMemoryService, MemoryExtractionWorker, QwenEmbeddingClient, init_memory_database
from app.memory.extractor import LongTermMemoryExtractor
from app.memory.schemas import (
    EventMemoryRead,
    MemoryExtractionJobRead,
    MemoryRecallRead,
    MemoryRecallRequest,
    ProfileMemoryRead,
)
from app.mcp.api import register_mcp_routes
from app.mcp.router import build_mcp_registry
from app.runtime_env import load_dotenv_file
from app.schemas import (
    MedicalRecordCreate,
    MedicalRecordRead,
    MedicalRecordUpdate,
    PatientCreate,
    PatientRead,
    PatientUpdate,
    ChatAttachmentDeleteResponse,
    ChatAttachmentRead,
    UploadedImageRead,
    UploadedImageUploadRequest,
    VisitCreate,
    VisitRead,
    VisitUpdate,
)
from app.tts import QwenOmniTtsService, register_tts_routes


def _raise_integrity_error(error, duplicate_message, default_message):
    detail = str(getattr(error, "orig", error)).lower()
    if "unique" in detail or "duplicate" in detail:
        raise HTTPException(status_code=409, detail=duplicate_message)
    raise HTTPException(status_code=400, detail=default_message)


def _env_enabled(name, default="true"):
    return str(os.getenv(name, default)).strip().lower() not in ("0", "false", "no")


def _env_int(name, default):
    raw = str(os.getenv(name, default)).strip()
    try:
        return int(raw)
    except ValueError:
        digits = "".join(ch for ch in raw if ch.isdigit())
        return int(digits or default)


def _build_attachment_response(attachment):
    return {
        "id": attachment.id,
        "kind": attachment.kind,
        "status": attachment.status,
        "session_id": attachment.session_id,
        "patient_id": attachment.patient_id,
        "record_id": attachment.record_id,
        "visit_id": attachment.visit_id,
        "image_id": attachment.image_id,
        "file_name": attachment.file_name,
        "mime_type": attachment.mime_type,
        "file_size": attachment.file_size,
        "width": attachment.width,
        "height": attachment.height,
        "preview_url": "/api/v1/chat/attachments/{0}/preview".format(attachment.id),
        "download_url": "/api/v1/chat/attachments/{0}/file".format(attachment.id),
        "source": attachment.source,
        "created_at": attachment.created_at,
    }


def _sse_event(event, data):
    return "event: {0}\ndata: {1}\n\n".format(event, json.dumps(data, ensure_ascii=False, default=str))


def create_app(database_url=None, memory_database_url=None, start_memory_worker=None):
    """Create a FastAPI application instance."""

    load_dotenv_file()

    openapi_tags = [
        {"name": "System", "description": "Health checks and system endpoints."},
        {"name": "Patient", "description": "Patient profile CRUD endpoints."},
        {"name": "MedicalRecord", "description": "Medical record CRUD endpoints."},
        {"name": "Visit", "description": "Visit CRUD endpoints."},
        {"name": "Image", "description": "Uploaded image and attachment endpoints."},
        {"name": "MCP", "description": "MCP server and tool routing endpoints."},
        {"name": "Agent", "description": "Patient agent orchestration endpoints."},
        {"name": "Speech", "description": "Speech synthesis and audio file endpoints."},
        {"name": "Memory", "description": "Long-term memory endpoints."},
    ]

    app = FastAPI(
        title="Patient Agent API",
        description=(
            "Provides patient, record, visit, image upload, MCP tool routing, "
            "agent orchestration, chat sessions, and long-term memory endpoints."
        ),
        version="1.6.0",
        openapi_tags=openapi_tags,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine, session_factory = init_database(database_url)
    app.state.engine = engine
    app.state.SessionLocal = session_factory

    resolved_memory_database_url = memory_database_url if memory_database_url is not None else os.getenv("MEMORY_DATABASE_URL")
    memory_init_error = None
    try:
        memory_engine, memory_session_factory = init_memory_database(resolved_memory_database_url)
    except Exception as exc:  # pragma: no cover - defensive fallback for local startup misconfiguration
        memory_engine, memory_session_factory = None, None
        memory_init_error = str(exc)
    app.state.memory_engine = memory_engine
    app.state.MemorySessionLocal = memory_session_factory
    app.state.memory_init_error = memory_init_error

    app.state.image_storage_service = UploadedImageStorageService()
    app.state.tts_service = QwenOmniTtsService()
    app.state.mcp_registry = build_mcp_registry(session_factory, tts_service=app.state.tts_service)
    if not app.state.tts_service.api_key:
        app.state.tts_service.api_key = app.state.mcp_registry.qwen_client.api_key
    if not app.state.tts_service.base_url:
        app.state.tts_service.base_url = app.state.mcp_registry.qwen_client.base_url

    memory_service = None
    if memory_session_factory is not None:
        embedding_client = None
        if memory_engine is not None and memory_engine.dialect.name == "postgresql" and _env_enabled("MEMORY_EMBEDDING_ENABLED", "true"):
            dimensions = _env_int("MEMORY_EMBEDDING_DIMENSIONS", 1024)
            embedding_client = QwenEmbeddingClient(dimensions=dimensions if dimensions > 0 else None)
        memory_service = LongTermMemoryService(
            session_factory,
            memory_session_factory,
            extractor=LongTermMemoryExtractor(),
            embedder=embedding_client,
            max_retries=_env_int("MEMORY_EXTRACTION_MAX_RETRIES", 3),
            retrieval_enabled=_env_enabled("MEMORY_RETRIEVAL_ENABLED", "true"),
            dense_topn=_env_int("MEMORY_RETRIEVAL_DENSE_TOPN", 10),
            keyword_topn=_env_int("MEMORY_RETRIEVAL_KEYWORD_TOPN", 10),
            retrieval_topk=_env_int("MEMORY_RETRIEVAL_TOPK", 8),
            rrf_k=_env_int("MEMORY_RRF_K", 60),
        )
    app.state.memory_service = memory_service

    app.state.agent_service = PatientAgentService(
        session_factory,
        app.state.mcp_registry,
        memory_service=memory_service,
    )
    if app.state.memory_service is not None:
        app.state.memory_service.extractor.llm = app.state.agent_service.llm

    if start_memory_worker is None:
        start_memory_worker = _env_enabled("MEMORY_EXTRACTION_ENABLED", "true")
    app.state.should_start_memory_worker = bool(start_memory_worker and app.state.memory_service is not None)
    app.state.memory_worker = None

    def get_db(request: Request):
        db = request.app.state.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def get_memory_service(request: Request):
        service = request.app.state.memory_service
        if service is None:
            raise HTTPException(status_code=503, detail="Long-term memory service is not configured.")
        return service

    def ensure_patient_exists(db, patient_id):
        patient = PatientRepository(db).get_by_id(patient_id)
        if patient is None:
            raise HTTPException(status_code=404, detail="鎮ｈ€呬笉瀛樺湪")
        return patient

    def ensure_record_exists(db, record_id):
        record = MedicalRecordRepository(db).get_by_id(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Medical record was not found.")
        return record

    def ensure_visit_exists(db, visit_id):
        visit = VisitRepository(db).get_by_id(visit_id)
        if visit is None:
            raise HTTPException(status_code=404, detail="Visit was not found.")
        return visit

    @app.get("/health", tags=["System"], summary="Health check")
    def health_check():
        return {"status": "ok"}

    @app.post("/api/v1/patients", response_model=PatientRead, tags=["Patient"], summary="Create patient")
    def create_patient(payload: PatientCreate, db: Session = Depends(get_db)):
        repo = PatientRepository(db)
        try:
            return repo.create_patient(**payload.dict())
        except IntegrityError as exc:
            db.rollback()
            _raise_integrity_error(exc, "Patient number or id card already exists.", "Failed to create patient record.")

    @app.get("/api/v1/patients", response_model=List[PatientRead], tags=["Patient"], summary="List patients")
    def list_patients(
        patient_no: Optional[str] = Query(None, description="Filter by patient number"),
        id_card: Optional[str] = Query(None, description="Filter by id card"),
        limit: int = Query(50, ge=1, le=200, description="杩斿洖鏉℃暟"),
        db: Session = Depends(get_db),
    ):
        repo = PatientRepository(db)
        if patient_no:
            patient = repo.get_by_patient_no(patient_no)
            return [patient] if patient else []
        if id_card:
            patient = repo.get_by_id_card(id_card)
            return [patient] if patient else []
        return repo.list_patients(limit=limit)

    @app.get("/api/v1/patients/{patient_id}", response_model=PatientRead, tags=["Patient"], summary="Get patient by id")
    def get_patient(patient_id: str, db: Session = Depends(get_db)):
        patient = PatientRepository(db).get_by_id(patient_id)
        if patient is None:
            raise HTTPException(status_code=404, detail="鎮ｈ€呬笉瀛樺湪")
        return patient

    @app.get(
        "/api/v1/patients/by-patient-no/{patient_no}",
        response_model=PatientRead,
        tags=["Patient"],
        summary="Get patient by patient number",
    )
    def get_patient_by_patient_no(patient_no: str, db: Session = Depends(get_db)):
        patient = PatientRepository(db).get_by_patient_no(patient_no)
        if patient is None:
            raise HTTPException(status_code=404, detail="鎮ｈ€呬笉瀛樺湪")
        return patient

    @app.patch("/api/v1/patients/{patient_id}", response_model=PatientRead, tags=["Patient"], summary="Update patient")
    def update_patient(patient_id: str, payload: PatientUpdate, db: Session = Depends(get_db)):
        repo = PatientRepository(db)
        try:
            patient = repo.update_patient(patient_id, **payload.dict(exclude_unset=True))
        except IntegrityError as exc:
            db.rollback()
            _raise_integrity_error(exc, "Patient number or id card already exists.", "Failed to update patient record.")
        if patient is None:
            raise HTTPException(status_code=404, detail="鎮ｈ€呬笉瀛樺湪")
        return patient

    @app.post(
        "/api/v1/patients/{patient_id}/medical-records",
        response_model=MedicalRecordRead,
        tags=["鐥呭巻"],
        summary="鍒涘缓鐥呭巻璁板綍",
    )
    def create_medical_record(patient_id: str, payload: MedicalRecordCreate, db: Session = Depends(get_db)):
        ensure_patient_exists(db, patient_id)
        return MedicalRecordRepository(db).create_record(patient_id=patient_id, **payload.dict())

    @app.get(
        "/api/v1/patients/{patient_id}/medical-records",
        response_model=List[MedicalRecordRead],
        tags=["鐥呭巻"],
        summary="List patient medical records",
    )
    def list_medical_records(
        patient_id: str,
        limit: int = Query(50, ge=1, le=200, description="杩斿洖鏉℃暟"),
        db: Session = Depends(get_db),
    ):
        ensure_patient_exists(db, patient_id)
        return MedicalRecordRepository(db).list_by_patient(patient_id, limit=limit)

    @app.get("/api/v1/medical-records/{record_id}", response_model=MedicalRecordRead, tags=["鐥呭巻"], summary="鏌ヨ鐥呭巻璇︽儏")
    def get_medical_record(record_id: str, db: Session = Depends(get_db)):
        record = MedicalRecordRepository(db).get_by_id(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Medical record was not found.")
        return record

    @app.patch("/api/v1/medical-records/{record_id}", response_model=MedicalRecordRead, tags=["鐥呭巻"], summary="鏇存柊鐥呭巻璁板綍")
    def update_medical_record(record_id: str, payload: MedicalRecordUpdate, db: Session = Depends(get_db)):
        record = MedicalRecordRepository(db).update_record(record_id, **payload.dict(exclude_unset=True))
        if record is None:
            raise HTTPException(status_code=404, detail="Medical record was not found.")
        return record

    @app.post("/api/v1/patients/{patient_id}/visits", response_model=VisitRead, tags=["灏辫瘖"], summary="鍒涘缓灏辫瘖璁板綍")
    def create_visit(patient_id: str, payload: VisitCreate, db: Session = Depends(get_db)):
        ensure_patient_exists(db, patient_id)
        repo = VisitRepository(db)
        try:
            return repo.create_visit(patient_id=patient_id, **payload.dict())
        except IntegrityError as exc:
            db.rollback()
            _raise_integrity_error(exc, "Visit number already exists.", "Failed to create visit record.")

    @app.get("/api/v1/patients/{patient_id}/visits", response_model=List[VisitRead], tags=["Visit"], summary="List patient visits")
    def list_visits(
        patient_id: str,
        limit: int = Query(50, ge=1, le=200, description="杩斿洖鏉℃暟"),
        db: Session = Depends(get_db),
    ):
        ensure_patient_exists(db, patient_id)
        return VisitRepository(db).list_by_patient(patient_id, limit=limit)

    @app.get("/api/v1/visits/{visit_id}", response_model=VisitRead, tags=["灏辫瘖"], summary="鏌ヨ灏辫瘖璇︽儏")
    def get_visit(visit_id: str, db: Session = Depends(get_db)):
        visit = VisitRepository(db).get_by_id(visit_id)
        if visit is None:
            raise HTTPException(status_code=404, detail="Visit was not found.")
        return visit

    @app.patch("/api/v1/visits/{visit_id}", response_model=VisitRead, tags=["灏辫瘖"], summary="鏇存柊灏辫瘖璁板綍")
    def update_visit(visit_id: str, payload: VisitUpdate, db: Session = Depends(get_db)):
        repo = VisitRepository(db)
        try:
            visit = repo.update_visit(visit_id, **payload.dict(exclude_unset=True))
        except IntegrityError as exc:
            db.rollback()
            _raise_integrity_error(exc, "Visit number already exists.", "Failed to update visit record.")
        if visit is None:
            raise HTTPException(status_code=404, detail="Visit was not found.")
        return visit

    @app.post("/api/v1/images/upload", response_model=UploadedImageRead, tags=["Image"], summary="Upload one image")
    def upload_image(payload: UploadedImageUploadRequest, db: Session = Depends(get_db)):
        if payload.patient_id:
            ensure_patient_exists(db, payload.patient_id)
        if payload.record_id:
            ensure_record_exists(db, payload.record_id)
        if payload.visit_id:
            ensure_visit_exists(db, payload.visit_id)

        try:
            content = payload.decode_content()
        except Exception:
            raise HTTPException(status_code=400, detail="鍥剧墖 Base64 鍐呭鏃犳晥")
        if not content:
            raise HTTPException(status_code=400, detail="涓婁紶鍥剧墖涓嶈兘涓虹┖")

        storage_result = app.state.image_storage_service.save_file(payload.file_name, content)
        image = UploadedImageRepository(db).create_image(
            patient_id=payload.patient_id,
            record_id=payload.record_id,
            visit_id=payload.visit_id,
            image_type=payload.image_type,
            original_file_name=payload.file_name,
            stored_file_name=storage_result["stored_file_name"],
            file_path=storage_result["file_path"],
            mime_type=payload.mime_type,
            file_size=storage_result["file_size"],
            source=payload.source,
            notes=payload.notes,
        )
        return image

    @app.get("/api/v1/images/{image_id}", response_model=UploadedImageRead, tags=["Image"], summary="Get uploaded image metadata")
    def get_uploaded_image(image_id: str, db: Session = Depends(get_db)):
        image = UploadedImageRepository(db).get_by_id(image_id)
        if image is None:
            raise HTTPException(status_code=404, detail="Uploaded image was not found.")
        return image

    @app.post(
        "/api/v1/chat/attachments/upload",
        response_model=ChatAttachmentRead,
        tags=["Agent"],
        summary="上传聊天图片附件",
    )
    async def upload_chat_attachment(
        file: UploadFile = File(...),
        session_id: Optional[str] = Form(None),
        patient_id: Optional[str] = Form(None),
        record_id: Optional[str] = Form(None),
        visit_id: Optional[str] = Form(None),
        attachment_type: str = Form("image"),
        source: str = Form("chat_input"),
        db: Session = Depends(get_db),
    ):
        if attachment_type != "image":
            raise HTTPException(status_code=400, detail="Only image attachments are supported.")
        if session_id and ChatSessionRepository(db).get_by_id(session_id) is None:
            raise HTTPException(status_code=404, detail="Session was not found.")
        if patient_id:
            ensure_patient_exists(db, patient_id)
        if record_id:
            ensure_record_exists(db, record_id)
        if visit_id:
            ensure_visit_exists(db, visit_id)

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded image cannot be empty.")

        storage_result = app.state.image_storage_service.save_file(file.filename, content)
        image = UploadedImageRepository(db).create_image(
            patient_id=patient_id,
            record_id=record_id,
            visit_id=visit_id,
            image_type="chat_attachment",
            original_file_name=file.filename,
            stored_file_name=storage_result["stored_file_name"],
            file_path=storage_result["file_path"],
            mime_type=file.content_type or "application/octet-stream",
            file_size=storage_result["file_size"],
            source=source,
            notes=None,
        )
        attachment = ChatAttachmentRepository(db).create_attachment(
            session_id=session_id,
            patient_id=patient_id,
            record_id=record_id,
            visit_id=visit_id,
            image_id=image.id,
            kind="image",
            status="ready",
            file_name=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            file_size=storage_result["file_size"],
            source=source,
        )
        return _build_attachment_response(attachment)

    @app.get(
        "/api/v1/chat/attachments/{attachment_id}/preview",
        response_class=FileResponse,
        tags=["Agent"],
        summary="预览聊天附件",
    )
    def preview_chat_attachment(attachment_id: str, db: Session = Depends(get_db)):
        attachment = ChatAttachmentRepository(db).get_by_id(attachment_id)
        if attachment is None:
            raise HTTPException(status_code=404, detail="Attachment was not found.")
        image = UploadedImageRepository(db).get_by_id(attachment.image_id)
        if image is None:
            raise HTTPException(status_code=404, detail="Uploaded image was not found.")
        return FileResponse(image.file_path, media_type=image.mime_type, filename=image.original_file_name)

    @app.get(
        "/api/v1/chat/attachments/{attachment_id}/file",
        response_class=FileResponse,
        tags=["Agent"],
        summary="下载聊天附件",
    )
    def download_chat_attachment(attachment_id: str, db: Session = Depends(get_db)):
        attachment = ChatAttachmentRepository(db).get_by_id(attachment_id)
        if attachment is None:
            raise HTTPException(status_code=404, detail="Attachment was not found.")
        image = UploadedImageRepository(db).get_by_id(attachment.image_id)
        if image is None:
            raise HTTPException(status_code=404, detail="Uploaded image was not found.")
        return FileResponse(
            image.file_path,
            media_type=image.mime_type,
            filename=image.original_file_name,
            content_disposition_type="attachment",
        )

    @app.delete(
        "/api/v1/chat/attachments/{attachment_id}",
        response_model=ChatAttachmentDeleteResponse,
        tags=["Agent"],
        summary="删除聊天附件",
    )
    def delete_chat_attachment(attachment_id: str, db: Session = Depends(get_db)):
        attachment_repo = ChatAttachmentRepository(db)
        attachment = attachment_repo.get_by_id(attachment_id)
        if attachment is None:
            raise HTTPException(status_code=404, detail="Attachment was not found.")
        image = UploadedImageRepository(db).get_by_id(attachment.image_id)
        attachment_repo.delete_attachment(attachment_id)
        if image is not None:
            app.state.image_storage_service.delete_file(image.file_path)
            UploadedImageRepository(db).delete_image(image.id)
        return {"deleted": True, "attachment_id": attachment_id}

    @app.post("/api/v1/chat/sessions", response_model=ChatSessionRead, tags=["Agent"], summary="创建会话")
    def create_chat_session(payload: ChatSessionCreateRequest, db: Session = Depends(get_db)):
        if payload.patient_id:
            ensure_patient_exists(db, payload.patient_id)
        return ChatSessionRepository(db).create_session(**payload.dict())

    @app.get("/api/v1/chat/sessions", response_model=List[ChatSessionListItemRead], tags=["Agent"], summary="列出会话")
    def list_chat_sessions(
        limit: int = Query(20, ge=1, le=100, description="返回会话数量"),
        cursor: Optional[str] = Query(None, description="分页游标"),
        db: Session = Depends(get_db),
    ):
        repo = ChatSessionRepository(db)
        return [repo.to_list_item(item) for item in repo.list_sessions(limit=limit, cursor=cursor)]

    @app.get("/api/v1/chat/sessions/{session_id}", response_model=ChatSessionRead, tags=["Agent"], summary="查询会话")
    def get_chat_session(session_id: str, db: Session = Depends(get_db)):
        chat_session = ChatSessionRepository(db).get_by_id(session_id)
        if chat_session is None:
            raise HTTPException(status_code=404, detail="Session was not found.")
        return chat_session

    @app.patch("/api/v1/chat/sessions/{session_id}", response_model=ChatSessionRead, tags=["Agent"], summary="更新会话")
    def update_chat_session(session_id: str, payload: ChatSessionUpdateRequest, db: Session = Depends(get_db)):
        chat_session = ChatSessionRepository(db).update_session(session_id, **payload.dict(exclude_unset=True))
        if chat_session is None:
            raise HTTPException(status_code=404, detail="Session was not found.")
        return chat_session

    @app.get(
        "/api/v1/chat/sessions/{session_id}/messages",
        response_model=List[ChatMessageRead],
        tags=["Agent"],
        summary="查询会话消息",
    )
    def list_chat_messages(
        session_id: str,
        limit: int = Query(200, ge=1, le=500, description="返回消息条数"),
        db: Session = Depends(get_db),
    ):
        chat_session = ChatSessionRepository(db).get_by_id(session_id)
        if chat_session is None:
            raise HTTPException(status_code=404, detail="Session was not found.")
        repo = MessageRepository(db)
        return [repo.to_read_model(item) for item in repo.list_by_session(session_id, limit=limit)]

    @app.get(
        "/api/v1/chat/sessions/{session_id}/context",
        response_model=ChatSessionContextRead,
        tags=["Agent"],
        summary="查询会话聚合上下文",
    )
    def get_chat_session_context(session_id: str, db: Session = Depends(get_db)):
        session_repo = ChatSessionRepository(db)
        chat_session = session_repo.get_by_id(session_id)
        if chat_session is None:
            raise HTTPException(status_code=404, detail="Session was not found.")

        patient = None
        if chat_session.patient_id:
            patient_model = PatientRepository(db).get_by_id(chat_session.patient_id)
            if patient_model is not None:
                patient = PatientRead.from_orm(patient_model).dict()

        message_repo = MessageRepository(db)
        messages = message_repo.list_by_session(session_id, limit=50)
        latest_agent_run = None
        for item in reversed(messages):
            if item.message_type == "final_answer":
                payload = message_repo.to_read_model(item).get("payload") or {}
                latest_agent_run = {
                    "run_id": payload.get("run_id"),
                    "final_answer": item.content,
                    "created_at": item.created_at,
                }
                break

        attachments = [_build_attachment_response(item) for item in ChatAttachmentRepository(db).list_by_session(session_id)]
        return {
            "session": chat_session,
            "patient": patient,
            "latest_agent_run": latest_agent_run,
            "attachments": attachments,
        }

    @app.get(
        "/api/v1/memory/patients/{patient_id}/events",
        response_model=List[EventMemoryRead],
        tags=["Memory"],
        summary="List patient event memories",
    )
    def list_event_memories(
        patient_id: str,
        limit: int = Query(50, ge=1, le=200, description="杩斿洖璁板繂鏉℃暟"),
        db: Session = Depends(get_db),
        memory_service=Depends(get_memory_service),
    ):
        ensure_patient_exists(db, patient_id)
        return memory_service.list_event_memories(patient_id, limit=limit)

    @app.get(
        "/api/v1/memory/patients/{patient_id}/profiles",
        response_model=List[ProfileMemoryRead],
        tags=["Memory"],
        summary="List patient profile memories",
    )
    def list_profile_memories(
        patient_id: str,
        limit: int = Query(50, ge=1, le=200, description="杩斿洖璁板繂鏉℃暟"),
        db: Session = Depends(get_db),
        memory_service=Depends(get_memory_service),
    ):
        ensure_patient_exists(db, patient_id)
        return memory_service.list_profile_memories(patient_id, limit=limit)

    @app.post(
        "/api/v1/memory/patients/{patient_id}/recall",
        response_model=MemoryRecallRead,
        tags=["Memory"],
        summary="鐠嬪啳鐦梹鎸庢埂鐠佹澘绻傞崣顒€娲栫紒鎾寸亯",
    )
    def recall_long_term_memories(
        patient_id: str,
        payload: MemoryRecallRequest,
        db: Session = Depends(get_db),
        memory_service=Depends(get_memory_service),
    ):
        ensure_patient_exists(db, patient_id)
        return memory_service.recall_long_term_memories(patient_id, payload.query)

    @app.get(
        "/api/v1/memory/jobs/{job_id}",
        response_model=MemoryExtractionJobRead,
        tags=["Memory"],
        summary="鏌ヨ闀挎湡璁板繂鎶藉彇浠诲姟",
    )
    def get_memory_job(job_id: str, memory_service=Depends(get_memory_service)):
        job = memory_service.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Memory extraction job was not found.")
        return job

    @app.on_event("startup")
    def startup_memory_worker():
        if not app.state.should_start_memory_worker:
            return
        worker = MemoryExtractionWorker(
            app.state.memory_service,
            poll_interval_seconds=_env_int("MEMORY_EXTRACTION_POLL_INTERVAL_SECONDS", 5),
        )
        worker.start()
        app.state.memory_worker = worker

    @app.on_event("shutdown")
    def shutdown_memory_worker():
        worker = getattr(app.state, "memory_worker", None)
        if worker is not None:
            worker.stop()
            app.state.memory_worker = None

    register_mcp_routes(app)
    register_agent_routes(app)
    register_tts_routes(app)
    return app


app = create_app()

