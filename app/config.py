import os

# Default to SQLite for local development so it works out-of-the-box without installing PostgreSQL.
# In Docker, docker-compose.yml sets DATABASE_URL to PostgreSQL.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./eve_healthcare.db",
)
SECRET_KEY = os.getenv("SECRET_KEY", "your-secure-secret-key-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
