from typing import Optional
from pydantic import BaseModel, Field


class AirQualitySummaryInput(BaseModel):
    aqi: Optional[int] = Field(default=None, ge=1, le=5)
    sentiment_label: Optional[str] = None
    co: Optional[float] = None
    pm2_5: Optional[float] = None
    aqi_rolling_7d: Optional[float] = None
    pm2_5_rolling_7d: Optional[float] = None


class AirQualitySummaryOutput(BaseModel):
    llm_response: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500
    )