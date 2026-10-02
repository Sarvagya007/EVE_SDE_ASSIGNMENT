import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    DateTime,
    Enum,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)


class DiagnosticCentre(Base):
    __tablename__ = "diagnostic_centres"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String, nullable=False)

    tests = relationship("CentreTestMapping", back_populates="centre")


class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    centres = relationship("CentreTestMapping", back_populates="test")


class CentreTestMapping(Base):
    __tablename__ = "centre_test_mappings"

    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("diagnostic_centres.id"), nullable=False)
    test_id = Column(Integer, ForeignKey("diagnostic_tests.id"), nullable=False)
    price = Column(Float, nullable=False)

    centre = relationship("DiagnosticCentre", back_populates="tests")
    test = relationship("DiagnosticTest", back_populates="centres")

    __table_args__ = (
        UniqueConstraint("centre_id", "test_id", name="uq_centre_test"),
    )


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    centre_id = Column(Integer, ForeignKey("diagnostic_centres.id"), nullable=False)
    test_id = Column(Integer, ForeignKey("diagnostic_tests.id"), nullable=False)
    appointment_time = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING, nullable=False)


class ProcessedWebhookEvent(Base):
    """Tracks received webhook IDs to enforce idempotency."""
    __tablename__ = "processed_webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, index=True, nullable=False)
    booking_id = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
