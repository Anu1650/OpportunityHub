"""Request/response schemas.

Deliberately permissive on email (plain str, not EmailStr) so we do not pull
in email-validator -- a 4-hour build does not need that failure mode.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Category = Literal[
    "internship",
    "hackathon",
    "scholarship",
    "course",
    "certification",
    "competition",
    "workshop",
]
Mode = Literal["remote", "onsite", "hybrid"]


class StudentIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=120)
    university: str = ""
    year: str = ""
    degree: str = ""
    skills: List[str] = []
    interests: List[str] = []
    categories: List[str] = []


class Student(StudentIn):
    id: str
    createdAt: Optional[str] = None


class OpportunityIn(BaseModel):
    title: str
    org: str
    category: str
    description: str = ""
    tags: List[str] = []
    mode: str = "remote"
    eligibility: str = ""
    deadline: Optional[str] = None
    applyUrl: str = ""
    featured: bool = False


class Opportunity(OpportunityIn):
    id: str
    score: Optional[int] = None
    matchedSkills: List[str] = []
    matchedInterests: List[str] = []
    reasons: List[str] = []
    saved: bool = False
    daysLeft: Optional[int] = None


class BookmarkIn(BaseModel):
    studentId: str
    opportunityId: str


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class VerifyOtpIn(BaseModel):
    email: str
    code: str = Field(min_length=4, max_length=10)


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


class ProfileUpdateIn(BaseModel):
    university: str = ""
    year: str = ""
    degree: str = ""
    skills: List[str] = []
    interests: List[str] = []
    categories: List[str] = []
