"""Interpretable multigraph features for the deterministic GraphControlAgent."""

from __future__ import annotations

import statistics
import time
from dataclasses import asdict, dataclass
from typing import Any

from runtime_state import AIEdgeState


@dataclass(frozen=True)
class GraphControlWeights:
    """Positive weights reward restricting the opponent's residual graph."""

    legal_word_restriction: float = 3.0
    safe_word_restriction: float = 4.0
    dangerous_word_rate: float = 1.0
    reachable_char_restriction: float = 1.5
    reachable_edge_restriction: float = 3.0
    scc_vertex_restriction: float = 1.5
    scc_internal_edge_restriction: float = 2.0
    scc_exit_restriction: float = 1.0
    depth2_restriction: float = 1.0
    depth3_restriction: float = 1.0
    low_out_degree_reach_rate: float = 1.5
    dead_end_reach_rate: float = 2.5
    destination_restriction: float = 1.5
    destination_concentration: float = 1.5


DEFAULT_GRAPH_CONTROL_WEIGHTS = GraphControlWeights()


@dataclass(frozen=True)
class TopologyFeatures:
    reachable_char_ids: frozenset[int]
    scc_char_ids: frozenset[int]
    depth2_char_ids: frozenset[int]
    depth3_char_ids: frozenset[int]
    low_out_degree_reach_rate: float
    dead_end_reach_rate: float
    reachability_time_sec: float
    scc_time_sec: float
    local_time_sec: float


def _iter_bits(mask: int):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def _reachable(adjacency: list[int], start_id: int) -> frozenset[int]:
    visited = 0
    frontier = 1 << start_id
    while frontier:
        visited |= frontier
        next_frontier = 0
        current = frontier
        while current:
            bit = current & -current
            vertex = bit.bit_length() - 1
            next_frontier |= adjacency[vertex]
            current ^= bit
        frontier = next_frontier & ~visited
    return frozenset(_iter_bits(visited))


def _depth_reachable(adjacency: list[int], start_id: int, depth: int) -> frozenset[int]:
    visited = 1 << start_id
    frontier = visited
    for _ in range(depth):
        next_frontier = 0
        current = frontier
        while current:
            bit = current & -current
            vertex = bit.bit_length() - 1
            next_frontier |= adjacency[vertex]
            current ^= bit
        frontier = next_frontier & ~visited
        visited |= next_frontier
    return frozenset(_iter_bits(visited))


def _reverse_adjacency(adjacency: list[int]) -> list[int]:
    reverse = [0] * len(adjacency)
    for start_id, mask in enumerate(adjacency):
        for end_id in _iter_bits(mask):
            reverse[end_id] |= 1 << start_id
    return reverse


def topology_features(state: AIEdgeState, start_id: int) -> TopologyFeatures:
    """Compute topology-only features for the already-mutated state."""

    adjacency = list(state.active_end_masks)
    reach_started = time.perf_counter()
    reachable = _reachable(adjacency, start_id)
    reachability_time = time.perf_counter() - reach_started

    scc_started = time.perf_counter()
    reverse = _reverse_adjacency(adjacency)
    can_reach_start = _reachable(reverse, start_id)
    scc = reachable & can_reach_start
    scc_time = time.perf_counter() - scc_started

    local_started = time.perf_counter()
    depth2 = _depth_reachable(adjacency, start_id, 2)
    depth3 = _depth_reachable(adjacency, start_id, 3)
    n_id = state.edge_dictionary.char_to_id.get("ん")
    low_count = sum(
        state.active_safe_edge_type_counts[char_id] <= 2 for char_id in depth2
    )
    dead_count = sum(
        char_id == n_id or state.active_safe_edge_type_counts[char_id] == 0
        for char_id in depth3
    )
    local_time = time.perf_counter() - local_started
    return TopologyFeatures(
        reachable,
        scc,
        depth2,
        depth3,
        low_count / len(depth2) if depth2 else 1.0,
        dead_count / len(depth3) if depth3 else 1.0,
        reachability_time,
        scc_time,
        local_time,
    )


def _edge_sum_from_starts(state: AIEdgeState, starts: frozenset[int]) -> int:
    return sum(state.remaining_word_counts[start_id] for start_id in starts)


def _scc_edge_counts(
    state: AIEdgeState, members: frozenset[int]
) -> tuple[int, int]:
    internal = 0
    exits = 0
    char_count = state.edge_dictionary.char_count
    for start_id in members:
        row_start = start_id * char_count
        for end_id in _iter_bits(state.active_end_masks[start_id]):
            count = state.edge_counts[row_start + end_id]
            if end_id in members:
                internal += count
            else:
                exits += count
    return internal, exits


def _destination_concentration(state: AIEdgeState, start_id: int) -> float:
    total = state.remaining_word_counts[start_id]
    if total <= 0:
        return 1.0
    char_count = state.edge_dictionary.char_count
    row_start = start_id * char_count
    return sum(
        (state.edge_counts[row_start + end_id] / total) ** 2
        for end_id in _iter_bits(state.active_end_masks[start_id])
    )


def _normalized_score(
    normalized: dict[str, float],
    weights: GraphControlWeights,
) -> float:
    return (
        weights.legal_word_restriction * (1.0 - normalized["legal_word_count"])
        + weights.safe_word_restriction * (1.0 - normalized["safe_word_count"])
        + weights.dangerous_word_rate * normalized["dangerous_word_count"]
        + weights.reachable_char_restriction
        * (1.0 - normalized["reachable_char_count"])
        + weights.reachable_edge_restriction
        * (1.0 - normalized["reachable_edge_count"])
        + weights.scc_vertex_restriction * (1.0 - normalized["scc_vertex_count"])
        + weights.scc_internal_edge_restriction
        * (1.0 - normalized["scc_internal_edge_count"])
        + weights.scc_exit_restriction
        * (1.0 - normalized["scc_exit_edge_count"])
        + weights.depth2_restriction * (1.0 - normalized["depth2_char_count"])
        + weights.depth3_restriction * (1.0 - normalized["depth3_char_count"])
        + weights.low_out_degree_reach_rate
        * normalized["low_out_degree_reach_rate"]
        + weights.dead_end_reach_rate * normalized["dead_end_reach_rate"]
        + weights.destination_restriction
        * (1.0 - normalized["destination_count"])
        + weights.destination_concentration
        * normalized["destination_concentration"]
    )


def evaluate_applied_candidate(
    state: AIEdgeState,
    start_id: int,
    end_id: int,
    topology: TopologyFeatures,
    weights: GraphControlWeights = DEFAULT_GRAPH_CONTROL_WEIGHTS,
) -> dict[str, Any]:
    """Evaluate a candidate after it has already been applied to ``state``."""

    char_count = state.edge_dictionary.char_count
    remaining_total = max(1, sum(state.remaining_word_counts))
    legal = state.remaining_word_counts[end_id]
    safe = state.remaining_safe_word_counts[end_id]
    danger = legal - safe
    internal, exits = _scc_edge_counts(state, topology.scc_char_ids)
    raw = {
        "legal_word_count": legal,
        "safe_word_count": safe,
        "dangerous_word_count": danger,
        "reachable_char_count": len(topology.reachable_char_ids),
        "reachable_edge_count": _edge_sum_from_starts(
            state, topology.reachable_char_ids
        ),
        "scc_vertex_count": len(topology.scc_char_ids),
        "scc_internal_edge_count": internal,
        "scc_exit_edge_count": exits,
        "depth2_char_count": len(topology.depth2_char_ids),
        "depth3_char_count": len(topology.depth3_char_ids),
        "low_out_degree_reach_rate": topology.low_out_degree_reach_rate,
        "dead_end_reach_rate": topology.dead_end_reach_rate,
        "destination_count": state.active_edge_type_counts[end_id],
        "destination_concentration": _destination_concentration(state, end_id),
    }
    normalized = {
        "legal_word_count": legal / remaining_total,
        "safe_word_count": safe / remaining_total,
        "dangerous_word_count": danger / remaining_total,
        "reachable_char_count": len(topology.reachable_char_ids) / char_count,
        "reachable_edge_count": raw["reachable_edge_count"] / remaining_total,
        "scc_vertex_count": len(topology.scc_char_ids) / char_count,
        "scc_internal_edge_count": internal / remaining_total,
        "scc_exit_edge_count": exits / remaining_total,
        "depth2_char_count": len(topology.depth2_char_ids) / char_count,
        "depth3_char_count": len(topology.depth3_char_ids) / char_count,
        "low_out_degree_reach_rate": topology.low_out_degree_reach_rate,
        "dead_end_reach_rate": topology.dead_end_reach_rate,
        "destination_count": state.active_edge_type_counts[end_id] / char_count,
        "destination_concentration": raw["destination_concentration"],
    }
    n_id = state.edge_dictionary.char_to_id.get("ん")
    immediate_loss = end_id == n_id
    immediate_win = not immediate_loss and legal == 0
    base_score = _normalized_score(normalized, weights)
    score = -1_000_000_000.0 if immediate_loss else 1_000_000_000.0 if immediate_win else base_score
    return {
        "start_id": start_id,
        "end_id": end_id,
        "edge_count_after": state.edge_counts[
            state.edge_dictionary.edge_index(start_id, end_id)
        ],
        "remaining_word_count": remaining_total,
        "immediate_win": immediate_win,
        "immediate_loss": immediate_loss,
        "raw": raw,
        "normalized": normalized,
        "score": score,
        "topology_time_sec": (
            topology.reachability_time_sec
            + topology.scc_time_sec
            + topology.local_time_sec
        ),
        "scc_time_sec": topology.scc_time_sec,
        "reachability_time_sec": topology.reachability_time_sec,
        "local_time_sec": topology.local_time_sec,
    }


def candidate_summary(details: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(detail["score"]) for detail in details]
    best = max(scores)
    summary = {
        "candidate_count": len(details),
        "highest_score": best,
        "lowest_score": min(scores),
        "score_range": best - min(scores),
        "score_stddev": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
        "distinct_score_count": len(set(scores)),
        "best_score_tie_count": sum(score == best for score in scores),
        "all_candidates_tied": len(set(scores)) == 1,
    }
    structural_scores = [
        float(detail["score"])
        for detail in details
        if not detail["immediate_win"] and not detail["immediate_loss"]
    ]
    if structural_scores:
        structural_best = max(structural_scores)
        summary.update(
            {
                "structural_candidate_count": len(structural_scores),
                "structural_highest_score": structural_best,
                "structural_lowest_score": min(structural_scores),
                "structural_score_range": structural_best
                - min(structural_scores),
                "structural_score_stddev": (
                    statistics.pstdev(structural_scores)
                    if len(structural_scores) > 1
                    else 0.0
                ),
                "structural_distinct_score_count": len(set(structural_scores)),
                "structural_best_score_tie_count": sum(
                    score == structural_best for score in structural_scores
                ),
                "structural_all_candidates_tied": (
                    len(set(structural_scores)) == 1
                ),
            }
        )
    else:
        summary.update(
            {
                "structural_candidate_count": 0,
                "structural_highest_score": None,
                "structural_lowest_score": None,
                "structural_score_range": 0.0,
                "structural_score_stddev": 0.0,
                "structural_distinct_score_count": 0,
                "structural_best_score_tie_count": 0,
                "structural_all_candidates_tied": True,
            }
        )
    return summary


def weights_dict(weights: GraphControlWeights = DEFAULT_GRAPH_CONTROL_WEIGHTS) -> dict[str, float]:
    return {key: float(value) for key, value in asdict(weights).items()}
