from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any


class ManuscriptCreate(BaseModel):
    title: Optional[str] = "Untitled Manuscript"
    raw_text: str
    model: Optional[str] = "gemini-2.5-flash"
    cost_limit_usd: Optional[float] = None

    @field_validator("cost_limit_usd")
    @classmethod
    def validate_cost_limit(cls, value):
        if value is None:
            return value
        if value < 0 or value > 1000:
            raise ValueError("Budget must be between $0 and $1,000; $0 means unlimited")
        return round(float(value), 6)


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
    cost_limit_usd: Optional[float] = None
    cost_spent_usd: Optional[float] = 0
    cost_reserved_usd: Optional[float] = 0
    reader_config_locked: Optional[bool] = False
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
    primary_focus: Optional[str] = None
    secondary_focuses: List[str] = Field(default_factory=list)
    writer_focus_note: Optional[str] = ""
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


class ReaderFocusUpdate(BaseModel):
    primary_focus: Optional[str] = None
    secondary_focuses: List[str] = Field(default_factory=list)
    writer_focus_note: str = ""
    liked_tropes: List[str]
    disliked_tropes: List[str]

    @field_validator("primary_focus")
    @classmethod
    def validate_primary(cls, value):
        from services.reader_focus import FOCUS_LABELS
        if value is not None and value not in FOCUS_LABELS:
            raise ValueError("Unknown primary focus")
        return value

    @field_validator("secondary_focuses")
    @classmethod
    def validate_secondary(cls, value):
        from services.reader_focus import FOCUS_LABELS
        if len(value) > 2 or len(set(value)) != len(value) or any(item not in FOCUS_LABELS for item in value):
            raise ValueError("Choose at most two distinct secondary focuses")
        return value

    @field_validator("writer_focus_note")
    @classmethod
    def validate_note(cls, value):
        normalized = " ".join((value or "").split())
        if len(normalized) > 160:
            raise ValueError("Writer focus note must be 160 characters or fewer")
        return normalized

    @field_validator("liked_tropes", "disliked_tropes")
    @classmethod
    def validate_tastes(cls, value):
        if len(value) > 8 or any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 160 for item in value):
            raise ValueError("Invalid personal taste list")
        return [item.strip() for item in value]

    @model_validator(mode="after")
    def focuses_must_be_distinct(self):
        if self.primary_focus and self.primary_focus in self.secondary_focuses:
            raise ValueError("Primary focus cannot also be a secondary focus")
        return self


class ModelConfigRequest(BaseModel):
    provider: str
    model: str


class AppendTextRequest(BaseModel):
    raw_text_chunk: str


class WaitlistRequest(BaseModel):
    email: str


class FeedbackRequest(BaseModel):
    message: str


class BudgetUpdateRequest(BaseModel):
    cost_limit_usd: float

    @field_validator("cost_limit_usd")
    @classmethod
    def validate_limit(cls, value):
        if value < 0 or value > 1000:
            raise ValueError("Budget must be between $0 and $1,000; $0 means unlimited")
        return round(float(value), 6)
