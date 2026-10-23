"""Runtime settings, read from environment variables once at startup."""
import os
import secrets
from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        # "demo" = header-based identity for local runs, "firebase" = verified Firebase ID tokens.
        self.auth_mode = os.getenv("AUTH_MODE", "demo").lower()
        # In demo mode the teacher view is protected by a PIN. If unset, a random one is generated.
        self.teacher_pin = os.getenv("TEACHER_PIN") or secrets.token_hex(3)
        self.teacher_pin_generated = not os.getenv("TEACHER_PIN")
        # Used to pseudonymize user ids in logs and storage.
        self.id_salt = os.getenv("ID_SALT") or secrets.token_hex(16)
        # Gemini: either an API key (AI Studio) or Vertex AI (set GOOGLE_GENAI_USE_VERTEXAI=true).
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")
        self.gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self.gcp_location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        # Limits.
        self.max_image_bytes = int(os.getenv("MAX_IMAGE_BYTES", str(4 * 1024 * 1024)))
        self.rate_per_minute = int(os.getenv("RATE_PER_MINUTE", "30"))
        self.allowed_origins = [o for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o]
