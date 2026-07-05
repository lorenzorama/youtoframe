from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class JobCreateRequest(BaseModel):
    youtube_urls: list[str]
    interval_seconds: Optional[float] = None
    manual_timestamps: Optional[list[float]] = None
    save_to_output: bool = False
    output_subdir: Optional[str] = None


class JobResponse(BaseModel):
    id: int
    youtube_url: str
    status: str
    error_message: Optional[str] = None
    frames_total: int
    frames_done: int
    created_at: datetime
    save_to_output: bool
    output_subdir: Optional[str]
    output_index: Optional[int]

    class Config:
        from_attributes = True


class FrameResponse(BaseModel):
    id: int
    timestamp_seconds: float
    caption: Optional[str] = None

    class Config:
        from_attributes = True


class TranscriptCueResponse(BaseModel):
    start_seconds: float
    end_seconds: float
    text: str

    class Config:
        from_attributes = True


class TranscriptResponse(BaseModel):
    language: Optional[str] = None
    source: Optional[str] = None
    cues: list[TranscriptCueResponse]
