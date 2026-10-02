import os
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure test DB environment is configured
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, get_db
from app.main import app
from app import models

# In-memory SQLite for test execution
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()
    db_session = TestingSessionLocal(bind=connection)

    yield db_session

    db_session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client):
    # Create user and get token
    signup_res = client.post(
        "/auth/signup",
        json={"email": "alice@example.com", "password": "password123", "name": "Alice"},
    )
    assert signup_res.status_code == 201

    login_res = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_auth_headers(client):
    signup_res = client.post(
        "/auth/signup",
        json={"email": "bob@example.com", "password": "password123", "name": "Bob"},
    )
    assert signup_res.status_code == 201

    login_res = client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "password123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_setup(client):
    # Create a centre
    centre_res = client.post(
        "/centres/",
        json={"name": "Health First Labs", "location": "Bangalore Central"},
    )
    centre_id = centre_res.json()["id"]

    # Add a test
    test_res = client.post(
        f"/centres/{centre_id}/tests",
        json={"test_name": "Lipid Profile", "price": 850.0},
    )
    test_id = test_res.json()["test_id"]
    return {"centre_id": centre_id, "test_id": test_id, "price": 850.0}


# ==========================================
# 1. AUTHENTICATION TESTS
# ==========================================

def test_signup_success(client):
    res = client.post(
        "/auth/signup",
        json={"email": "newuser@example.com", "password": "password123", "name": "New User"},
    )
    assert res.status_code == 201
    assert res.json()["email"] == "newuser@example.com"
    assert "hashed_password" not in res.json()


def test_signup_duplicate_email(client):
    client.post(
        "/auth/signup",
        json={"email": "dup@example.com", "password": "password123", "name": "User 1"},
    )
    res = client.post(
        "/auth/signup",
        json={"email": "dup@example.com", "password": "password123", "name": "User 2"},
    )
    assert res.status_code == 409


def test_login_success(client):
    client.post(
        "/auth/signup",
        json={"email": "login@example.com", "password": "password123", "name": "Login User"},
    )
    res = client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "password123"},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_invalid_credentials(client):
    res = client.post(
        "/auth/login",
        json={"email": "wrong@example.com", "password": "wrongpassword"},
    )
    assert res.status_code == 401


def test_protected_route_without_token(client):
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    res = client.post(
        "/bookings/",
        json={"centre_id": 1, "test_id": 1, "appointment_time": future_time},
    )
    assert res.status_code == 401


# ==========================================
# 2. CENTRES & TESTS TESTS
# ==========================================

def test_list_centres_with_tests(client, test_setup):
    res = client.get("/centres/")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    centre = data[0]
    assert centre["id"] == test_setup["centre_id"]
    assert len(centre["available_tests"]) == 1
    assert centre["available_tests"][0]["test_name"] == "Lipid Profile"
    assert centre["available_tests"][0]["price"] == 850.0


def test_add_duplicate_test_to_centre(client, test_setup):
    res = client.post(
        f"/centres/{test_setup['centre_id']}/tests",
        json={"test_id": test_setup["test_id"], "price": 900.0},
    )
    assert res.status_code == 409


# ==========================================
# 3. BOOKING TESTS & EDGE CASES
# ==========================================

def test_create_booking_success(client, auth_headers, test_setup):
    future_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    res = client.post(
        "/bookings/",
        json={
            "centre_id": test_setup["centre_id"],
            "test_id": test_setup["test_id"],
            "appointment_time": future_time,
        },
        headers=auth_headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["amount"] == 850.0  # Price snapshot directly from database
    assert data["status"] == "PENDING"


def test_create_booking_past_date(client, auth_headers, test_setup):
    past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    res = client.post(
        "/bookings/",
        json={
            "centre_id": test_setup["centre_id"],
            "test_id": test_setup["test_id"],
            "appointment_time": past_time,
        },
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_create_booking_nonexistent_test(client, auth_headers, test_setup):
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    res = client.post(
        "/bookings/",
        json={
            "centre_id": test_setup["centre_id"],
            "test_id": 9999,
            "appointment_time": future_time,
        },
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_unauthorized_user_cannot_view_booking(client, auth_headers, other_auth_headers, test_setup):
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    booking_res = client.post(
        "/bookings/",
        json={
            "centre_id": test_setup["centre_id"],
            "test_id": test_setup["test_id"],
            "appointment_time": future_time,
        },
        headers=auth_headers,
    )
    booking_id = booking_res.json()["id"]

    # Bob attempts to view Alice's booking
    res = client.get(f"/bookings/{booking_id}", headers=other_auth_headers)
    assert res.status_code == 403


def test_cancel_booking(client, auth_headers, test_setup):
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    booking_res = client.post(
        "/bookings/",
        json={
            "centre_id": test_setup["centre_id"],
            "test_id": test_setup["test_id"],
            "appointment_time": future_time,
        },
        headers=auth_headers,
    )
    booking_id = booking_res.json()["id"]

    # Cancel booking
    cancel_res = client.patch(f"/bookings/{booking_id}/cancel", headers=auth_headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Cancelling again should fail with 409
    cancel_again = client.patch(f"/bookings/{booking_id}/cancel", headers=auth_headers)
    assert cancel_again.status_code == 409


# ==========================================
# 4. PAYMENT & WEBHOOK TESTS
# ==========================================

def test_mock_payment_success(client, auth_headers, test_setup, db):
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    b_res = client.post(
        "/bookings/",
        json={
            "centre_id": test_setup["centre_id"],
            "test_id": test_setup["test_id"],
            "appointment_time": future_time,
        },
        headers=auth_headers,
    )
    booking_id = b_res.json()["id"]

    pay_res = client.post(
        "/payments/",
        json={"booking_id": booking_id, "force_status": "SUCCESS"},
        headers=auth_headers,
    )
    assert pay_res.status_code == 200
    assert pay_res.json()["payment_result"] == "SUCCESS"
    assert pay_res.json()["booking_status"] == "CONFIRMED"


def test_double_payment_rejected(client, auth_headers, test_setup):
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    b_res = client.post(
        "/bookings/",
        json={
            "centre_id": test_setup["centre_id"],
            "test_id": test_setup["test_id"],
            "appointment_time": future_time,
        },
        headers=auth_headers,
    )
    booking_id = b_res.json()["id"]

    # Pay once
    client.post(
        "/payments/",
        json={"booking_id": booking_id, "force_status": "SUCCESS"},
        headers=auth_headers,
    )

    # Pay again
    second_pay = client.post(
        "/payments/",
        json={"booking_id": booking_id, "force_status": "SUCCESS"},
        headers=auth_headers,
    )
    assert second_pay.status_code == 409


def test_webhook_idempotency_triple_delivery(client, auth_headers, test_setup, db):
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    b_res = client.post(
        "/bookings/",
        json={
            "centre_id": test_setup["centre_id"],
            "test_id": test_setup["test_id"],
            "appointment_time": future_time,
        },
        headers=auth_headers,
    )
    booking_id = b_res.json()["id"]

    webhook_payload = {
        "event_id": "evt_idempotent_test_100",
        "booking_id": booking_id,
        "payment_status": "SUCCESS",
    }

    # 1st Webhook delivery -> Processed
    res1 = client.post("/payments/webhook/", json=webhook_payload)
    assert res1.status_code == 200
    assert res1.json()["status"] == "success"
    assert res1.json()["new_status"] == "CONFIRMED"

    # 2nd Webhook delivery -> Ignored (Idempotent)
    res2 = client.post("/payments/webhook/", json=webhook_payload)
    assert res2.status_code == 200
    assert res2.json()["status"] == "ignored"

    # 3rd Webhook delivery -> Ignored (Idempotent)
    res3 = client.post("/payments/webhook/", json=webhook_payload)
    assert res3.status_code == 200
    assert res3.json()["status"] == "ignored"

    # Verify database state has exactly 1 event and status remains CONFIRMED
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    assert booking.status == models.BookingStatus.CONFIRMED

    events = db.query(models.ProcessedWebhookEvent).filter_by(event_id="evt_idempotent_test_100").all()
    assert len(events) == 1


def test_webhook_terminal_state_protected(client, auth_headers, test_setup, db):
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    b_res = client.post(
        "/bookings/",
        json={
            "centre_id": test_setup["centre_id"],
            "test_id": test_setup["test_id"],
            "appointment_time": future_time,
        },
        headers=auth_headers,
    )
    booking_id = b_res.json()["id"]

    # Cancel booking
    client.patch(f"/bookings/{booking_id}/cancel", headers=auth_headers)

    # Late webhook arrives with SUCCESS
    res = client.post(
        "/payments/webhook/",
        json={
            "event_id": "evt_late_arrival",
            "booking_id": booking_id,
            "payment_status": "SUCCESS",
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"

    # Booking must remain CANCELLED
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    assert booking.status == models.BookingStatus.CANCELLED
