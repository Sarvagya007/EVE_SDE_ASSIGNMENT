from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.auth import get_current_user

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post("/", response_model=schemas.BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: schemas.BookingCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify appointment is in the future
    app_time = payload.appointment_time
    if app_time.tzinfo is None:
        app_time = app_time.replace(tzinfo=timezone.utc)

    if app_time <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Appointment time must be in the future.",
        )

    # Verify that the test is available at the selected centre
    mapping = db.query(models.CentreTestMapping).filter_by(
        centre_id=payload.centre_id,
        test_id=payload.test_id,
    ).first()

    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested test is not offered at this diagnostic centre.",
        )

    # Snapshot the price directly from the database mapping (never trust client price)
    booking = models.Booking(
        user_id=current_user.id,
        centre_id=payload.centre_id,
        test_id=payload.test_id,
        appointment_time=payload.appointment_time,
        amount=mapping.price,
        status=models.BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/", response_model=List[schemas.BookingResponse])
def list_my_bookings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve all bookings belonging to the authenticated user."""
    return db.query(models.Booking).filter(models.Booking.user_id == current_user.id).all()


@router.get("/{booking_id}", response_model=schemas.BookingResponse)
def get_booking(
    booking_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found.",
        )
    if booking.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized access to booking.",
        )
    return booking


@router.patch("/{booking_id}/cancel", response_model=schemas.BookingResponse)
@router.post("/{booking_id}/cancel", response_model=schemas.BookingResponse)
def cancel_booking(
    booking_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cancel a booking if it belongs to current_user and is in PENDING or CONFIRMED status.
    """
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found.",
        )
    if booking.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized access to booking.",
        )
    if booking.status not in (models.BookingStatus.PENDING, models.BookingStatus.CONFIRMED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel booking with status '{booking.status}'.",
        )

    booking.status = models.BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    return booking
