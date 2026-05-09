"""Text-to-speech service package."""

from .api import register_tts_routes
from .service import QwenOmniTtsService

__all__ = ["QwenOmniTtsService", "register_tts_routes"]
