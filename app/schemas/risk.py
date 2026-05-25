from pydantic import BaseModel


class RiskCheckRequest(BaseModel):
    elder_id: str
    drugs: list[str] = []
    foods: list[str] = []
    context: str | None = None


class RiskAlert(BaseModel):
    type: str          # drug_drug / drug_food / food_allergy / disease_related
    severity: str      # high / medium / low
    message: str
    source: str        # DDInter / model_assisted / profile


class RiskCheckResponse(BaseModel):
    risk_level: str    # red / yellow / green
    alerts: list[RiskAlert]
    suggestion: str
