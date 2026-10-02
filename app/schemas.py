from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CentreCreate(BaseModel):
    name: str
    location: str


class TestCreate(BaseModel):
    name: str
    price: float


class CentreTestMappingCreate(BaseModel):
    test_id: Optional[int] = None
    test_name: Optional[str] = None
    price: float


class BookingCreate(BaseModel):
    centre_id: int
    test_id: int
    appointment_time: datetime


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    centre_id: int
    test_id: int
    amount: float
    status: str
    appointment_time: datetime


class PaymentRequest(BaseModel):
    booking_id: int
    force_status: Optional[str] = None  # Optional: "SUCCESS" or "FAILED" for deterministic testing


class WebhookPayload(BaseModel):
    event_id: str
    booking_id: int
    payment_status: str  # "SUCCESS" or "FAILED"
