import random
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.auth import get_current_user

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/")
def simulate_payment(
    payload: schemas.PaymentRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.query(models.Booking).filter(models.Booking.id == payload.booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found.",
        )

    # Authorization check
    if booking.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized access to booking.",
        )

    # State check: Only PENDING bookings can be paid
    if booking.status != models.BookingStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot pay for booking with status '{booking.status}'.",
        )

    # Mock payment logic: randomly succeed (80%) or fail (20%), or use deterministic force_status
    if payload.force_status in ("SUCCESS", "FAILED"):
        outcome = payload.force_status
    else:
        outcome = "SUCCESS" if random.random() < 0.8 else "FAILED"

    booking.status = (
        models.BookingStatus.CONFIRMED if outcome == "SUCCESS" else models.BookingStatus.FAILED
    )
    db.commit()

    return {
        "booking_id": booking.id,
        "payment_result": outcome,
        "booking_status": booking.status,
    }


@router.post("/webhook/")
def payment_webhook(payload: schemas.WebhookPayload, db: Session = Depends(get_db)):
    """
    Idempotent Webhook:
    1. Checks if the event_id has already been processed.
    2. If yes, returns HTTP 200 immediately without re-modifying database state.
    3. If no, validates booking and terminal state before applying updates.
    4. Logs event_id inside an atomic transaction to guarantee idempotency.
    """
    # 1. Idempotency Check
    existing_event = (
        db.query(models.ProcessedWebhookEvent)
        .filter_by(event_id=payload.event_id)
        .first()
    )
    if existing_event:
        return {"status": "ignored", "message": "Event already processed previously"}

    # 2. Validate Booking
    booking = db.query(models.Booking).filter(models.Booking.id == payload.booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target booking does not exist.",
        )

    # 3. Terminal State Guard: Do not regress CONFIRMED or CANCELLED bookings
    if booking.status in (models.BookingStatus.CONFIRMED, models.BookingStatus.CANCELLED):
        # Save event to preserve idempotency on future retries
        event_log = models.ProcessedWebhookEvent(
            event_id=payload.event_id,
            booking_id=payload.booking_id,
            status=payload.payment_status,
        )
        db.add(event_log)
        db.commit()
        return {
            "status": "ignored",
            "message": f"Booking is already in terminal state '{booking.status}'",
            "booking_id": booking.id,
            "current_status": booking.status,
        }

    # 4. Update Status
    if payload.payment_status == "SUCCESS":
        booking.status = models.BookingStatus.CONFIRMED
    else:
        booking.status = models.BookingStatus.FAILED

    # 5. Save Event ID to ensure idempotency
    event_log = models.ProcessedWebhookEvent(
        event_id=payload.event_id,
        booking_id=payload.booking_id,
        status=payload.payment_status,
    )
    db.add(event_log)
    db.commit()

    return {
        "status": "success",
        "booking_id": booking.id,
        "new_status": booking.status,
    }
