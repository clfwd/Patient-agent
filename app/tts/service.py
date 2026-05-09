"""Qwen Omni based text-to-speech service."""

import base64
import json
import os
import re
import shutil
import subprocess
import uuid
import wave
from datetime import datetime
from pathlib import Path

import httpx


class TtsSynthesisError(Exception):
    """Raised when text-to-speech generation fails."""


class QwenOmniTtsService(object):
    """Generate local MP3 files with Qwen Omni audio output."""

    AUDIO_FORMAT = "mp3"
    SAMPLE_RATE = 24000
    SOURCE_AUDIO_FORMAT = "wav"

    def __init__(
        self,
        api_key=None,
        base_url=None,
        model=None,
        voice=None,
        timeout=120.0,
        output_dir=None,
    ):
        self.api_key = (
            api_key
            or os.getenv("QWEN_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        self.base_url = (
            base_url
            or os.getenv("QWEN_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        self.model = model or os.getenv("QWEN_OMNI_TTS_MODEL") or "qwen3-omni-flash"
        self.voice = voice or os.getenv("QWEN_OMNI_TTS_VOICE") or "Cherry"
        self.timeout = timeout
        self.output_dir = Path(output_dir or (Path(__file__).resolve().parents[2] / "generated_audio"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = shutil.which("ffmpeg")

    def is_configured(self):
        return bool(self.api_key)

    @staticmethod
    def _sanitize_file_name(file_name):
        if not file_name:
            return None
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name.strip())
        if not safe_name:
            return None
        if not safe_name.lower().endswith(".mp3"):
            safe_name += ".mp3"
        return safe_name

    def _build_output_path(self, file_name=None):
        safe_name = self._sanitize_file_name(file_name)
        if safe_name:
            return self.output_dir / safe_name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        generated_name = "tts_{0}_{1}.mp3".format(timestamp, uuid.uuid4().hex[:8])
        return self.output_dir / generated_name

    def _stream_audio_chunks(self, text, voice):
        if not self.is_configured():
            raise TtsSynthesisError("Qwen API key 未配置，无法生成语音。")

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": text}],
            "modalities": ["text", "audio"],
            "audio": {
                "voice": voice,
                "format": self.SOURCE_AUDIO_FORMAT,
            },
            "stream": True,
        }
        headers = {
            "Authorization": "Bearer {0}".format(self.api_key),
            "Content-Type": "application/json",
        }

        transcript_chunks = []
        audio_chunks = []
        url = "{0}/chat/completions".format(self.base_url)

        with httpx.Client(timeout=self.timeout, trust_env=False) as client:
            try:
                with client.stream("POST", url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        event = json.loads(data)
                        delta = ((event.get("choices") or [{}])[0]).get("delta") or {}
                        if delta.get("content"):
                            transcript_chunks.append(delta["content"])
                        audio_delta = delta.get("audio") or {}
                        if audio_delta.get("data"):
                            audio_chunks.append(base64.b64decode(audio_delta["data"]))
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise TtsSynthesisError("Qwen 语音生成失败: {0}".format(exc))

        if not audio_chunks:
            raise TtsSynthesisError("Qwen 未返回音频数据。")

        transcript = "".join(transcript_chunks).strip() or text
        return transcript, b"".join(audio_chunks)

    def _write_wav_file(self, wav_path, pcm_bytes):
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.SAMPLE_RATE)
            wav_file.writeframes(pcm_bytes)

    def _convert_wav_to_mp3(self, wav_path, output_path):
        if not self.ffmpeg_path:
            raise TtsSynthesisError("未找到 ffmpeg，无法将模型返回音频转换为 mp3。")

        try:
            completed = subprocess.run(
                [
                    self.ffmpeg_path,
                    "-y",
                    "-i",
                    str(wav_path),
                    "-codec:a",
                    "libmp3lame",
                    "-ar",
                    str(self.SAMPLE_RATE),
                    str(output_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as exc:
            raise TtsSynthesisError("调用 ffmpeg 失败: {0}".format(exc))

        if completed.returncode != 0 or not output_path.exists():
            stderr = (completed.stderr or b"").decode("utf-8", errors="ignore")
            raise TtsSynthesisError("ffmpeg 转 mp3 失败: {0}".format(stderr.strip() or completed.returncode))

    def synthesize_to_file(self, text, voice=None, file_name=None):
        requested_text = (text or "").strip()
        if not requested_text:
            raise TtsSynthesisError("播报文本不能为空。")

        selected_voice = voice or self.voice
        output_path = self._build_output_path(file_name=file_name)
        wav_path = output_path.with_suffix(".wav")
        transcript, audio_bytes = self._stream_audio_chunks(requested_text, selected_voice)
        self._write_wav_file(wav_path, audio_bytes)
        self._convert_wav_to_mp3(wav_path, output_path)
        if wav_path.exists():
            wav_path.unlink()

        return {
            "file_name": output_path.name,
            "file_path": str(output_path.resolve()),
            "download_url": "/api/v1/tts/files/{0}".format(output_path.name),
            "transcript": transcript,
            "voice": selected_voice,
            "model": self.model,
            "audio_format": self.AUDIO_FORMAT,
            "sample_rate": self.SAMPLE_RATE,
            "file_size": output_path.stat().st_size,
        }
