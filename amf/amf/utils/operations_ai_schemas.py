# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from typing import List, Literal

from pydantic import BaseModel, Field


class StrictModel(BaseModel):
    class Config:
        extra = "forbid"


class Evidence(StrictModel):
    source_path: str = Field(
        ...,
        description="Exact JSON path in the supplied KPI snapshot.",
    )
    value: str = Field(
        ...,
        description="Human-readable value found at source_path.",
    )


class OperationsInsight(StrictModel):
    category: Literal[
        "Delivery",
        "Machining",
        "Shipping",
        "Procurement",
        "Cross-KPI",
        "Data Quality",
    ]
    severity: Literal["Critical", "High", "Medium", "Low"]
    finding_type: Literal["Confirmed", "Hypothesis"]
    title_en: str
    title_fr: str
    finding_en: str
    finding_fr: str
    operational_impact_en: str
    operational_impact_fr: str
    recommendation_en: str
    recommendation_fr: str
    confidence: float = Field(..., ge=0, le=1)
    evidence: List[Evidence] = Field(..., min_length=1)


class OperationsInsights(StrictModel):
    executive_summary_en: str
    executive_summary_fr: str
    insights: List[OperationsInsight]
    management_questions_en: List[str]
    management_questions_fr: List[str]
    assumptions: List[str]
    data_quality_warnings: List[str]


def model_to_dict(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()
