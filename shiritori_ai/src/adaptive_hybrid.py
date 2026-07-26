"""Position-adaptive edge-search hybrids for large shiritori dictionaries."""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import asdict, dataclass, replace
from typing import Any, Sequence, TypeVar

from agents import (
    DEFAULT_BEAM_WIDTHS,
    DEFAULT_EVALUATION_CONFIG,
    DEFAULT_TIME_LIMIT_SEC,
    LOSS_SCORE,
    WIN_SCORE,
    AlphaBetaAgent,
    BeamAlphaBetaAgent,
    BeamPVSAgent,
    EdgeMoveDecision,
    EvaluationConfig,
    SearchStats,
    SearchTimeout,
    CandidateEvaluation,
    _safe_edge_fallback,
    check_deadline,
    edge_candidate_analysis,
    edge_is_terminal,
)
from exact_solver import AnalysisLimitExceeded, ShiritoriSolver
from runtime_dictionary import EdgeDictionary
from runtime_state import AIEdgeState


T = TypeVar("T")


@dataclass(frozen=True)
class AdaptiveHybridConfig:
    """Tunable thresholds shared by the adaptive hybrids.

    Root candidate counts in the D10000 follow-up had median 24, p90 41 and
    p95 47.  The defaults therefore keep all very small nodes, use a wide
    beam through the median region and narrow only the upper tail.
    """

    branch_switch_threshold: int = 12
    no_prune_threshold: int = 6
    medium_branch_threshold: int = 24
    high_branch_threshold: int = 48
    medium_beam_width: int = 12
    high_beam_width: int = 8
    very_high_beam_width: int = 6
    ply_width_caps: tuple[int, ...] = DEFAULT_BEAM_WIDTHS
    iterative_start_depth: int = 7
    pvs_research_rate_threshold: float = 0.04
    pvs_time_growth_limit: float = 3.0
    next_depth_safety_ratio: float = 0.80
    exact_max_reachable_words: int = 32
    exact_max_edge_types: int = 18
    exact_max_vertices: int = 12
    exact_max_state_estimate: int = 200_000
    exact_max_states: int = 200_000
    exact_time_fraction: float = 0.20
    exact_time_cap_sec: float = 0.20
    exact_normal_time_reserve_sec: float = 0.10
    frontier_exact_min_legal_edge_types: int = 2
    exact_event_log_limit: int = 200
    score_gap_wide_threshold: float = 4.0
    score_gap_narrow_threshold: float = 16.0
    score_gap_min_widths: tuple[int, ...] = (8, 5, 3, 2)
    score_gap_max_widths: tuple[int, ...] = (16, 10, 5, 2)
    selective_proof_candidate_limit: int = 3
    selective_proof_score_margin: float = 6.0
    selective_proof_max_calls: int = 3

    def __post_init__(self) -> None:
        positive = (
            self.branch_switch_threshold,
            self.no_prune_threshold,
            self.medium_branch_threshold,
            self.high_branch_threshold,
            self.medium_beam_width,
            self.high_beam_width,
            self.very_high_beam_width,
            self.iterative_start_depth,
            self.exact_max_reachable_words,
            self.exact_max_edge_types,
            self.exact_max_vertices,
            self.exact_max_state_estimate,
            self.exact_max_states,
            self.frontier_exact_min_legal_edge_types,
            self.exact_event_log_limit,
            self.selective_proof_candidate_limit,
            self.selective_proof_max_calls,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("adaptive hybrid thresholds must be positive")
        if not (
            self.no_prune_threshold
            <= self.medium_branch_threshold
            <= self.high_branch_threshold
        ):
            raise ValueError("dynamic branch thresholds must be non-decreasing")
        if not self.ply_width_caps or any(
            width <= 0 for width in self.ply_width_caps
        ):
            raise ValueError("ply_width_caps must contain positive widths")
        if not 0.0 <= self.pvs_research_rate_threshold <= 1.0:
            raise ValueError("pvs_research_rate_threshold must be in [0, 1]")
        if self.pvs_time_growth_limit < 1.0:
            raise ValueError("pvs_time_growth_limit must be at least 1")
        if not 0.0 < self.next_depth_safety_ratio <= 1.0:
            raise ValueError("next_depth_safety_ratio must be in (0, 1]")
        if not 0.0 < self.exact_time_fraction <= 1.0:
            raise ValueError("exact_time_fraction must be in (0, 1]")
        if self.exact_time_cap_sec <= 0:
            raise ValueError("exact_time_cap_sec must be positive")
        if self.exact_normal_time_reserve_sec < 0:
            raise ValueError("exact_normal_time_reserve_sec must be non-negative")
        if not (
            self.score_gap_wide_threshold
            < self.score_gap_narrow_threshold
        ):
            raise ValueError(
                "score gap thresholds must satisfy wide < narrow"
            )
        if (
            len(self.score_gap_min_widths) != len(self.score_gap_max_widths)
            or not self.score_gap_min_widths
            or any(width <= 0 for width in self.score_gap_min_widths)
            or any(width <= 0 for width in self.score_gap_max_widths)
            or any(
                minimum > maximum
                for minimum, maximum in zip(
                    self.score_gap_min_widths,
                    self.score_gap_max_widths,
                )
            )
        ):
            raise ValueError("invalid score-gap beam width bounds")
        if self.selective_proof_score_margin < 0:
            raise ValueError("selective proof score margin must be non-negative")


@dataclass(frozen=True)
class PositionScale:
    legal_edge_types: int
    legal_word_count: int
    safe_word_count: int
    reachable_word_count: int
    reachable_edge_types: int
    reachable_vertices: int
    estimated_state_count: int


def _iter_bits(mask: int):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def position_scale(
    state: AIEdgeState,
    estimate_cap: int = 10**18,
) -> PositionScale:
    """Return cheap residual-graph features without mutating ``state``."""

    char_count = state.edge_dictionary.char_count
    if state.required_char_id is None:
        reachable = {
            char_id
            for char_id in range(char_count)
            if state.active_end_masks[char_id]
        }
        for mask in state.active_end_masks:
            reachable.update(_iter_bits(mask))
    else:
        reachable = set()
        frontier = [state.required_char_id]
        while frontier:
            char_id = frontier.pop()
            if char_id in reachable:
                continue
            reachable.add(char_id)
            frontier.extend(
                end_id
                for end_id in _iter_bits(state.active_end_masks[char_id])
                if end_id not in reachable
            )

    word_count = 0
    edge_types = 0
    estimate = 1
    for start_id in reachable:
        row = start_id * char_count
        for end_id in _iter_bits(state.active_end_masks[start_id]):
            count = state.edge_counts[row + end_id]
            if count <= 0:
                continue
            word_count += count
            edge_types += 1
            estimate *= count + 1
            if estimate > estimate_cap:
                estimate = estimate_cap + 1

    if state.required_char_id is None:
        legal_words = sum(state.remaining_word_counts)
        safe_words = sum(state.remaining_safe_word_counts)
    else:
        legal_words = state.remaining_word_counts[state.required_char_id]
        safe_words = state.remaining_safe_word_counts[state.required_char_id]
    return PositionScale(
        legal_edge_types=len(state.available_edges()),
        legal_word_count=legal_words,
        safe_word_count=safe_words,
        reachable_word_count=word_count,
        reachable_edge_types=edge_types,
        reachable_vertices=len(reachable),
        estimated_state_count=estimate,
    )


def _extra_decision(
    decision: EdgeMoveDecision,
    **extra: object,
) -> EdgeMoveDecision:
    return replace(decision, extra={**decision.extra, **extra})


class _DynamicBeamMixin:
    adaptive_config: AdaptiveHybridConfig
    _force_full_search = False

    def _dynamic_width(self, candidate_count: int, ply: int) -> int:
        if self._force_full_search or (
            candidate_count <= self.adaptive_config.no_prune_threshold
        ):
            return candidate_count
        if candidate_count <= self.adaptive_config.medium_branch_threshold:
            width = self.adaptive_config.medium_beam_width
        elif candidate_count <= self.adaptive_config.high_branch_threshold:
            width = self.adaptive_config.high_beam_width
        else:
            width = self.adaptive_config.very_high_beam_width
        cap = self.adaptive_config.ply_width_caps[
            min(ply, len(self.adaptive_config.ply_width_caps) - 1)
        ]
        return min(candidate_count, width, cap)

    def _edge_ordering_limit(self, ply: int) -> None:
        # Candidate count is needed before the dynamic policy can choose a
        # width. Candidate evaluation was already O(all candidates) in the
        # fixed-beam implementation, so only the final selection moves later.
        return None

    def _record_edge_ordering_limit(
        self,
        candidate_count: int,
        selected_count: int,
        ply: int,
        stats: SearchStats,
    ) -> None:
        # _ordered_edges receives the full list; actual dynamic pruning is
        # recorded by _select_ordered_edge_candidates below.
        return None

    def _record_dynamic_width(
        self,
        candidate_count: int,
        selected_count: int,
        width: int,
        ply: int,
        stats: SearchStats,
    ) -> None:
        stats.beam_widths_used[ply] = width
        stats.beam_candidate_counts_by_ply[ply] = (
            stats.beam_candidate_counts_by_ply.get(ply, 0) + candidate_count
        )
        stats.beam_selected_counts_by_ply[ply] = (
            stats.beam_selected_counts_by_ply.get(ply, 0) + selected_count
        )
        stats.beam_ordering_calls_by_ply[ply] = (
            stats.beam_ordering_calls_by_ply.get(ply, 0) + 1
        )
        stats.beam_max_selected_by_ply[ply] = max(
            stats.beam_max_selected_by_ply.get(ply, 0),
            selected_count,
        )
        key = f"{ply}:{width}"
        stats.dynamic_beam_width_counts[key] = (
            stats.dynamic_beam_width_counts.get(key, 0) + 1
        )
        pruned = max(0, candidate_count - selected_count)
        stats.beam_pruned_counts_by_ply[ply] = (
            stats.beam_pruned_counts_by_ply.get(ply, 0) + pruned
        )
        stats.beam_pruned_move_count += pruned

    def _select_ordered_edge_candidates(
        self,
        ordered: list[tuple[int, int]],
        *,
        candidate_count: int,
        ply: int,
        stats: SearchStats,
        evaluations: dict[tuple[int, int], CandidateEvaluation] | None = None,
    ) -> list[tuple[int, int]]:
        """Apply the dynamic policy after every edge-ordering call."""

        width = self._dynamic_width(candidate_count, ply)
        selected = ordered[:width]
        self._record_dynamic_width(
            candidate_count, len(selected), width, ply, stats
        )
        return selected

    def _select_root_candidates(
        self,
        candidates: list[T],
        stats: SearchStats,
    ) -> list[T]:
        width = self._dynamic_width(len(candidates), 0)
        selected = candidates[:width]
        self._record_dynamic_width(
            len(candidates), len(selected), width, 0, stats
        )
        return selected

    def _limit_beam(
        self,
        candidates: list[T],
        ply: int,
        stats: SearchStats,
    ) -> list[T]:
        width = self._dynamic_width(len(candidates), ply)
        selected = candidates[:width]
        self._record_dynamic_width(
            len(candidates), len(selected), width, ply, stats
        )
        return selected

    def _dynamic_extra(self) -> dict[str, object]:
        return {
            "dynamic_beam": True,
            "dynamic_beam_config": asdict(self.adaptive_config),
        }


class BranchSwitchAlphaBetaAgent(BeamAlphaBetaAgent):
    """Use full-width AlphaBeta on low-branching positions, Beam otherwise."""

    name = "branch_switch_alpha_beta"

    def __init__(
        self,
        *args: object,
        adaptive_config: AdaptiveHybridConfig = AdaptiveHybridConfig(),
        **kwargs: object,
    ) -> None:
        self.adaptive_config = adaptive_config
        self._full_alpha_mode = False
        super().__init__(*args, **kwargs)

    def _edge_ordering_limit(self, ply: int) -> int | None:
        return None if self._full_alpha_mode else super()._edge_ordering_limit(ply)

    def _record_edge_ordering_limit(
        self,
        candidate_count: int,
        selected_count: int,
        ply: int,
        stats: SearchStats,
    ) -> None:
        if not self._full_alpha_mode:
            super()._record_edge_ordering_limit(
                candidate_count, selected_count, ply, stats
            )

    def _select_root_candidates(
        self,
        candidates: list[T],
        stats: SearchStats,
    ) -> list[T]:
        if self._full_alpha_mode:
            return candidates
        return super()._select_root_candidates(candidates, stats)

    def _limit_beam(
        self,
        candidates: list[T],
        ply: int,
        stats: SearchStats,
    ) -> list[T]:
        if self._full_alpha_mode:
            return candidates
        return super()._limit_beam(candidates, ply, stats)

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        scale = position_scale(state)
        self._full_alpha_mode = (
            scale.legal_edge_types
            <= self.adaptive_config.branch_switch_threshold
        )
        mode = (
            "alpha_beta_full"
            if self._full_alpha_mode
            else "beam_alpha_beta"
        )
        reason = (
            "legal_edges_at_or_below_threshold"
            if self._full_alpha_mode
            else "legal_edges_above_threshold"
        )
        try:
            decision = super().choose_edge(state)
        finally:
            self._full_alpha_mode = False
        return _extra_decision(
            decision,
            search_mode=mode,
            mode_history=[{"mode": mode, "reason": reason}],
            switch_reason=reason,
            mode_counts={mode: 1},
            mode_switch_count=0,
            position_scale=asdict(scale),
        )


class DynamicBeamAlphaBetaAgent(_DynamicBeamMixin, BeamAlphaBetaAgent):
    """AlphaBeta with a candidate-count-dependent beam at every node."""

    name = "dynamic_beam_alpha_beta"

    def __init__(
        self,
        *args: object,
        adaptive_config: AdaptiveHybridConfig = AdaptiveHybridConfig(),
        **kwargs: object,
    ) -> None:
        self.adaptive_config = adaptive_config
        super().__init__(*args, **kwargs)

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        scale = position_scale(state)
        decision = super().choose_edge(state)
        return _extra_decision(
            decision,
            search_mode="dynamic_beam_alpha_beta",
            mode_history=[
                {
                    "mode": "dynamic_beam_alpha_beta",
                    "reason": "candidate_count_policy",
                }
            ],
            switch_reason="candidate_count_policy",
            mode_counts={"dynamic_beam_alpha_beta": 1},
            mode_switch_count=0,
            position_scale=asdict(scale),
            **self._dynamic_extra(),
        )


class _ScoreGapDynamicBeamMixin(_DynamicBeamMixin):
    """Choose each node's beam width from already-computed ordering scores."""

    _previous_root_best: tuple[int, int] | None = None

    def _score_gap_width(
        self,
        ordered: Sequence[tuple[int, int]],
        evaluations: dict[tuple[int, int], CandidateEvaluation],
        ply: int,
    ) -> tuple[int, float]:
        base = self.beam_widths[min(ply, len(self.beam_widths) - 1)]
        bound_index = min(
            ply, len(self.adaptive_config.score_gap_min_widths) - 1
        )
        minimum = self.adaptive_config.score_gap_min_widths[bound_index]
        maximum = self.adaptive_config.score_gap_max_widths[bound_index]
        if len(ordered) < 2:
            return min(len(ordered), minimum), math.inf
        first = evaluations[ordered[0]].total_score
        second = evaluations[ordered[1]].total_score
        gap = first - second
        if not math.isfinite(gap):
            gap = 1_000_000_000.0
        if gap <= self.adaptive_config.score_gap_wide_threshold:
            width = maximum
        elif gap >= self.adaptive_config.score_gap_narrow_threshold:
            width = minimum
        else:
            width = base
        return min(len(ordered), width), gap

    def _record_score_gap(
        self,
        *,
        gap: float,
        ply: int,
        stats: SearchStats,
    ) -> None:
        stats.beam_score_gap_sums_by_ply[ply] = (
            stats.beam_score_gap_sums_by_ply.get(ply, 0.0) + gap
        )
        stats.beam_score_gap_counts_by_ply[ply] = (
            stats.beam_score_gap_counts_by_ply.get(ply, 0) + 1
        )
        stats.beam_score_gap_mins_by_ply[ply] = min(
            stats.beam_score_gap_mins_by_ply.get(ply, math.inf), gap
        )
        stats.beam_score_gap_maxs_by_ply[ply] = max(
            stats.beam_score_gap_maxs_by_ply.get(ply, -math.inf), gap
        )

    def _select_ordered_edge_candidates(
        self,
        ordered: list[tuple[int, int]],
        *,
        candidate_count: int,
        ply: int,
        stats: SearchStats,
        evaluations: dict[tuple[int, int], CandidateEvaluation] | None = None,
    ) -> list[tuple[int, int]]:
        if not ordered or evaluations is None:
            return []
        width, gap = self._score_gap_width(ordered, evaluations, ply)
        selected = ordered[:width]
        retained_previous_best = False
        if (
            ply == 0
            and self._previous_root_best in ordered
            and self._previous_root_best not in selected
            and selected
        ):
            selected = [self._previous_root_best, *selected[:-1]]
            retained_previous_best = True
        self._record_score_gap(gap=gap, ply=ply, stats=stats)
        self._record_dynamic_width(
            candidate_count, len(selected), width, ply, stats
        )
        if retained_previous_best:
            stats.dynamic_beam_width_counts["previous_best_retained"] = (
                stats.dynamic_beam_width_counts.get(
                    "previous_best_retained", 0
                )
                + 1
            )
        return selected


class ScoreGapDynamicBeamAlphaBetaAgent(
    _ScoreGapDynamicBeamMixin,
    BeamAlphaBetaAgent,
):
    """BeamAlphaBeta widened for close candidates and narrowed for clear ones."""

    name = "score_gap_dynamic_beam_alpha_beta"

    def __init__(
        self,
        *args: object,
        adaptive_config: AdaptiveHybridConfig = AdaptiveHybridConfig(),
        **kwargs: object,
    ) -> None:
        self.adaptive_config = adaptive_config
        self._previous_root_best = None
        super().__init__(*args, **kwargs)

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        scale = position_scale(state)
        decision = super().choose_edge(state)
        if decision.start_id is not None and decision.end_id is not None:
            self._previous_root_best = (
                decision.start_id,
                decision.end_id,
            )
        return _extra_decision(
            decision,
            search_mode=self.name,
            mode_history=[
                {
                    "mode": self.name,
                    "reason": "top_ordering_score_gap",
                }
            ],
            switch_reason="top_ordering_score_gap",
            mode_counts={self.name: 1},
            mode_switch_count=0,
            previous_root_best=self._previous_root_best,
            position_scale=asdict(scale),
            **self._dynamic_extra(),
        )


class DynamicBeamPVSAgent(_DynamicBeamMixin, BeamPVSAgent):
    """PVS with the same candidate-count-dependent beam as AlphaBeta."""

    name = "dynamic_beam_pvs"

    def __init__(
        self,
        *args: object,
        adaptive_config: AdaptiveHybridConfig = AdaptiveHybridConfig(),
        **kwargs: object,
    ) -> None:
        self.adaptive_config = adaptive_config
        super().__init__(*args, **kwargs)

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        scale = position_scale(state)
        decision = super().choose_edge(state)
        return _extra_decision(
            decision,
            search_mode="dynamic_beam_pvs",
            mode_history=[
                {
                    "mode": "dynamic_beam_pvs",
                    "reason": "candidate_count_policy",
                }
            ],
            switch_reason="candidate_count_policy",
            mode_counts={"dynamic_beam_pvs": 1},
            mode_switch_count=0,
            position_scale=asdict(scale),
            **self._dynamic_extra(),
        )


_SUM_FIELDS = (
    "nodes_searched",
    "leaf_evaluations",
    "ordering_evaluations",
    "full_survival_evaluations",
    "simple_survival_evaluations",
    "completed_root_moves",
    "cutoff_count",
    "pruned_move_count",
    "beam_pruned_move_count",
    "null_window_search_count",
    "research_count",
    "root_alpha_updates",
    "legal_move_generation_time_sec",
    "candidate_evaluation_time_sec",
    "candidate_sort_time_sec",
    "root_ordering_time_sec",
    "ordering_time_sec",
    "evaluation_time_sec",
    "search_time_sec",
    "total_search_time_sec",
)
_DICT_SUM_FIELDS = (
    "beam_candidate_counts_by_ply",
    "beam_selected_counts_by_ply",
    "beam_pruned_counts_by_ply",
    "beam_ordering_calls_by_ply",
    "dynamic_beam_width_counts",
    "beam_score_gap_sums_by_ply",
    "beam_score_gap_counts_by_ply",
)


def _merge_stats(total: SearchStats, step: SearchStats) -> None:
    for field_name in _SUM_FIELDS:
        setattr(
            total,
            field_name,
            getattr(total, field_name) + getattr(step, field_name),
        )
    for field_name in _DICT_SUM_FIELDS:
        destination = getattr(total, field_name)
        for key, value in getattr(step, field_name).items():
            destination[key] = destination.get(key, 0) + value
    for key, value in step.beam_widths_used.items():
        total.beam_widths_used[key] = value
    for key, value in step.beam_max_selected_by_ply.items():
        total.beam_max_selected_by_ply[key] = max(
            total.beam_max_selected_by_ply.get(key, 0), value
        )
    for key, value in step.beam_score_gap_mins_by_ply.items():
        total.beam_score_gap_mins_by_ply[key] = min(
            total.beam_score_gap_mins_by_ply.get(key, math.inf), value
        )
    for key, value in step.beam_score_gap_maxs_by_ply.items():
        total.beam_score_gap_maxs_by_ply[key] = max(
            total.beam_score_gap_maxs_by_ply.get(key, -math.inf), value
        )


class ResearchAdaptiveBeamAgent(DynamicBeamPVSAgent):
    """One iterative search that switches from PVS to AlphaBeta when risky."""

    name = "research_adaptive_beam"
    low_branch_uses_full_alpha = False

    def _edge_negamax_alpha_beta(
        self,
        state: AIEdgeState,
        depth: int,
        ply: int,
        alpha: float,
        beta: float,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        return BeamAlphaBetaAgent._edge_negamax_alpha_beta(
            self,
            state,
            depth,
            ply,
            alpha,
            beta,
            deadline,
            stats,
        )

    def _alpha_score_edge(
        self,
        state: AIEdgeState,
        start_id: int,
        end_id: int,
        depth: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        check_deadline(deadline)
        if edge_is_terminal(state, end_id):
            return LOSS_SCORE
        root_alpha = getattr(stats, "_root_alpha", LOSS_SCORE)
        state.apply_edge(start_id, end_id)
        try:
            score = -self._edge_negamax_alpha_beta(
                state,
                depth - 1,
                1,
                -WIN_SCORE,
                -root_alpha,
                deadline,
                stats,
            )
        finally:
            state.undo_edge()
        if score > root_alpha:
            setattr(stats, "_root_alpha", score)
            stats.root_alpha_updates += 1
        return score

    def _run_depth(
        self,
        state: AIEdgeState,
        edges: list[tuple[int, int]],
        depth: int,
        mode: str,
        deadline: float,
    ) -> tuple[tuple[int, int], float, SearchStats, bool]:
        stats = SearchStats()
        self._force_full_search = mode == "alpha_beta_full"
        try:
            ordered, pre_scores, ordering_timed_out = self._ordered_edges(
                state,
                edges,
                deadline,
                allow_partial=True,
                stats=stats,
                ply=0,
            )
            if not ordered:
                fallback = _safe_edge_fallback(state, edges)
                assert fallback is not None
                return fallback, LOSS_SCORE, stats, False
            best = ordered[0]
            best_score = pre_scores[best].total_score
            for edge in ordered:
                check_deadline(deadline)
                if mode == "beam_pvs":
                    score = BeamPVSAgent._score_edge(
                        self,
                        state,
                        edge[0],
                        edge[1],
                        depth,
                        deadline,
                        stats,
                    )
                else:
                    score = self._alpha_score_edge(
                        state,
                        edge[0],
                        edge[1],
                        depth,
                        deadline,
                        stats,
                    )
                stats.completed_root_moves += 1
                if score > best_score or stats.completed_root_moves == 1:
                    best = edge
                    best_score = score
            return best, best_score, stats, not ordering_timed_out
        finally:
            self._force_full_search = False

    def _initial_mode(self, scale: PositionScale) -> tuple[str, str]:
        if (
            self.low_branch_uses_full_alpha
            and scale.legal_edge_types
            <= self.adaptive_config.branch_switch_threshold
        ):
            return "alpha_beta_full", "low_branching_position"
        if scale.safe_word_count <= self.adaptive_config.no_prune_threshold:
            return "beam_alpha_beta", "few_safe_moves_avoid_pvs_overhead"
        if scale.legal_edge_types > self.adaptive_config.no_prune_threshold:
            return "beam_pvs", "many_legal_edges_start_with_pvs"
        return "beam_alpha_beta", "few_legal_edges_avoid_pvs_overhead"

    def _next_mode(
        self,
        previous_mode: str,
        previous_stats: SearchStats,
        previous_time: float,
        prior_completed_time: float | None,
        remaining_time: float,
    ) -> tuple[str, str, float]:
        research_rate = (
            previous_stats.research_count
            / previous_stats.null_window_search_count
            if previous_stats.null_window_search_count
            else 0.0
        )
        growth = (
            previous_time / prior_completed_time
            if prior_completed_time is not None
            and prior_completed_time > 0
            else 2.0
        )
        growth = max(1.0, growth)
        predicted = previous_time * min(
            growth, self.adaptive_config.pvs_time_growth_limit
        )
        if previous_mode != "beam_pvs":
            return previous_mode, "continue_non_pvs_mode", predicted
        if research_rate > self.adaptive_config.pvs_research_rate_threshold:
            return (
                "beam_alpha_beta",
                "pvs_research_rate_above_threshold",
                predicted,
            )
        if predicted > (
            remaining_time * self.adaptive_config.next_depth_safety_ratio
        ):
            return (
                "beam_alpha_beta",
                "predicted_next_depth_exceeds_safe_budget",
                predicted,
            )
        return "beam_pvs", "pvs_research_low_and_budget_safe", predicted

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        started = time.perf_counter()
        deadline = started + self.time_limit_sec
        target_depth = self._effective_depth()
        start_depth = min(
            self.adaptive_config.iterative_start_depth,
            max(1, target_depth - 1),
        )
        edges = state.available_edges()
        if not edges:
            return EdgeMoveDecision(
                None, None, time.perf_counter() - started, False, LOSS_SCORE
            )
        fallback = _safe_edge_fallback(state, edges)
        assert fallback is not None
        best_edge = fallback
        best_score = LOSS_SCORE
        completed_depth = 0
        total_stats = SearchStats()
        mode_history: list[dict[str, object]] = []
        mode_counts: dict[str, int] = {}
        scale = position_scale(
            state, self.adaptive_config.exact_max_state_estimate
        )
        mode, reason = self._initial_mode(scale)
        previous_time: float | None = None
        fallback_count = 0
        timed_out = False
        predicted_next_time = 0.0

        for depth in range(start_depth, target_depth + 1):
            remaining = max(0.0, deadline - time.perf_counter())
            if remaining <= 0:
                timed_out = True
                fallback_count += int(completed_depth > 0)
                break
            depth_started = time.perf_counter()
            depth_started_offset = depth_started - started
            try:
                edge, score, stats, complete = self._run_depth(
                    state, edges, depth, mode, deadline
                )
            except SearchTimeout:
                timed_out = True
                fallback_count += int(completed_depth > 0)
                mode_history.append(
                    {
                        "depth": depth,
                        "effective_depth": depth,
                        "mode": mode,
                        "reason": reason,
                        "status": "timeout",
                        "completed": False,
                        "started_offset_sec": depth_started_offset,
                        "finished_offset_sec": time.perf_counter() - started,
                        "elapsed_time_sec": (
                            time.perf_counter() - depth_started
                        ),
                    }
                )
                break
            duration = time.perf_counter() - depth_started
            _merge_stats(total_stats, stats)
            if not complete:
                timed_out = True
                fallback_count += int(completed_depth > 0)
                mode_history.append(
                    {
                        "depth": depth,
                        "effective_depth": depth,
                        "mode": mode,
                        "reason": reason,
                        "status": "incomplete",
                        "completed": False,
                        "started_offset_sec": depth_started_offset,
                        "finished_offset_sec": time.perf_counter() - started,
                        "elapsed_time_sec": duration,
                        "nodes_searched": stats.nodes_searched,
                        "null_window_search_count": (
                            stats.null_window_search_count
                        ),
                        "research_count": stats.research_count,
                        "research_rate": (
                            stats.research_count
                            / stats.null_window_search_count
                            if stats.null_window_search_count
                            else 0.0
                        ),
                    }
                )
                break
            best_edge, best_score = edge, score
            completed_depth = depth
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
            research_rate = (
                stats.research_count / stats.null_window_search_count
                if stats.null_window_search_count
                else 0.0
            )
            history_item: dict[str, object] = {
                "depth": depth,
                "effective_depth": depth,
                "mode": mode,
                "reason": reason,
                "status": "complete",
                "completed": True,
                "started_offset_sec": depth_started_offset,
                "finished_offset_sec": time.perf_counter() - started,
                "elapsed_time_sec": duration,
                "nodes_searched": stats.nodes_searched,
                "null_window_search_count": stats.null_window_search_count,
                "research_count": stats.research_count,
                "research_rate": research_rate,
            }
            mode_history.append(history_item)
            if depth < target_depth:
                next_mode, next_reason, predicted_next_time = self._next_mode(
                    mode,
                    stats,
                    duration,
                    previous_time,
                    max(0.0, deadline - time.perf_counter()),
                )
                history_item["next_mode"] = next_mode
                history_item["next_reason"] = next_reason
                history_item["predicted_next_time_sec"] = predicted_next_time
                mode, reason = next_mode, next_reason
                previous_time = duration

        elapsed = time.perf_counter() - started
        total_stats.total_search_time_sec = elapsed
        elapsed_ratio, target_elapsed_ratio = self._elapsed_ratios(elapsed)
        self._record_depth_result(timed_out, target_elapsed_ratio)
        analysis = edge_candidate_analysis(
            state, best_edge[0], best_edge[1], self.evaluation_config
        )
        final_mode = (
            str(mode_history[-1]["mode"]) if mode_history else "fallback"
        )
        completed_modes = [
            str(item["mode"])
            for item in mode_history
            if item.get("status") == "complete"
        ]
        mode_switch_count = sum(
            previous != current
            for previous, current in zip(
                completed_modes, completed_modes[1:]
            )
        )
        extra = self._search_extra(
            total_stats,
            completed_depth or start_depth,
            timed_out=timed_out,
            move_unit="edge_type",
            elapsed_ratio=elapsed_ratio,
            target_elapsed_ratio=target_elapsed_ratio,
            root_candidate_count=len(edges),
            searched_root_candidate_count=total_stats.completed_root_moves,
            completed_iterative_depth=completed_depth,
            iterative_start_depth=start_depth,
            iterative_target_depth=target_depth,
            depth_control="single_internal_iterative_deepening",
            search_mode=final_mode,
            mode_history=mode_history,
            switch_reason=(
                str(mode_history[-1].get("reason", reason))
                if mode_history
                else "no_depth_completed"
            ),
            mode_counts=mode_counts,
            mode_switch_count=mode_switch_count,
            fallback_count=fallback_count,
            predicted_next_depth_time_sec=predicted_next_time,
            position_scale=asdict(scale),
            **self._dynamic_extra(),
            **analysis,
        )
        return EdgeMoveDecision(
            best_edge[0],
            best_edge[1],
            elapsed,
            timed_out,
            best_score,
            extra,
        )


class _ExactEndgameMixin:
    adaptive_config: AdaptiveHybridConfig

    def _exact_eligible(self, scale: PositionScale) -> tuple[bool, str]:
        checks = (
            (
                scale.reachable_word_count
                <= self.adaptive_config.exact_max_reachable_words,
                "reachable_words",
            ),
            (
                scale.reachable_edge_types
                <= self.adaptive_config.exact_max_edge_types,
                "reachable_edge_types",
            ),
            (
                scale.reachable_vertices
                <= self.adaptive_config.exact_max_vertices,
                "reachable_vertices",
            ),
            (
                scale.estimated_state_count
                <= self.adaptive_config.exact_max_state_estimate,
                "estimated_states",
            ),
        )
        failed = [name for passed, name in checks if not passed]
        return (not failed, "eligible" if not failed else "too_large:" + ",".join(failed))

    def _residual_dictionary(self, state: AIEdgeState) -> EdgeDictionary:
        return EdgeDictionary(
            dictionary_hash=state.edge_dictionary.dictionary_hash,
            normalization_version=state.edge_dictionary.normalization_version,
            char_to_id=dict(state.edge_dictionary.char_to_id),
            id_to_char=state.edge_dictionary.id_to_char,
            char_count=state.edge_dictionary.char_count,
            edge_instance_count=sum(state.edge_counts),
            initial_edge_counts=tuple(state.edge_counts),
            initial_active_end_masks=tuple(state.active_end_masks),
        )

    def _try_exact(
        self,
        state: AIEdgeState,
        scale: PositionScale,
        started: float,
    ) -> EdgeMoveDecision | None:
        eligible, reason = self._exact_eligible(scale)
        self._last_exact_gate = {
            "eligible": eligible,
            "reason": reason,
            **asdict(scale),
        }
        if not eligible:
            return None
        edges = state.available_edges()
        fallback = _safe_edge_fallback(state, edges)
        if fallback is None:
            return EdgeMoveDecision(
                None, None, time.perf_counter() - started, False, LOSS_SCORE
            )
        exact_budget = min(
            self.adaptive_config.exact_time_cap_sec,
            self.time_limit_sec * self.adaptive_config.exact_time_fraction,
        )
        solver = ShiritoriSolver(
            self._residual_dictionary(state),
            max_states=self.adaptive_config.exact_max_states,
            timeout_sec=exact_budget,
        )
        try:
            if state.required_char_id is None:
                results = solver.analyze_first_moves(stop_on_first_win=True)
                winning = next((item for item in results if item.is_winning), None)
                exact_edge = (
                    (winning.start_id, winning.end_id)
                    if winning is not None
                    else fallback
                )
                is_winning = winning is not None
            else:
                is_winning = solver.solve(state.required_char_id)
                exact_edge = (
                    solver.get_best_edge(state.required_char_id)
                    if is_winning
                    else fallback
                )
            assert exact_edge is not None
            elapsed = time.perf_counter() - started
            return EdgeMoveDecision(
                exact_edge[0],
                exact_edge[1],
                elapsed,
                False,
                WIN_SCORE if is_winning else LOSS_SCORE,
                {
                    "search_mode": "exact_endgame",
                    "mode_history": [
                        {
                            "mode": "exact_endgame",
                            "reason": reason,
                            "status": "complete",
                        }
                    ],
                    "switch_reason": reason,
                    "mode_counts": {"exact_endgame": 1},
                    "mode_switch_count": 0,
                    "position_scale": asdict(scale),
                    "exact_attempt_count": 1,
                    "exact_success_count": 1,
                    "exact_timeout_count": 0,
                    "exact_limit_count": 0,
                    "exact_state_count": solver.count_states(),
                    "exact_result": "win" if is_winning else "loss",
                    "exact_time_budget_sec": exact_budget,
                    "fallback_count": 0,
                    "effective_depth": 0,
                    "nodes_searched": solver.count_states(),
                },
            )
        except AnalysisLimitExceeded as exc:
            was_timeout = exc.reason.startswith("timeout")
            elapsed = time.perf_counter() - started
            return EdgeMoveDecision(
                fallback[0],
                fallback[1],
                elapsed,
                False,
                LOSS_SCORE,
                {
                    "search_mode": "exact_fallback",
                    "mode_history": [
                        {
                            "mode": "exact_endgame",
                            "reason": reason,
                            "status": "limit_exceeded",
                            "limit_reason": exc.reason,
                        },
                        {
                            "mode": "exact_fallback",
                            "reason": "exact_limit_exceeded",
                            "status": "selected",
                        },
                    ],
                    "switch_reason": "exact_limit_exceeded",
                    "mode_counts": {
                        "exact_endgame": 1,
                        "exact_fallback": 1,
                    },
                    "mode_switch_count": 1,
                    "position_scale": asdict(scale),
                    "exact_attempt_count": 1,
                    "exact_success_count": 0,
                    "exact_timeout_count": int(was_timeout),
                    "exact_limit_count": 1,
                    "exact_state_count": solver.count_states(),
                    "exact_result": "incomplete",
                    "exact_time_budget_sec": exact_budget,
                    "fallback_count": 1,
                    "effective_depth": 0,
                    "nodes_searched": solver.count_states(),
                },
            )

    def _attach_exact_gate(
        self,
        decision: EdgeMoveDecision,
        scale: PositionScale,
    ) -> EdgeMoveDecision:
        return _extra_decision(
            decision,
            position_scale=asdict(scale),
            exact_gate=self._last_exact_gate,
            exact_attempt_count=0,
            exact_success_count=0,
            exact_timeout_count=0,
            exact_limit_count=0,
            exact_state_count=0,
        )


class EndgameExactHybridAgent(_ExactEndgameMixin, BeamAlphaBetaAgent):
    """Fixed BeamAlphaBeta normally, bounded exact search in small endgames."""

    name = "endgame_exact_hybrid"

    def __init__(
        self,
        *args: object,
        adaptive_config: AdaptiveHybridConfig = AdaptiveHybridConfig(),
        **kwargs: object,
    ) -> None:
        self.adaptive_config = adaptive_config
        self._last_exact_gate: dict[str, object] = {}
        super().__init__(*args, **kwargs)

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        started = time.perf_counter()
        scale = position_scale(
            state, self.adaptive_config.exact_max_state_estimate
        )
        exact = self._try_exact(state, scale, started)
        if exact is not None:
            return exact
        decision = super().choose_edge(state)
        return self._attach_exact_gate(
            _extra_decision(
                decision,
                search_mode="beam_alpha_beta",
                mode_history=[
                    {
                        "mode": "beam_alpha_beta",
                        "reason": "exact_gate_rejected",
                    }
                ],
                switch_reason="exact_gate_rejected",
                mode_counts={"beam_alpha_beta": 1},
                mode_switch_count=0,
            ),
            scale,
        )


class ProofExtensionBeamAlphaBetaAgent(
    _ExactEndgameMixin,
    BeamAlphaBetaAgent,
):
    """Fixed BeamAlphaBeta with bounded exact proofs at depth frontiers."""

    name = "proof_extension_beam_alpha_beta"

    def __init__(
        self,
        *args: object,
        adaptive_config: AdaptiveHybridConfig = AdaptiveHybridConfig(),
        **kwargs: object,
    ) -> None:
        self.adaptive_config = adaptive_config
        self._last_exact_gate: dict[str, object] = {}
        self._proof_events: list[dict[str, object]] = []
        self._proof_cache: dict[
            tuple[int, tuple[int, ...]], bool
        ] = {}
        self._proof_exact_elapsed = 0.0
        self._proof_counters: dict[str, int] = {}
        self._proof_ineligible_reasons: dict[str, int] = {}
        self._active_root_edge: tuple[int, int] | None = None
        self._proof_root_edges: set[tuple[int, int]] = set()
        self._proof_turn_deadline: float | None = None
        super().__init__(*args, **kwargs)

    def _deadline(self) -> float:
        if self._proof_turn_deadline is not None:
            return self._proof_turn_deadline
        return super()._deadline()

    def _reset_proof_context(self) -> None:
        self._proof_events = []
        self._proof_cache = {}
        self._proof_exact_elapsed = 0.0
        self._proof_counters = {
            "root_attempts": 0,
            "frontier_attempts": 0,
            "completed": 0,
            "interrupted": 0,
            "ineligible": 0,
            "trivial_successes": 0,
            "nontrivial_successes": 0,
            "cache_hits": 0,
            "fallbacks": 0,
            "timeouts": 0,
        }
        self._proof_ineligible_reasons = {}
        self._active_root_edge = None
        self._proof_root_edges = set()

    def _record_proof_event(self, event: dict[str, object]) -> None:
        if len(self._proof_events) < self.adaptive_config.exact_event_log_limit:
            self._proof_events.append(event)

    def _proof_budget(self, deadline: float) -> float:
        total_limit = min(
            self.adaptive_config.exact_time_cap_sec,
            self.time_limit_sec * self.adaptive_config.exact_time_fraction,
        )
        available_total = total_limit - self._proof_exact_elapsed
        available_turn = (
            deadline
            - time.perf_counter()
            - self.adaptive_config.exact_normal_time_reserve_sec
        )
        return max(0.0, min(available_total, available_turn))

    def _frontier_eligible(
        self,
        state: AIEdgeState,
    ) -> tuple[PositionScale | None, str]:
        if state.required_char_id is None:
            return None, "no_required_char"
        required = state.required_char_id
        legal_types = state.active_edge_type_counts[required]
        if (
            legal_types
            < self.adaptive_config.frontier_exact_min_legal_edge_types
        ):
            return None, "too_few_legal_edge_types"
        if (
            state.remaining_word_counts[required]
            > self.adaptive_config.exact_max_reachable_words
        ):
            return None, "too_many_immediate_words"
        scale = position_scale(
            state, self.adaptive_config.exact_max_state_estimate
        )
        eligible, reason = self._exact_eligible(scale)
        return (scale if eligible else None), reason

    def _frontier_exact_score(
        self,
        state: AIEdgeState,
        *,
        deadline: float,
        ply: int,
        normal_score: float,
    ) -> float | None:
        scale, reason = self._frontier_eligible(state)
        if scale is None:
            self._proof_counters["ineligible"] += 1
            self._proof_ineligible_reasons[reason] = (
                self._proof_ineligible_reasons.get(reason, 0) + 1
            )
            return None
        budget = self._proof_budget(deadline)
        if budget <= 0:
            self._proof_counters["ineligible"] += 1
            self._proof_ineligible_reasons["no_exact_time_budget"] = (
                self._proof_ineligible_reasons.get(
                    "no_exact_time_budget", 0
                )
                + 1
            )
            return None
        assert state.required_char_id is not None
        self._proof_counters["frontier_attempts"] += 1
        key = (state.required_char_id, tuple(state.edge_counts))
        started = time.perf_counter()
        if key in self._proof_cache:
            is_winning = self._proof_cache[key]
            self._proof_counters["cache_hits"] += 1
            exact_score = (
                WIN_SCORE - float(ply)
                if is_winning
                else LOSS_SCORE + float(ply)
            )
            self._record_proof_event(
                {
                    "location": "frontier",
                    "ply": ply,
                    "normal_search_depth": 0,
                    "status": "cache_hit",
                    "result": "win" if is_winning else "loss",
                    "normal_score": normal_score,
                    "exact_score": exact_score,
                    "score_difference": exact_score - normal_score,
                    "memo_hit": True,
                    "multiple_legal_edges": scale.legal_edge_types > 1,
                    "trivial": False,
                    **asdict(scale),
                }
            )
            if self._active_root_edge is not None:
                self._proof_root_edges.add(self._active_root_edge)
            return exact_score

        solver = ShiritoriSolver(
            self._residual_dictionary(state),
            max_states=self.adaptive_config.exact_max_states,
            timeout_sec=budget,
        )
        try:
            is_winning = solver.solve(state.required_char_id)
        except AnalysisLimitExceeded as exc:
            elapsed = time.perf_counter() - started
            self._proof_exact_elapsed += elapsed
            self._proof_counters["interrupted"] += 1
            if exc.reason.startswith("timeout"):
                self._proof_counters["timeouts"] += 1
            self._proof_counters["fallbacks"] += 1
            self._record_proof_event(
                {
                    "location": "frontier",
                    "ply": ply,
                    "normal_search_depth": 0,
                    "status": "interrupted",
                    "limit_reason": exc.reason,
                    "result": "unknown",
                    "normal_score": normal_score,
                    "exact_score": None,
                    "score_difference": None,
                    "searched_states": solver.count_states(),
                    "elapsed_time_sec": elapsed,
                    "time_budget_sec": budget,
                    "memo_hit": False,
                    "multiple_legal_edges": scale.legal_edge_types > 1,
                    "trivial": solver.count_states() <= 1,
                    "fallback": "heuristic_evaluation",
                    **asdict(scale),
                }
            )
            return None

        elapsed = time.perf_counter() - started
        self._proof_exact_elapsed += elapsed
        self._proof_cache[key] = is_winning
        self._proof_counters["completed"] += 1
        trivial = solver.count_states() <= 1
        counter = "trivial_successes" if trivial else "nontrivial_successes"
        self._proof_counters[counter] += 1
        exact_score = (
            WIN_SCORE - float(ply)
            if is_winning
            else LOSS_SCORE + float(ply)
        )
        if self._active_root_edge is not None:
            self._proof_root_edges.add(self._active_root_edge)
        self._record_proof_event(
            {
                "location": "frontier",
                "ply": ply,
                "normal_search_depth": 0,
                "status": "complete",
                "result": "win" if is_winning else "loss",
                "normal_score": normal_score,
                "exact_score": exact_score,
                "score_difference": exact_score - normal_score,
                "searched_states": solver.count_states(),
                "elapsed_time_sec": elapsed,
                "time_budget_sec": budget,
                "memo_hit": False,
                "multiple_legal_edges": scale.legal_edge_types > 1,
                "trivial": trivial,
                "fallback": "none",
                **asdict(scale),
            }
        )
        return exact_score

    def _evaluate_edge_leaf(
        self,
        state: AIEdgeState,
        deadline: float,
        ply: int,
        stats: SearchStats,
    ) -> float:
        normal_score = super()._evaluate_edge_leaf(
            state, deadline, ply, stats
        )
        exact_score = self._frontier_exact_score(
            state,
            deadline=deadline,
            ply=ply,
            normal_score=normal_score,
        )
        return normal_score if exact_score is None else exact_score

    def _score_edge(
        self,
        state: AIEdgeState,
        start_id: int,
        end_id: int,
        depth: int,
        deadline: float,
        stats: SearchStats,
    ) -> float:
        self._active_root_edge = (start_id, end_id)
        try:
            return super()._score_edge(
                state, start_id, end_id, depth, deadline, stats
            )
        finally:
            self._active_root_edge = None

    def _proof_extra(
        self,
        decision: EdgeMoveDecision,
    ) -> EdgeMoveDecision:
        selected = (
            (decision.start_id, decision.end_id)
            if decision.start_id is not None and decision.end_id is not None
            else None
        )
        return _extra_decision(
            decision,
            proof_extension=True,
            exact_call_events=self._proof_events,
            exact_root_call_count=self._proof_counters["root_attempts"],
            exact_frontier_call_count=self._proof_counters[
                "frontier_attempts"
            ],
            exact_attempt_count=(
                self._proof_counters["root_attempts"]
                + self._proof_counters["frontier_attempts"]
            ),
            exact_success_count=self._proof_counters["completed"],
            exact_limit_count=self._proof_counters["interrupted"],
            exact_timeout_count=self._proof_counters["timeouts"],
            exact_ineligible_count=self._proof_counters["ineligible"],
            exact_ineligible_reason_counts=dict(
                sorted(self._proof_ineligible_reasons.items())
            ),
            exact_trivial_success_count=self._proof_counters[
                "trivial_successes"
            ],
            exact_nontrivial_success_count=self._proof_counters[
                "nontrivial_successes"
            ],
            exact_memo_hit_count=self._proof_counters["cache_hits"],
            exact_total_time_sec=self._proof_exact_elapsed,
            exact_fallback_count=self._proof_counters["fallbacks"],
            root_selected_move_had_exact_proof=(
                selected in self._proof_root_edges if selected else False
            ),
            root_choice_changed_by_exact=None,
            root_choice_change_requires_paired_baseline=True,
        )

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        self._reset_proof_context()
        started = time.perf_counter()
        self._proof_turn_deadline = started + self.time_limit_sec
        try:
            scale = position_scale(
                state, self.adaptive_config.exact_max_state_estimate
            )
            eligible, reason = self._exact_eligible(scale)
            root_eligible = (
                eligible
                and scale.legal_edge_types
                >= self.adaptive_config.frontier_exact_min_legal_edge_types
            )
            if root_eligible:
                self._proof_counters["root_attempts"] += 1
                exact = self._try_exact(state, scale, started)
                if exact is not None and exact.extra.get(
                    "exact_success_count"
                ):
                    self._proof_counters["completed"] += 1
                    states = int(exact.extra.get("exact_state_count", 0))
                    trivial = states <= 1
                    self._proof_counters[
                        "trivial_successes"
                        if trivial
                        else "nontrivial_successes"
                    ] += 1
                    self._proof_exact_elapsed += exact.elapsed_time_sec
                    self._record_proof_event(
                        {
                            "location": "root",
                            "ply": 0,
                            "normal_search_depth": self._effective_depth(),
                            "status": "complete",
                            "result": exact.extra.get("exact_result", ""),
                            "searched_states": states,
                            "elapsed_time_sec": exact.elapsed_time_sec,
                            "memo_hit": False,
                            "multiple_legal_edges": (
                                scale.legal_edge_types > 1
                            ),
                            "trivial": trivial,
                            "normal_score": None,
                            "exact_score": exact.score,
                            "score_difference": None,
                            "fallback": "none",
                            **asdict(scale),
                        }
                    )
                    return self._proof_extra(exact)
                if exact is not None:
                    was_timeout = bool(
                        exact.extra.get("exact_timeout_count")
                    )
                    self._proof_counters["interrupted"] += 1
                    self._proof_counters["timeouts"] += int(was_timeout)
                    self._proof_counters["fallbacks"] += 1
                    self._proof_exact_elapsed += exact.elapsed_time_sec
                    self._record_proof_event(
                        {
                            "location": "root",
                            "ply": 0,
                            "normal_search_depth": self._effective_depth(),
                            "status": "interrupted",
                            "result": "unknown",
                            "searched_states": int(
                                exact.extra.get("exact_state_count", 0)
                            ),
                            "elapsed_time_sec": exact.elapsed_time_sec,
                            "time_budget_sec": exact.extra.get(
                                "exact_time_budget_sec", 0.0
                            ),
                            "memo_hit": False,
                            "multiple_legal_edges": (
                                scale.legal_edge_types > 1
                            ),
                            "trivial": False,
                            "normal_score": None,
                            "exact_score": None,
                            "score_difference": None,
                            "fallback": "beam_alpha_beta",
                            **asdict(scale),
                        }
                    )
            else:
                gate_reason = (
                    reason
                    if not eligible
                    else "too_few_root_legal_edge_types"
                )
                self._proof_counters["ineligible"] += 1
                self._proof_ineligible_reasons[gate_reason] = (
                    self._proof_ineligible_reasons.get(gate_reason, 0) + 1
                )
            decision = BeamAlphaBetaAgent.choose_edge(self, state)
            decision = _extra_decision(
                decision,
                search_mode="proof_extension_beam_alpha_beta",
                mode_counts={"proof_extension_beam_alpha_beta": 1},
                exact_gate={
                    "eligible": root_eligible,
                    "reason": (
                        reason
                        if root_eligible or not eligible
                        else "too_few_root_legal_edge_types"
                    ),
                    **asdict(scale),
                },
            )
            return self._proof_extra(decision)
        finally:
            self._proof_turn_deadline = None


class SelectiveProofAlphaBetaAgent(
    _ExactEndgameMixin,
    BeamAlphaBetaAgent,
):
    """Run normal BeamAlphaBeta, then prove only competitive root candidates."""

    name = "selective_proof_alpha_beta"

    def __init__(
        self,
        *args: object,
        adaptive_config: AdaptiveHybridConfig = AdaptiveHybridConfig(),
        **kwargs: object,
    ) -> None:
        self.adaptive_config = adaptive_config
        self._selective_normal_deadline: float | None = None
        super().__init__(*args, **kwargs)

    def _deadline(self) -> float:
        if self._selective_normal_deadline is not None:
            return self._selective_normal_deadline
        return super()._deadline()

    def _proof_candidates(
        self,
        decision: EdgeMoveDecision,
    ) -> list[tuple[tuple[int, int], float]]:
        rows = [
            (
                (int(row["start_id"]), int(row["end_id"])),
                float(row["score"]),
            )
            for row in decision.extra.get("root_search_scores", [])
        ]
        rows.sort(key=lambda item: (-item[1], item[0][0], item[0][1]))
        if not rows:
            return []
        best_score = rows[0][1]
        competitive = [
            item
            for item in rows
            if item[1]
            >= best_score - self.adaptive_config.selective_proof_score_margin
        ]
        limit = self.adaptive_config.selective_proof_candidate_limit
        return (competitive if len(competitive) >= 2 else rows)[:limit]

    def _prove_root_candidate(
        self,
        state: AIEdgeState,
        edge: tuple[int, int],
        normal_score: float,
        budget: float,
    ) -> dict[str, object]:
        started = time.perf_counter()
        state.apply_edge(*edge)
        try:
            scale = position_scale(
                state, self.adaptive_config.exact_max_state_estimate
            )
            common = {
                "location": "root_candidate",
                "ply": 1,
                "target_candidate": list(edge),
                "normal_score": normal_score,
                "multiple_root_candidates": True,
                **asdict(scale),
            }
            if edge_is_terminal(state, edge[1]):
                return {
                    **common,
                    "status": "complete",
                    "result": "loss",
                    "exact_score": LOSS_SCORE + 1.0,
                    "score_difference": LOSS_SCORE + 1.0 - normal_score,
                    "searched_states": 0,
                    "elapsed_time_sec": time.perf_counter() - started,
                    "time_budget_sec": budget,
                    "trivial": True,
                }
            eligible, reason = self._exact_eligible(scale)
            if not eligible:
                return {
                    **common,
                    "status": "ineligible",
                    "reason": reason,
                    "result": "unknown",
                    "exact_score": None,
                    "score_difference": None,
                    "searched_states": 0,
                    "elapsed_time_sec": time.perf_counter() - started,
                    "time_budget_sec": budget,
                    "trivial": False,
                }
            if state.required_char_id is None:
                raise AssertionError("candidate successor must require a char")
            solver = ShiritoriSolver(
                self._residual_dictionary(state),
                max_states=self.adaptive_config.exact_max_states,
                timeout_sec=budget,
            )
            try:
                opponent_is_winning = solver.solve(state.required_char_id)
            except AnalysisLimitExceeded as exc:
                return {
                    **common,
                    "status": "interrupted",
                    "limit_reason": exc.reason,
                    "result": "unknown",
                    "exact_score": None,
                    "score_difference": None,
                    "searched_states": solver.count_states(),
                    "elapsed_time_sec": time.perf_counter() - started,
                    "time_budget_sec": budget,
                    "trivial": False,
                }
            root_is_winning = not opponent_is_winning
            exact_score = (
                WIN_SCORE - 1.0
                if root_is_winning
                else LOSS_SCORE + 1.0
            )
            return {
                **common,
                "status": "complete",
                "result": "win" if root_is_winning else "loss",
                "exact_score": exact_score,
                "score_difference": exact_score - normal_score,
                "searched_states": solver.count_states(),
                "elapsed_time_sec": time.perf_counter() - started,
                "time_budget_sec": budget,
                "trivial": solver.count_states() <= 1,
            }
        finally:
            state.undo_edge()

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        turn_started = time.perf_counter()
        total_deadline = turn_started + self.time_limit_sec
        exact_limit = min(
            self.adaptive_config.exact_time_cap_sec,
            self.time_limit_sec * self.adaptive_config.exact_time_fraction,
        )
        self._selective_normal_deadline = total_deadline - exact_limit
        try:
            normal = BeamAlphaBetaAgent.choose_edge(self, state)
        finally:
            self._selective_normal_deadline = None

        candidates = self._proof_candidates(normal)
        events: list[dict[str, object]] = []
        exact_elapsed = 0.0
        for edge, score in candidates[
            : self.adaptive_config.selective_proof_max_calls
        ]:
            remaining = min(
                exact_limit - exact_elapsed,
                total_deadline - time.perf_counter(),
            )
            if remaining <= 0:
                events.append(
                    {
                        "location": "root_candidate",
                        "ply": 1,
                        "target_candidate": list(edge),
                        "normal_score": score,
                        "status": "interrupted",
                        "limit_reason": "no_exact_time_budget",
                        "result": "unknown",
                        "multiple_root_candidates": len(candidates) > 1,
                    }
                )
                break
            event = self._prove_root_candidate(
                state, edge, score, remaining
            )
            events.append(event)
            exact_elapsed += float(event.get("elapsed_time_sec", 0.0))

        exact_results = {
            tuple(int(value) for value in event["target_candidate"]): str(
                event["result"]
            )
            for event in events
            if event.get("status") == "complete"
        }
        baseline = (
            (normal.start_id, normal.end_id)
            if normal.start_id is not None and normal.end_id is not None
            else None
        )
        # Incomplete and ineligible analyses are observational only.  Preserve
        # the normal result unless a completed proof establishes a strict
        # win/loss priority.
        selected = baseline
        ranked = self._proof_candidates(normal)
        proven_wins = [
            edge
            for edge, _score in ranked
            if exact_results.get(edge) == "win"
        ]
        if proven_wins:
            selected = proven_wins[0]
        elif baseline is not None and exact_results.get(baseline) == "loss":
            selected = next(
                (
                    edge
                    for edge, _score in ranked
                    if exact_results.get(edge) != "loss"
                ),
                baseline,
            )
        elapsed = time.perf_counter() - turn_started
        completed = [
            event for event in events if event.get("status") == "complete"
        ]
        nontrivial = [
            event for event in completed if not event.get("trivial")
        ]
        interrupted = [
            event for event in events if event.get("status") == "interrupted"
        ]
        extra = {
            **normal.extra,
            "search_mode": self.name,
            "selective_proof": True,
            "normal_search_elapsed_time_sec": normal.elapsed_time_sec,
            "exact_call_events": events,
            "exact_attempt_count": len(
                [
                    event
                    for event in events
                    if event.get("status") != "ineligible"
                ]
            ),
            "exact_success_count": len(completed),
            "exact_nontrivial_success_count": len(nontrivial),
            "exact_trivial_success_count": len(completed) - len(nontrivial),
            "exact_limit_count": len(interrupted),
            "exact_timeout_count": sum(
                str(event.get("limit_reason", "")).startswith("timeout")
                for event in interrupted
            ),
            "exact_total_time_sec": exact_elapsed,
            "exact_time_budget_sec": exact_limit,
            "selective_proof_candidate_count": len(candidates),
            "selective_proof_candidates": [
                [edge[0], edge[1]] for edge, _score in candidates
            ],
            "root_choice_changed_by_exact": selected != baseline,
            "normal_root_choice": list(baseline) if baseline else None,
            "exact_root_choice": list(selected) if selected else None,
        }
        return EdgeMoveDecision(
            selected[0] if selected else None,
            selected[1] if selected else None,
            elapsed,
            normal.timed_out,
            (
                next(
                    (
                        float(event["exact_score"])
                        for event in completed
                        if tuple(event["target_candidate"]) == selected
                    ),
                    normal.score,
                )
                if selected
                else normal.score
            ),
            extra,
        )


class DynamicProofExtensionBeamAlphaBetaAgent(
    _DynamicBeamMixin,
    ProofExtensionBeamAlphaBetaAgent,
):
    """Corrected dynamic BeamAlphaBeta plus frontier exact proofs."""

    name = "dynamic_proof_extension_beam_alpha_beta"

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        decision = super().choose_edge(state)
        return _extra_decision(decision, **self._dynamic_extra())


class IntegratedAdaptiveHybridAgent(
    _ExactEndgameMixin,
    ResearchAdaptiveBeamAgent,
):
    """Exact endgame + low-branch full AB + adaptive PVS/BeamAlphaBeta."""

    name = "integrated_adaptive_hybrid"
    low_branch_uses_full_alpha = True

    def __init__(
        self,
        *args: object,
        adaptive_config: AdaptiveHybridConfig = AdaptiveHybridConfig(),
        **kwargs: object,
    ) -> None:
        self._last_exact_gate: dict[str, object] = {}
        super().__init__(*args, adaptive_config=adaptive_config, **kwargs)

    def choose_edge(self, state: AIEdgeState) -> EdgeMoveDecision:
        started = time.perf_counter()
        scale = position_scale(
            state, self.adaptive_config.exact_max_state_estimate
        )
        exact = self._try_exact(state, scale, started)
        if exact is not None:
            return exact
        decision = super().choose_edge(state)
        return self._attach_exact_gate(decision, scale)


ADAPTIVE_HYBRID_AGENT_NAMES = (
    "branch_switch_alpha_beta",
    "dynamic_beam_alpha_beta",
    "dynamic_beam_pvs",
    "research_adaptive_beam",
    "endgame_exact_hybrid",
    "proof_extension_beam_alpha_beta",
    "dynamic_proof_extension_beam_alpha_beta",
    "integrated_adaptive_hybrid",
    "score_gap_dynamic_beam_alpha_beta",
    "selective_proof_alpha_beta",
)


def build_adaptive_hybrid_agent(
    name: str,
    *,
    adaptive_config: AdaptiveHybridConfig | None = None,
    **kwargs: Any,
):
    config = adaptive_config or AdaptiveHybridConfig()
    classes = {
        "branch_switch_alpha_beta": BranchSwitchAlphaBetaAgent,
        "dynamic_beam_alpha_beta": DynamicBeamAlphaBetaAgent,
        "dynamic_beam_pvs": DynamicBeamPVSAgent,
        "research_adaptive_beam": ResearchAdaptiveBeamAgent,
        "endgame_exact_hybrid": EndgameExactHybridAgent,
        "proof_extension_beam_alpha_beta": ProofExtensionBeamAlphaBetaAgent,
        "dynamic_proof_extension_beam_alpha_beta": (
            DynamicProofExtensionBeamAlphaBetaAgent
        ),
        "integrated_adaptive_hybrid": IntegratedAdaptiveHybridAgent,
        "score_gap_dynamic_beam_alpha_beta": (
            ScoreGapDynamicBeamAlphaBetaAgent
        ),
        "selective_proof_alpha_beta": SelectiveProofAlphaBetaAgent,
    }
    try:
        cls = classes[name]
    except KeyError as exc:
        raise ValueError(f"unknown adaptive hybrid: {name}") from exc
    return cls(adaptive_config=config, **kwargs)


def add_adaptive_hybrid_cli_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    defaults = AdaptiveHybridConfig()

    def positive_int_csv(value: str) -> tuple[int, ...]:
        try:
            widths = tuple(
                int(item.strip())
                for item in value.split(",")
                if item.strip()
            )
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "widths must be comma-separated integers"
            ) from exc
        if not widths or any(width <= 0 for width in widths):
            raise argparse.ArgumentTypeError("widths must be positive")
        return widths

    parser.add_argument(
        "--branch-switch-threshold",
        type=int,
        default=defaults.branch_switch_threshold,
    )
    parser.add_argument(
        "--dynamic-no-prune-threshold",
        type=int,
        default=defaults.no_prune_threshold,
    )
    parser.add_argument(
        "--dynamic-medium-threshold",
        type=int,
        default=defaults.medium_branch_threshold,
    )
    parser.add_argument(
        "--dynamic-high-threshold",
        type=int,
        default=defaults.high_branch_threshold,
    )
    parser.add_argument(
        "--dynamic-medium-width",
        type=int,
        default=defaults.medium_beam_width,
    )
    parser.add_argument(
        "--dynamic-high-width",
        type=int,
        default=defaults.high_beam_width,
    )
    parser.add_argument(
        "--dynamic-very-high-width",
        type=int,
        default=defaults.very_high_beam_width,
    )
    parser.add_argument(
        "--dynamic-ply-width-caps",
        type=positive_int_csv,
        default=defaults.ply_width_caps,
    )
    parser.add_argument(
        "--iterative-start-depth",
        type=int,
        default=defaults.iterative_start_depth,
    )
    parser.add_argument(
        "--pvs-research-threshold",
        type=float,
        default=defaults.pvs_research_rate_threshold,
    )
    parser.add_argument(
        "--pvs-time-growth-limit",
        type=float,
        default=defaults.pvs_time_growth_limit,
    )
    parser.add_argument(
        "--next-depth-safety-ratio",
        type=float,
        default=defaults.next_depth_safety_ratio,
    )
    parser.add_argument(
        "--exact-max-reachable-words",
        type=int,
        default=defaults.exact_max_reachable_words,
    )
    parser.add_argument(
        "--exact-max-edge-types",
        type=int,
        default=defaults.exact_max_edge_types,
    )
    parser.add_argument(
        "--exact-max-vertices",
        type=int,
        default=defaults.exact_max_vertices,
    )
    parser.add_argument(
        "--exact-max-state-estimate",
        type=int,
        default=defaults.exact_max_state_estimate,
    )
    parser.add_argument(
        "--exact-max-states",
        type=int,
        default=defaults.exact_max_states,
    )
    parser.add_argument(
        "--exact-time-fraction",
        type=float,
        default=defaults.exact_time_fraction,
    )
    parser.add_argument(
        "--exact-time-cap-sec",
        type=float,
        default=defaults.exact_time_cap_sec,
    )
    parser.add_argument(
        "--exact-normal-time-reserve-sec",
        type=float,
        default=defaults.exact_normal_time_reserve_sec,
    )
    parser.add_argument(
        "--frontier-exact-min-legal-edge-types",
        type=int,
        default=defaults.frontier_exact_min_legal_edge_types,
    )
    parser.add_argument(
        "--exact-event-log-limit",
        type=int,
        default=defaults.exact_event_log_limit,
    )
    parser.add_argument(
        "--score-gap-wide-threshold",
        type=float,
        default=defaults.score_gap_wide_threshold,
    )
    parser.add_argument(
        "--score-gap-narrow-threshold",
        type=float,
        default=defaults.score_gap_narrow_threshold,
    )
    parser.add_argument(
        "--score-gap-min-widths",
        type=positive_int_csv,
        default=defaults.score_gap_min_widths,
    )
    parser.add_argument(
        "--score-gap-max-widths",
        type=positive_int_csv,
        default=defaults.score_gap_max_widths,
    )
    parser.add_argument(
        "--selective-proof-candidate-limit",
        type=int,
        default=defaults.selective_proof_candidate_limit,
    )
    parser.add_argument(
        "--selective-proof-score-margin",
        type=float,
        default=defaults.selective_proof_score_margin,
    )
    parser.add_argument(
        "--selective-proof-max-calls",
        type=int,
        default=defaults.selective_proof_max_calls,
    )


def adaptive_hybrid_config_from_args(
    args: argparse.Namespace,
) -> AdaptiveHybridConfig:
    return AdaptiveHybridConfig(
        branch_switch_threshold=args.branch_switch_threshold,
        no_prune_threshold=args.dynamic_no_prune_threshold,
        medium_branch_threshold=args.dynamic_medium_threshold,
        high_branch_threshold=args.dynamic_high_threshold,
        medium_beam_width=args.dynamic_medium_width,
        high_beam_width=args.dynamic_high_width,
        very_high_beam_width=args.dynamic_very_high_width,
        ply_width_caps=tuple(args.dynamic_ply_width_caps),
        iterative_start_depth=args.iterative_start_depth,
        pvs_research_rate_threshold=args.pvs_research_threshold,
        pvs_time_growth_limit=args.pvs_time_growth_limit,
        next_depth_safety_ratio=args.next_depth_safety_ratio,
        exact_max_reachable_words=args.exact_max_reachable_words,
        exact_max_edge_types=args.exact_max_edge_types,
        exact_max_vertices=args.exact_max_vertices,
        exact_max_state_estimate=args.exact_max_state_estimate,
        exact_max_states=args.exact_max_states,
        exact_time_fraction=args.exact_time_fraction,
        exact_time_cap_sec=args.exact_time_cap_sec,
        exact_normal_time_reserve_sec=args.exact_normal_time_reserve_sec,
        frontier_exact_min_legal_edge_types=(
            args.frontier_exact_min_legal_edge_types
        ),
        exact_event_log_limit=args.exact_event_log_limit,
        score_gap_wide_threshold=args.score_gap_wide_threshold,
        score_gap_narrow_threshold=args.score_gap_narrow_threshold,
        score_gap_min_widths=tuple(args.score_gap_min_widths),
        score_gap_max_widths=tuple(args.score_gap_max_widths),
        selective_proof_candidate_limit=(
            args.selective_proof_candidate_limit
        ),
        selective_proof_score_margin=args.selective_proof_score_margin,
        selective_proof_max_calls=args.selective_proof_max_calls,
    )
