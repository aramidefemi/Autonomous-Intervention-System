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
