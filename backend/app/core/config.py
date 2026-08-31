import json
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "OilSpill Backend API"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "FastAPI Backend for Oil Spill Detection and Management System"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # OilTrace SAR+ML detection service (Satyam's module, deployed on Modal).
    # Docs: docs/OilTrace_Detection_API.md. Timeout covers cold start (~40s)
    # plus CPU inference (~20-60s per scene).
    ML_SERVICE_URL: str = "https://vscimatic999--oiltrace-detection-web.modal.run"
    ML_SERVICE_TIMEOUT: float = 300.0

    # ── Drift simulation (Ved's module) ─────────────────────────────────
    # Paths to NetCDF forcing files.  Relative paths are resolved from the
    # working directory; absolute paths are used as-is.
    DRIFT_FORCING_CURRENTS_PATH: str = "data/currents.nc"
    DRIFT_FORCING_WIND_PATH: str = "data/wind.nc"
    # Optional explicit landmask NetCDF (land_binary_mask variable). Leave
    # None in production: OpenOil's built-in global auto-landmask is used and
    # is live-verified working. Set a path only for environments where the
    # auto-landmask is unavailable (e.g. some local Windows setups).
    DRIFT_LANDMASK_PATH: str | None = None

    # OpenOil simulation parameters.
    DRIFT_PARTICLE_COUNT: int = 1000
    DRIFT_OIL_TYPE: str = "GENERIC BUNKER C"
    DRIFT_DEFAULT_DURATION_HOURS: int = 12

    # Time step for internal OpenDrift integration (minutes).
    DRIFT_TIMESTEP_MINUTES: int = 15
    # Interval between saved output frames (minutes).
    DRIFT_OUTPUT_INTERVAL_MINUTES: int = 60

    # KDE / source-region extraction parameters.
    DRIFT_KDE_GRID_RESOLUTION: int = 100
    # Grid margin in km beyond the particle extent.
    DRIFT_KDE_MARGIN_KM: float = 0.5
    # Highest-density region mass fraction (0–1).
    DRIFT_KDE_HDR_MASS_FRACTION: float = 0.95

    # CORS Configuration
    ALLOWED_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
