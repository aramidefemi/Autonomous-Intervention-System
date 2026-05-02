from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_port: int = Field(default=8000, alias="APP_PORT")
    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    mongo_database: str = Field(default="watchtower", alias="MONGO_DATABASE")
    aws_endpoint_url: str | None = Field(default=None, alias="AWS_ENDPOINT_URL")
    aws_region: str = Field(default="eu-west-1", alias="AWS_REGION")
    aws_access_key_id: str = Field(default="test", alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="test", alias="AWS_SECRET_ACCESS_KEY")
    sqs_ingress_queue_name: str = Field(
        default="watchtower-ingress",
        alias="SQS_INGRESS_QUEUE_NAME",
    )
    sqs_dlq_queue_name: str = Field(default="watchtower-ingress-dlq", alias="SQS_DLQ_QUEUE_NAME")
    queue_ingress: bool = Field(default=False, alias="QUEUE_INGRESS")
    sqs_visibility_timeout: int = Field(default=30, ge=1, le=43200, alias="SQS_VISIBILITY_TIMEOUT")
    sqs_wait_time_seconds: int = Field(default=1, ge=0, le=20, alias="SQS_WAIT_TIME_SECONDS")
    sqs_max_receive_before_dlq: int = Field(
        default=5,
        ge=1,
        le=1000,
        alias="SQS_MAX_RECEIVE_BEFORE_DLQ",
    )
    intervention_cooldown_seconds: int = Field(
        default=300,
        ge=0,
        le=86400,
        alias="INTERVENTION_COOLDOWN_SECONDS",
    )
    # One extra INFO line per /v1/events (delivery, trace, type, idem) for terminal demos
    event_trace_log: bool = Field(default=False, alias="AIS_EVENT_TRACE_LOG")
    # NVIDIA NIM (OpenAI-compatible); optional — watchtower uses rules when unset
    nvidia_api_key: str | None = Field(default=None, alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        alias="NVIDIA_BASE_URL",
    )
    nvidia_model: str = Field(
        default="nvidia/nemotron-3-super-120b-a12b",
        alias="NVIDIA_MODEL",
    )
    nvidia_temperature: float = Field(default=1.0, ge=0.0, le=2.0, alias="NVIDIA_TEMPERATURE")
    nvidia_top_p: float = Field(default=0.95, ge=0.0, le=1.0, alias="NVIDIA_TOP_P")
    nvidia_max_tokens: int = Field(default=16384, ge=1, le=131072, alias="NVIDIA_MAX_TOKENS")
    nvidia_reasoning_budget: int = Field(
        default=16384,
        ge=0,
        le=131072,
        alias="NVIDIA_REASONING_BUDGET",
    )
    nvidia_enable_thinking: bool = Field(default=True, alias="NVIDIA_ENABLE_THINKING")
    # LiveKit Cloud: optional WebRTC sim. Unset disables /v1/voice/simulate/*
    livekit_url: str | None = Field(default=None, alias="LIVEKIT_URL")
    livekit_api_key: str | None = Field(default=None, alias="LIVEKIT_API_KEY")
    livekit_api_secret: str | None = Field(default=None, alias="LIVEKIT_API_SECRET")
    # ElevenLabs TTS for /v1/voice/simulate/ui when set (otherwise browser speechSynthesis)
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(default=None, alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = Field(
        default="eleven_turbo_v2_5",
        alias="ELEVENLABS_MODEL_ID",
    )

    @field_validator("app_port")
    @classmethod
    def port_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            msg = "APP_PORT must be between 1 and 65535"
            raise ValueError(msg)
        return v

    @field_validator("mongo_database")
    @classmethod
    def mongo_db_non_empty(cls, v: str) -> str:
        if not v.strip():
            msg = "MONGO_DATABASE must not be empty"
            raise ValueError(msg)
        return v

    @field_validator("nvidia_api_key", mode="before")
    @classmethod
    def nvidia_key_empty(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip() or None

    @field_validator("livekit_url", mode="before")
    @classmethod
    def livekit_url_empty(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip() or None

    @field_validator("livekit_api_key", mode="before")
    @classmethod
    def livekit_key_empty(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip() or None

    @field_validator("livekit_api_secret", mode="before")
    @classmethod
    def livekit_secret_empty(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip() or None

    @field_validator("elevenlabs_api_key", mode="before")
    @classmethod
    def elevenlabs_key_empty(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip() or None

    @field_validator("elevenlabs_voice_id", mode="before")
    @classmethod
    def elevenlabs_voice_empty(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip() or None

    @field_validator("event_trace_log", mode="before")
    @classmethod
    def event_trace_log_truthy(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if v is None or v == "":
            return False
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("mongo_uri")
    @classmethod
    def mongo_scheme(cls, v: str) -> str:
        if not v:
            msg = "MONGO_URI must not be empty"
            raise ValueError(msg)
        if not (v.startswith("mongodb://") or v.startswith("mongodb+srv://")):
            msg = "MONGO_URI must start with mongodb:// or mongodb+srv://"
            raise ValueError(msg)
        return v

    @field_validator("aws_region")
    @classmethod
    def region_non_empty(cls, v: str) -> str:
        if not v.strip():
            msg = "AWS_REGION must not be empty"
            raise ValueError(msg)
        return v

    @field_validator("nvidia_base_url")
    @classmethod
    def nvidia_https(cls, v: str) -> str:
        if not v.startswith("https://"):
            msg = "NVIDIA_BASE_URL must be an https URL"
            raise ValueError(msg)
        return v.rstrip("/")

    @field_validator("aws_endpoint_url")
    @classmethod
    def endpoint_if_present(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            msg = "AWS_ENDPOINT_URL must be an http(s) URL when set"
            raise ValueError(msg)
        return v.rstrip("/")

    @model_validator(mode="after")
    def localstack_keys_when_endpoint(self) -> "Settings":
        if self.aws_endpoint_url and (not self.aws_access_key_id or not self.aws_secret_access_key):
            msg = (
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required "
                "when AWS_ENDPOINT_URL is set"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def queue_ingress_requires_endpoint(self) -> "Settings":
        if self.queue_ingress and not self.aws_endpoint_url:
            msg = "QUEUE_INGRESS requires AWS_ENDPOINT_URL"
            raise ValueError(msg)
        return self
