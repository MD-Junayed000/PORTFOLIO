import re

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


# Auth schemas
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# About schemas
class AboutContentBase(BaseModel):
    bio: str
    title: str
    photo_url: Optional[str] = None
    education: Optional[str] = None
    focus_area: Optional[str] = None
    subtitle: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    scholar_url: Optional[str] = None
    extra_links: Optional[str] = None  # JSON string of [{name, url, icon}]
    cv_file_path: Optional[str] = None


class AboutContentResponse(AboutContentBase):
    id: int

    class Config:
        from_attributes = True


# Project schemas
class ProjectBase(BaseModel):
    name: str
    description: str
    tech_stack: str
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    image_url: Optional[str] = None
    order: int = 0


class ProjectResponse(ProjectBase):
    id: int

    class Config:
        from_attributes = True


# Project reorder schema
class ProjectReorderItem(BaseModel):
    id: int
    order: int


class ProjectReorderRequest(BaseModel):
    projects: List[ProjectReorderItem]


# Skill schemas
class SkillBase(BaseModel):
    category: str
    name: str
    proficiency: float = 0.0


class SkillResponse(SkillBase):
    id: int

    class Config:
        from_attributes = True


# Research schemas
class ResearchBase(BaseModel):
    title: str
    venue: Optional[str] = None
    year: Optional[int] = None
    status: Optional[str] = None
    link: Optional[str] = None


class ResearchResponse(ResearchBase):
    id: int

    class Config:
        from_attributes = True


# Experience schemas
class ExperienceBase(BaseModel):
    title: str
    organization: str
    period: str
    description: Optional[str] = None
    logo_url: Optional[str] = None


class ExperienceResponse(ExperienceBase):
    id: int

    class Config:
        from_attributes = True


# Certificate schemas
class CertificateBase(BaseModel):
    name: str
    issuer: Optional[str] = None
    date: Optional[str] = None
    file_path: Optional[str] = None


class CertificateResponse(CertificateBase):
    id: int

    class Config:
        from_attributes = True


# Chat schemas
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    response: str
    sources: List[str] = []


# Contact Message schemas
class ContactMessageBase(BaseModel):
    name: str = Field(..., max_length=100)
    email: str = Field(..., max_length=254)
    message: str = Field(..., max_length=5000)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid email address format")
        return v


class ContactMessageResponse(ContactMessageBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Document schemas
class DocumentBase(BaseModel):
    topic: Optional[str] = None


class DocumentResponse(BaseModel):
    id: int
    filename: str
    topic: Optional[str] = None
    original_name: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    chunk_count: int = 0

    class Config:
        from_attributes = True


# Admin Settings schemas
class AdminSettings(BaseModel):
    hf_model_id: Optional[str] = None
    hf_api_token: Optional[str] = None


# Contact Info schemas
class ContactInfoBase(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notification_emails: Optional[str] = None


class ContactInfoResponse(ContactInfoBase):
    id: int

    class Config:
        from_attributes = True
