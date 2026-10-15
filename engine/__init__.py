"""Tainted Graph Engine (Part A).

Provides graph client, query builder, generator, injector, and evaluation harness.
"""

from engine.config_loader import ConfigLoader, ConfigValidationError
from engine.prototype_queries import (
    GATE_PROTOTYPE_CYPHER,
    TRACE_PROTOTYPE_CYPHER,
    PrototypeQueryRunner,
)
from engine.generator import FoodGraphGenerator
from engine.injector import FaultInjector
from engine.query_builder import QueryBuilder
from engine.query_api_impl import QueryAPI
from engine.evaluation import EvaluationHarness, EvaluationReport, IncidentMetric

__all__ = [
    "ConfigLoader",
    "ConfigValidationError",
    "GATE_PROTOTYPE_CYPHER",
    "TRACE_PROTOTYPE_CYPHER",
    "PrototypeQueryRunner",
    "FoodGraphGenerator",
    "FaultInjector",
    "QueryBuilder",
    "QueryAPI",
    "EvaluationHarness",
    "EvaluationReport",
    "IncidentMetric",
]
