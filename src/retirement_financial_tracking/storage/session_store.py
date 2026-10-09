from __future__ import annotations

from dataclasses import dataclass, field

from retirement_financial_tracking.domain.models import ForecastResult, HouseholdPlan


@dataclass
class SessionStore:
    plans: dict[str, HouseholdPlan] = field(default_factory=dict)
    forecasts: dict[str, ForecastResult] = field(default_factory=dict)

    def put_plan(self, plan: HouseholdPlan) -> None:
        self.plans[plan.plan_id] = plan

    def get_plan(self, plan_id: str) -> HouseholdPlan | None:
        return self.plans.get(plan_id)

    def put_forecast(self, forecast: ForecastResult) -> None:
        self.forecasts[forecast.plan_id] = forecast

    def get_forecast(self, plan_id: str) -> ForecastResult | None:
        return self.forecasts.get(plan_id)

