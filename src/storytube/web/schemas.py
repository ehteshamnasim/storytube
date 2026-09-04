from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ConfigUpdateRequest(BaseModel):
    values: dict[str, str]


class PromptSaveRequest(BaseModel):
    text: str


class StorySaveRequest(BaseModel):
    name: str
    text: str


class VoicePreviewRequest(BaseModel):
    provider: str = "edge"
    voice: str = "en-US-AriaNeural"
    language: str = "English"


class RemixRequest(BaseModel):
    music_file: Optional[str] = None
    music_volume: float = 0.16
    ambience_volume: float = 0.05


class GenerateRequest(BaseModel):
    story_name: str
    story_text: str

    style: str = "anime/manga style"
    language: str = "English"
    category: str = "general"

    tts_provider: str = "edge"
    voice: str = "en-US-AriaNeural"
    voice_rate: str = "+0%"
    voice_pitch: str = "+0Hz"
    sarvam_speaker: str = "shubh"
    indicf5_voice: str = "mar_m"
    intro_enabled: bool = True
    intro_title: str = ""
    intro_subtitle: str = ""
    outro_enabled: bool = True
    outro_title: str = "Thank you for watching"
    outro_subtitle: str = "Subscribe for more stories"
    sarvam_pace: float = 1.0
    sarvam_temperature: float = 0.6

    size: str = "1920x1080"
    transition: float = 0.6
    scene_pause: float = 0.6
    ambience_volume: float = 0.1
    music_volume: float = 0.0
    music_style: str = "arabic"
    music_file: Optional[str] = None

    force_replan: bool = False
    force_images: bool = False
    force_voice: bool = False
