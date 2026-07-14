from pydantic import BaseModel, ConfigDict, Field

from crypto_alert_v2.domain.models import Symbol


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Symbol
    horizon: str = Field(min_length=1, max_length=32)
    query_text: str = Field(min_length=1, max_length=2000)
    notify: bool = False
