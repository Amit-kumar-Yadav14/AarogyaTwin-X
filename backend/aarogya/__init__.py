"""CPU-first synthetic prediction engine for AarogyaTwin-X.

The package intentionally contains no network or clinical-data integration.  The
pipeline creates a reproducible synthetic cohort and a reloadable artifact bundle;
``TwinEngine`` only reads that bundle for replay/inference.
"""

from .engine import TwinEngine
from .simulation import EVENT_DEFINITION, generate_cohort, event_label

__all__ = ["TwinEngine", "EVENT_DEFINITION", "generate_cohort", "event_label"]
