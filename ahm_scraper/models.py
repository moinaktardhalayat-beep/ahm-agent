"""Canonical AHM project record. Mirrors the Phase 0 schema from the handover."""
from dataclasses import dataclass, field, asdict
from datetime import date


@dataclass
class ProjectRecord:
    project_name: str
    location: str = ""
    sector: str = ""
    owner_developer: str = ""
    operator_brand: str = ""
    architect_consultant: str = ""
    main_contractor_pm: str = ""
    project_stage: str = ""
    stage_evidence_date: str = ""
    total_project_value: str = ""
    potential_ahm_package_value: str = ""
    facade_acp_scope_evidence: str = ""
    package_award_status: str = "UNKNOWN"
    decision_maker_name_role: str = ""
    contact_details_source: str = ""
    referral_path: str = ""
    last_contact_date: str = ""
    what_was_learned: str = ""
    next_action: str = "Verify stage and package status"
    next_action_owner: str = "User"
    next_action_due: str = ""
    confidence_label: str = "Inference"
    lead_stage: str = "Research candidate"
    source_url: str = ""
    scraped_at: str = field(default_factory=lambda: date.today().isoformat())

    def to_row(self):
        return asdict(self)
