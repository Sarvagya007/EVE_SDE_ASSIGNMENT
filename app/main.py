from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app import models
from app.routers import auth_routes, centres, bookings, payments


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables automatically on startup
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Database initialization notice: {e}")
    yield


app = FastAPI(
    title="EVE Healthcare — Diagnostic Test Booking & Payment API",
    description=(
        "Backend service for diagnostic test bookings, mock payments, "
        "and idempotent webhook processing with robust edge-case handling."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth_routes.router)
app.include_router(centres.router)
app.include_router(bookings.router)
app.include_router(payments.router)


@app.get("/", tags=["Health"])
def root():
    return {
        "message": "Welcome to EVE Healthcare Booking API",
        "docs": "/docs",
        "status": "healthy",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
