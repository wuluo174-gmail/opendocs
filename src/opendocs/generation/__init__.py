"""Document generation — summary, insights, templates, drafts."""

from opendocs.generation.draft_pipeline import GenerationPipeline
from opendocs.generation.models import Draft, InsightItem, SummaryResponse
from opendocs.generation.summary_pipeline import SummaryPipeline

__all__ = [
    "Draft",
    "GenerationPipeline",
    "InsightItem",
    "SummaryPipeline",
    "SummaryResponse",
]
