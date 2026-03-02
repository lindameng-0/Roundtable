from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict, Any


class ManuscriptCreate(BaseModel):
    title: Optional[str] = "Untitled Manuscript"
    raw_text: str
    model: Optional[str] = "gpt-4o-mini"


class ManuscriptResponse(BaseModel):
    id: str
    title: str
    user_id: Optional[str] = None
    genre: Optional[str] = None
    target_audience: Optional[str] = None
    age_range: Optional[str] = None
    comparable_books: Optional[List[str]] = None
    model: Optional[str] = None
    sections: Optional[List[Dict]] = None
    total_sections: Optional[int] = None
    total_lines: Optional[int] = None
    created_at: str


class ReaderPersonaResponse(BaseModel):
    id: str
    manuscript_id: str
    name: str
    age: int
    occupation: str
    personality: str
    reading_habits: str
    liked_tropes: List[str]
    disliked_tropes: List[str]
    voice_style: str
    temperature: float
    quote: str
    avatar_index: int
    personality_specific_instructions: Optional[str] = ""
    favorite_genres: Optional[Any] = ""
    genre_preferences: Optional[Any] = ""
    reading_priority: Optional[Any] = ""
    created_at: str

    @field_validator(
        "favorite_genres", "genre_preferences", "reading_priority",
        "personality_specific_instructions", "reading_habits", "voice_style",
        "quote", "occupation", mode="before"
    )
    @classmethod
    def coerce_to_str(cls, v):
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        if v is None:
            return ""
        return str(v) if str(v).strip() else ""

    @field_validator("name", mode="before")
    @classmethod
    def ensure_name(cls, v):
        if v is None:
            return "Reader"
        s = str(v).strip()
        return s if s else "Reader"


class RegenerateRequest(BaseModel):
    reader_id: Optional[str] = None


class ModelConfigRequest(BaseModel):
    provider: str
    model: str


class AppendTextRequest(BaseModel):
    raw_text_chunk: str


class WaitlistRequest(BaseModel):
    email: str
