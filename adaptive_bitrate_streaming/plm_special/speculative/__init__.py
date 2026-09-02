"""Speculative inference helpers for adaptive bitrate streaming."""

from plm_special.speculative.mpc_draft import (
    DRAFTERS,
    BaseDraftGenerator,
    HybridDraftGenerator,
    MPCDraftRollout,
    RepeatLastDraftGenerator,
    RobustMPCDraftGenerator,
    build_drafter,
    load_video_sizes,
    mpc_best_sequence,
    resolve_state,
    throughput_coefficient_of_variation,
)
from plm_special.speculative.acceptance import (
    AcceptancePlan,
    ObservationValidation,
    build_acceptance_plan,
    validate_speculative_observation,
)

__all__ = [
    'AcceptancePlan', 'BaseDraftGenerator', 'DRAFTERS', 'HybridDraftGenerator',
    'MPCDraftRollout', 'ObservationValidation', 'RepeatLastDraftGenerator',
    'RobustMPCDraftGenerator', 'build_acceptance_plan', 'build_drafter',
    'load_video_sizes', 'mpc_best_sequence', 'resolve_state',
    'throughput_coefficient_of_variation', 'validate_speculative_observation',
]
