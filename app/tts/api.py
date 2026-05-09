"""FastAPI route registration for text-to-speech APIs."""

from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .schemas import TtsSynthesizeRequest, TtsSynthesizeResponse
from .service import TtsSynthesisError


def register_tts_routes(app):
    """Register text-to-speech routes on an existing FastAPI app."""

    def get_tts_service(request: Request):
        return request.app.state.tts_service

    @app.post(
        "/api/v1/tts/synthesize",
        response_model=TtsSynthesizeResponse,
        tags=["语音"],
        summary="生成语音播报并保存到本地",
    )
    def synthesize_speech(payload: TtsSynthesizeRequest, tts_service=Depends(get_tts_service)):
        try:
            return tts_service.synthesize_to_file(
                text=payload.text,
                voice=payload.voice,
                file_name=payload.file_name,
            )
        except TtsSynthesisError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/v1/tts/files/{file_name}", tags=["语音"], summary="下载已生成的语音文件")
    def download_speech_file(file_name: str, tts_service=Depends(get_tts_service)):
        file_path = (tts_service.output_dir / file_name).resolve()
        if not str(file_path).startswith(str(tts_service.output_dir.resolve())):
            raise HTTPException(status_code=400, detail="非法文件路径。")
        if not Path(file_path).exists():
            raise HTTPException(status_code=404, detail="音频文件不存在。")
        return FileResponse(path=str(file_path), media_type="audio/mpeg", filename=file_name)
