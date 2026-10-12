"""
agents/patent_specialist.py - Patent Specialist Agent (AutoDev Version 3.6)
Strictly 100% Python Standard Library. Zero external dependencies.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.communication_bus import CommunicationBus
from core.patent_generator import PatentApplication, PatentClaim
from core.research_lab import ResearchLab

logger = logging.getLogger("AutoDev.Research.PatentSpecialist")


class PatentSpecialistAgent:
    """
    Patent Specialist Agent - Protector of Intellectual Property & Inventions:
    - Analyzes technological breakthroughs for patentability and non-obviousness
    - Drafts formal patent specifications with independent and dependent claims
    - Expands the corporate patent portfolio and defends institutional discoveries
    """

    def __init__(
        self,
        name: str = "PatentSpecialist",
        lab: Optional[ResearchLab] = None,
        bus: Optional[CommunicationBus] = None,
    ) -> None:
        self.name = name
        self.lab = lab or ResearchLab()
        self.bus = bus
        self.authority_level = 3

        if self.bus:
            self.bus.register_entity(self.name)

    @property
    def role(self) -> str:
        return "Patent Specialist"

    def evaluate_patentability(
        self, novelty_score: float, non_obviousness_score: float, utility_score: float
    ) -> Dict[str, Any]:
        patentable = all(score >= 0.5 for score in (novelty_score, non_obviousness_score, utility_score))
        return {
            "is_patentable": patentable,
            "novelty_score": novelty_score,
            "non_obviousness_score": non_obviousness_score,
            "utility_score": utility_score,
            "recommendation": "PROCEED_TO_DRAFT" if patentable else "DO_NOT_FILE",
        }

    def draft_patent_claims(self, title: str, independent_elements: List[str]) -> Dict[str, Any]:
        from core.patent_generator import PatentClaimType

        application = self.lab.patent_generator.draft_patent(title=title, inventors=[self.name])
        for element in independent_elements:
            self.lab.patent_generator.add_claim(application.patent_id, PatentClaimType.INDEPENDENT, element)
        return application.to_dict()

    def assess_patentability(self, novelty_score: float, performance_gain_pct: float) -> Dict[str, Any]:
        """Evaluates statutory patentability criteria (novelty, non-obviousness, utility)."""
        is_novel = novelty_score >= 0.50
        is_non_obvious = performance_gain_pct >= 15.0
        is_patentable = is_novel and is_non_obvious

        return {
            "is_patentable": is_patentable,
            "novelty_score": novelty_score,
            "performance_gain_pct": performance_gain_pct,
            "recommendation": "PROCEED_TO_DRAFT" if is_patentable else "DO_NOT_FILE",
            "assessed_by": self.name,
        }

    def draft_patent_for_algorithm(
        self,
        algorithm_name: str,
        domain: str,
        inventors: List[str],
        spec_text: str,
        advantage_text: str,
    ) -> PatentApplication:
        """Drafts a complete patent specification for an algorithmic discovery."""
        return self.lab.patent_generator.synthesize_from_algorithm(
            algorithm_name=algorithm_name,
            inventors=inventors,
            algorithm_domain=domain,
            specification_text=spec_text,
            performance_gain_description=advantage_text,
        )
