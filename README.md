# EVE Healthcare — Diagnostic Test Booking & Payment Backend

Backend service for diagnostic test bookings, mock payment processing, and idempotent payment webhooks built with **FastAPI**, **PostgreSQL / SQLite**, **SQLAlchemy ORM**, **Pydantic v2**, and **Docker**.

---

## 🚀 How to Run the Project (Quick Start)

### Option A: Using Docker Compose (Recommended for Evaluators)

Run the entire stack (PostgreSQL 16 + FastAPI server) with a single command:

```bash
docker-compose up --build
```

- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

### Option B: Running Locally (Python 3.11 / 3.12)

The project includes an automatic zero-config SQLite fallback for instant local evaluation without requiring a PostgreSQL server installation:

1. **Clone and enter the directory**:
   ```bash
   cd eve-healthcare-backend
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Windows PowerShell:
   python -m venv venv
   .\venv\Scripts\activate

   # macOS / Linux:
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run automated test suite (16 tests)**:
   ```bash
   pytest -v
   ```

5. **Start the API server**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   Open **[http://localhost:8000/docs](http://localhost:8000/docs)** in your browser.

---

## 📌 Problem Understanding (Summary)

Diagnostic medical platforms connect patients with healthcare providers, requiring strict guarantees around financial data integrity and scheduling:
1. **Catalog Flexibility**: Different diagnostic centres offer different tests at different price points (e.g. a CBC test costs ₹400 at Centre A, but ₹650 at Centre B).
2. **Financial Snapshotting**: Prices may fluctuate over time, but historical bookings must permanently preserve the agreed price agreed upon at booking creation.
3. **Webhook Idempotency**: Payment gateways (Razorpay, Stripe, etc.) operate over asynchronous networks and frequently retry webhook notifications. The backend must guarantee that receiving the exact same webhook event multiple times produces the exact same state without double-charging or corrupting booking statuses.
4. **State Machine Integrity**: A booking progresses through `PENDING`, `CONFIRMED`, `FAILED`, and `CANCELLED`. Once terminal (`CONFIRMED` or `CANCELLED`), delayed webhook failures or re-payments must be strictly guarded against.

---

## 💡 Important Assumptions Made

1. **Price Snapshotting**: The booking amount is pulled directly from `centre_test_mappings` in the database at the time of creation. The client cannot send an arbitrary `amount` in `POST /bookings/`, preventing price tampering.
2. **Role Permissions**: For the scope of this assignment, any authenticated user can register a diagnostic centre and add tests. In production, this would be restricted to an `ADMIN` role.
3. **Resource Ownership & Privacy**: Attempting to view, pay for, or cancel a booking belonging to another user returns `HTTP 403 FORBIDDEN` (or `404 NOT FOUND`) to avoid data leakage and prevent ID enumeration.
4. **Cancellation Rules**: As per the live-coding challenge, a user can cancel a booking only if it is currently `PENDING` or `CONFIRMED`. Attempting to cancel an already `CANCELLED` or `FAILED` booking returns `HTTP 409 CONFLICT`.
5. **Idempotency Key**: Each webhook notification supplies a unique `event_id`. The backend logs this ID in `processed_webhook_events` within an atomic transaction to ensure deduplication.

---

## 🏗️ Proposed Solution & Architecture

The codebase follows a modular, decoupled architecture:

```
eve-healthcare-backend/
├── app/
│   ├── main.py              # Application entrypoint, CORS middleware, lifespan table creation
│   ├── config.py            # Environment configuration & DB URL resolution
│   ├── database.py          # SQLAlchemy engine, session maker, get_db dependency
│   ├── models.py            # Relational database models (Users, Centres, Tests, Mappings, Bookings, WebhookEvents)
│   ├── schemas.py           # Pydantic validation schemas
│   ├── auth.py              # Native bcrypt hashing, JWT issuance & HTTPBearer dependency
│   └── routers/
│       ├── auth_routes.py   # Signup and login endpoints
│       ├── centres.py       # Diagnostic centres & tests catalog endpoints
│       ├── bookings.py      # Booking creation, retrieval, and cancellation
│       └── payments.py      # Mock payment simulation & idempotent webhook handler
├── tests/
│   └── test_api.py          # Pytest integration tests with in-memory SQLite isolation
├── Dockerfile               # Multi-stage container build
├── docker-compose.yml       # Production-ready PostgreSQL 16 + API composition
└── requirements.txt         # Pinned production dependencies
```

- **Dual-Database Support**: Runs on PostgreSQL 16 inside Docker, and seamlessly defaults to SQLite for local development and lightning-fast unit tests.
- **FastAPI + Pydantic v2**: Strict request/response validation, auto-generated OpenAPI documentation, and native typing.
- **Security**: Native bcrypt password hashing (with 72-byte safe handling) and signed HMAC-SHA256 JWT bearer tokens.

---

## 🗄️ Database Schema Design

```
┌──────────────────┐               ┌──────────────────┐
│      users       │               │diagnostic_centres│
├──────────────────┤               ├──────────────────┤
│ id (PK)          │               │ id (PK)          │
│ email (UQ, IDX)  │               │ name             │
│ hashed_password  │               │ location         │
│ name             │               └─────────┬────────┘
└────────┬─────────┘                         │ 1
         │ 1                                 │
         │                                   │ *
         │                         ┌─────────┴────────┐        ┌──────────────────┐
         │                         │centre_test_map...│ *    1 │ diagnostic_tests │
         │                         ├──────────────────┼────────┤──────────────────┤
         │                         │ id (PK)          │        │ id (PK)          │
         │                         │ centre_id (FK)   │        │ name             │
         │                         │ test_id (FK)     │        └──────────────────┘
         │                         │ price (FLOAT)    │
         │                         │ UQ(centre, test) │
         │                         └─────────┬────────┘
         │ *                                 │ 1
         ▼                                   ▼ *
┌─────────────────────────────────────────────────────┐
│                      bookings                       │
├─────────────────────────────────────────────────────┤
│ id (PK)                                             │
│ user_id (FK -> users.id, IDX)                       │
│ centre_id (FK -> diagnostic_centres.id)             │
│ test_id (FK -> diagnostic_tests.id)                 │
│ appointment_time (DATETIME)                         │
│ amount (FLOAT)  <-- Price Snapshot                  │
│ status (ENUM: PENDING, CONFIRMED, FAILED, CANCELLED)│
└─────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────┐
│   processed_webhook_events  │
├─────────────────────────────┤
│ id (PK)                     │
│ event_id (UQ, IDX)          │ <-- Unique Idempotency Key
│ booking_id (INT)            │
│ status (VARCHAR)            │
│ received_at (DATETIME)      │
└─────────────────────────────┘
```

---

## 📡 API Endpoints & Example Requests

| Method | Endpoint | Auth | Purpose |
|---|---|:---:|---|
| `POST` | `/auth/signup` | No | Register user (`email`, `password`, `name`) |
| `POST` | `/auth/login` | No | Authenticate & retrieve JWT access token |
| `GET` | `/centres/` | No | List diagnostic centres & offered tests with prices |
| `POST` | `/centres/` | Yes | Create a new diagnostic centre |
| `POST` | `/centres/{id}/tests` | Yes | Associate a test & price with a centre |
| `POST` | `/bookings/` | Yes | Create a diagnostic test booking (`PENDING`) |
| `GET` | `/bookings/` | Yes | Retrieve authenticated user's bookings |
| `GET` | `/bookings/{id}` | Yes | Retrieve single booking detail |
| `PATCH` | `/bookings/{id}/cancel` | Yes | Cancel booking (`PENDING` or `CONFIRMED` only) |
| `POST` | `/payments/` | Yes | Simulate payment outcome (`SUCCESS`/`FAILED`) |
| `POST` | `/payments/webhook/` | No/Provider | Idempotent webhook receiver for payment gateway |

---

### Example cURL Commands

#### 1. Register User
```bash
curl -X POST "http://localhost:8000/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"email": "patient@example.com", "password": "password123", "name": "Jane Doe"}'
```

#### 2. Login
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "patient@example.com", "password": "password123"}'
```

#### 3. Create Diagnostic Centre
```bash
curl -X POST "http://localhost:8000/centres/" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Apollo Clinic", "location": "Indiranagar, Bangalore"}'
```

#### 4. Add Test with Price
```bash
curl -X POST "http://localhost:8000/centres/1/tests" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"test_name": "Complete Blood Count (CBC)", "price": 499.0}'
```

#### 5. Book Test
```bash
curl -X POST "http://localhost:8000/bookings/" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "centre_id": 1,
    "test_id": 1,
    "appointment_time": "2026-11-20T10:00:00Z"
  }'
```

#### 6. Cancel Booking
```bash
curl -X PATCH "http://localhost:8000/bookings/1/cancel" \
  -H "Authorization: Bearer <TOKEN>"
```

#### 7. Mock Payment Simulation
```bash
curl -X POST "http://localhost:8000/payments/" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"booking_id": 1, "force_status": "SUCCESS"}'
```

#### 8. Idempotent Payment Webhook
```bash
curl -X POST "http://localhost:8000/payments/webhook/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt_gateway_998877",
    "booking_id": 1,
    "payment_status": "SUCCESS"
  }'
```

---

## 🛡️ Edge Cases Handled (15% Evaluation Criteria)

1. **Repeated Webhooks (Idempotency)**:
   - Evaluated by checking `event_id` in `processed_webhook_events`.
   - If an event has already been recorded, returns `HTTP 200` with `{"status": "ignored"}` immediately without modifying database state.
   - Verified by an automated test simulating 3 duplicate consecutive deliveries (`test_webhook_idempotency_triple_delivery`).
2. **Price Manipulation Guard**:
   - `amount` is never accepted in request payloads. The backend queries `centre_test_mappings` in the database to lock in the verified price.
3. **Unauthorized Resource Access**:
   - Users cannot view, pay for, or cancel another user's booking (`HTTP 403 FORBIDDEN`).
4. **Terminal State Protection**:
   - Once a booking reaches `CONFIRMED` or `CANCELLED`, a delayed `FAILED` webhook is logged for idempotency, but the booking status is preserved.
5. **Past Appointment Validation**:
   - Attempting to book an appointment with a past timestamp is rejected with `HTTP 422 UNPROCESSABLE ENTITY`.
6. **Double Payment Prevention**:
   - Attempting to pay for an already confirmed, cancelled, or failed booking returns `HTTP 409 CONFLICT`.

---

## 🔮 What I Would Improve With More Time

1. **Redis Caching**: Cache `GET /centres/` and test catalog responses in Redis with cache invalidation when centres or tests are added.
2. **Celery / Background Workers**: Offload heavy notification pipelines (SMS/email booking confirmations) to asynchronous Celery workers.
3. **Rate Limiting**: Protect `/auth/login` and `/payments/` endpoints against brute-force attacks using Redis-backed rate limiting (`slowapi`).
4. **Optimistic Locking**: Add a `version_id` column to `bookings` to prevent concurrency collisions when two operations attempt to update a booking simultaneously.
