"""Reproduce existing-agent benchmarks, tuning, retention, matches, and report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks"
sys.path.insert(0, str(BENCHMARK_ROOT))

from existing_agents_benchmark import (  # noqa: E402
    benchmark_positions,
    collect_fixed_positions,
    git_commit,
    percentile,
    restore_position,
    write_csv,
)

from agents import (  # noqa: E402
    AlphaBetaAgent,
    BeamNegamaxAgent,
    GreedyAgent,
    MinimaxAgent,
    PVSAgent,
    _edge_sort_key,
)
from match import simulate_runtime_match  # noqa: E402
from runtime_dictionary import RuntimeDictionary  # noqa: E402
from runtime_state import AIEdgeState  # noqa: E402
from search_common import evaluate_ordering_score  # noqa: E402
from existing_agent_analysis import generate_analysis_outputs  # noqa: E402


DEFAULT_RUNTIMES = [
    PROJECT_ROOT / f"data/dictionaries/D20000_L2-12_seed{seed}.runtime.json"
    for seed in (0, 1, 2)
]
STAGES = (
    "positions",
    "benchmark",
    "equal-depth",
    "tuning",
    "beam-retention",
    "final",
    "report",
)


def config_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def source_fingerprint() -> str:
    """Hash executable experiment sources, including uncommitted changes."""

    digest = hashlib.sha256()
    source_paths = sorted((PROJECT_ROOT / "src").glob("*.py")) + sorted(
        (PROJECT_ROOT / "benchmarks").glob("*.py")
    )
    for path in source_paths:
        digest.update(str(path.relative_to(PROJECT_ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def stage_current(output_dir: Path, config: dict[str, Any]) -> bool:
    manifest = output_dir / "manifest.json"
    if not manifest.is_file():
        return False
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    return saved.get("config_hash") == config_hash(config)


def write_manifest(output_dir: Path, config: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "commit_id": git_commit(),
        "source_fingerprint": source_fingerprint(),
        "config": config,
        "config_hash": config_hash(config),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def clone_state(template: AIEdgeState) -> AIEdgeState:
    return AIEdgeState(
        edge_dictionary=template.edge_dictionary,
        required_char_id=template.required_char_id,
        edge_counts=list(template.edge_counts),
        active_end_masks=list(template.active_end_masks),
    )


def tuning_configs(quick: bool) -> list[dict[str, Any]]:
    depths = (3, 4) if quick else (3, 4, 5)
    limits = (8, 12) if quick else (8, 12, 16)
    configs = [
        {
            "config_id": f"{agent}_d{depth}_b{limit}",
            "agent": agent,
            "depth": depth,
            "branch_limit": limit,
        }
        for agent in ("alpha_beta", "pvs")
        for depth in depths
        for limit in limits
    ]
    beam = [
        (4, (12, 8, 4, 2)),
        (5, (12, 8, 4, 2)),
        (5, (16, 10, 6, 3)),
        (5, (8, 6, 4, 2)),
    ]
    if quick:
        beam = beam[:2]
    configs.extend(
        {
            "config_id": f"beam_d{depth}_w{'-'.join(map(str, widths))}",
            "agent": "beam_negamax",
            "depth": depth,
            "beam_widths": widths,
        }
        for depth, widths in beam
    )
    return configs


def build_config_agent(config: dict[str, Any], time_limit_sec: float):
    common = {
        "time_limit_sec": time_limit_sec,
        "depth": int(config["depth"]),
        "adaptive_depth": False,
    }
    if config["agent"] == "alpha_beta":
        return AlphaBetaAgent(
            **common,
            branch_limit=int(config["branch_limit"]),
        )
    if config["agent"] == "pvs":
        return PVSAgent(
            **common,
            branch_limit=int(config["branch_limit"]),
        )
    return BeamNegamaxAgent(
        **common,
        beam_widths=tuple(config["beam_widths"]),
    )


def run_tuning(
    positions: list[dict[str, Any]],
    output_dir: Path,
    quick: bool,
) -> dict[str, Any]:
    repetitions = 1 if quick else 5
    time_limit = 0.25 if quick else 1.0
    train_positions = [row for row in positions if int(row["seed"]) in (0, 1)]
    configs = tuning_configs(quick)
    runs: list[dict[str, Any]] = []
    for config in configs:
        for position in train_positions:
            _runtime, template = restore_position(position)
            for repetition in range(repetitions):
                decision = build_config_agent(config, time_limit).choose_edge(
                    clone_state(template)
                )
                extra = decision.extra
                runs.append(
                    {
                        "config_id": config["config_id"],
                        "agent": config["agent"],
                        "position_id": position["position_id"],
                        "seed": position["seed"],
                        "risk_level": position["risk_level"],
                        "repetition": repetition,
                        "selected_edge": f"{decision.start_id}→{decision.end_id}",
                        "score": decision.score,
                        "elapsed_time_sec": decision.elapsed_time_sec,
                        "timed_out": decision.timed_out,
                        "nodes_searched": extra.get("nodes_searched", 0),
                        "completed_root_moves": extra.get("completed_root_moves", 0),
                        "effective_depth": extra.get("effective_depth", 0),
                    }
                )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in runs:
        grouped[row["config_id"]].append(row)
    summary: list[dict[str, Any]] = []
    for config in configs:
        rows = grouped[config["config_id"]]
        elapsed = [float(row["elapsed_time_sec"]) for row in rows]
        choices: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            choices[row["position_id"]].add(row["selected_edge"])
        summary.append(
            {
                **config,
                "run_count": len(rows),
                "mean_time_sec": statistics.fmean(elapsed),
                "median_time_sec": statistics.median(elapsed),
                "p95_time_sec": percentile(elapsed, 0.95),
                "timeout_rate": statistics.fmean(
                    bool(row["timed_out"]) for row in rows
                ),
                "mean_nodes": statistics.fmean(
                    int(row["nodes_searched"]) for row in rows
                ),
                "mean_completed_root_moves": statistics.fmean(
                    int(row["completed_root_moves"]) for row in rows
                ),
                "mean_effective_depth": statistics.fmean(
                    int(row["effective_depth"]) for row in rows
                ),
                "stable_position_rate": statistics.fmean(
                    len(value) == 1 for value in choices.values()
                ),
            }
        )
    selected: dict[str, dict[str, Any]] = {}
    for agent in ("alpha_beta", "beam_negamax", "pvs"):
        candidates = [row for row in summary if row["agent"] == agent]
        viable = [
            row
            for row in candidates
            if row["timeout_rate"] <= 0.2
            and row["p95_time_sec"] <= time_limit * 1.1
            and row["mean_completed_root_moves"] >= 2
        ] or candidates
        selected[agent] = min(
            viable,
            key=lambda row: (
                row["timeout_rate"],
                -row["stable_position_rate"],
                -row["mean_effective_depth"],
                row["p95_time_sec"],
                row["mean_time_sec"],
            ),
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "quick": quick,
        "time_limit_sec": time_limit,
        "repetitions": repetitions,
        "configs": configs,
        "runs": runs,
        "summary": summary,
        "selected": selected,
    }
    (output_dir / "tuning.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "selected_settings.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_csv(output_dir / "tuning_runs.csv", runs)
    write_csv(output_dir / "tuning_summary.csv", summary)
    return payload


def run_algorithm_variants(
    positions: list[dict[str, Any]],
    output_dir: Path,
    repetitions: int,
    time_limit_sec: float,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    variants = (
        (
            "alpha_beta_full_root_window",
            lambda: AlphaBetaAgent(
                time_limit_sec=time_limit_sec,
                depth=4,
                branch_limit=12,
                adaptive_depth=False,
                share_root_alpha=False,
            ),
        ),
        (
            "alpha_beta_shared_root_alpha",
            lambda: AlphaBetaAgent(
                time_limit_sec=time_limit_sec,
                depth=4,
                branch_limit=12,
                adaptive_depth=False,
                share_root_alpha=True,
            ),
        ),
        (
            "pvs_unit_window",
            lambda: PVSAgent(
                time_limit_sec=time_limit_sec,
                depth=4,
                branch_limit=12,
                adaptive_depth=False,
                null_window_epsilon=1.0,
            ),
        ),
        (
            "pvs_nextafter_window",
            lambda: PVSAgent(
                time_limit_sec=time_limit_sec,
                depth=4,
                branch_limit=12,
                adaptive_depth=False,
                null_window_epsilon=None,
            ),
        ),
    )
    for position in positions:
        _runtime, template = restore_position(position)
        for variant, factory in variants:
            for repetition in range(repetitions):
                decision = factory().choose_edge(clone_state(template))
                rows.append(
                    {
                        "position_id": position["position_id"],
                        "risk_level": position["risk_level"],
                        "variant": variant,
                        "repetition": repetition,
                        "selected_edge": f"{decision.start_id}→{decision.end_id}",
                        "score": decision.score,
                        "elapsed_time_sec": decision.elapsed_time_sec,
                        "nodes_searched": decision.extra.get("nodes_searched", 0),
                        "timed_out": decision.timed_out,
                        "root_alpha_updates": decision.extra.get("root_alpha_updates", 0),
                        "null_window_searches": decision.extra.get("null_window_searches", 0),
                        "research_count": decision.extra.get("research_count", 0),
                    }
                )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["variant"]].append(row)
    summary = [
        {
            "variant": variant,
            "runs": len(values),
            "mean_time_sec": statistics.fmean(
                float(row["elapsed_time_sec"]) for row in values
            ),
            "mean_nodes": statistics.fmean(
                int(row["nodes_searched"]) for row in values
            ),
            "timeout_rate": statistics.fmean(
                bool(row["timed_out"]) for row in values
            ),
            "mean_research_rate": (
                sum(int(row["research_count"]) for row in values)
                / sum(int(row["null_window_searches"]) for row in values)
                if sum(int(row["null_window_searches"]) for row in values)
                else 0.0
            ),
        }
        for variant, values in sorted(grouped.items())
    ]
    by_key = {
        (row["position_id"], row["repetition"], row["variant"]): row for row in rows
    }

    def agreement(left: str, right: str) -> dict[str, Any]:
        pairs = [
            (row, by_key[(row["position_id"], row["repetition"], right)])
            for row in rows
            if row["variant"] == left
        ]
        return {
            "left": left,
            "right": right,
            "pair_count": len(pairs),
            "move_agreement_rate": statistics.fmean(
                left_row["selected_edge"] == right_row["selected_edge"]
                for left_row, right_row in pairs
            ),
            "score_agreement_rate": statistics.fmean(
                math.isclose(
                    float(left_row["score"]),
                    float(right_row["score"]),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                for left_row, right_row in pairs
            ),
        }

    agreements = [
        agreement("alpha_beta_full_root_window", "alpha_beta_shared_root_alpha"),
        agreement("pvs_unit_window", "pvs_nextafter_window"),
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"runs": rows, "summary": summary, "agreements": agreements}
    (output_dir / "algorithm_variants.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_csv(output_dir / "algorithm_variant_runs.csv", rows)
    write_csv(output_dir / "algorithm_variant_summary.csv", summary)
    write_csv(output_dir / "algorithm_variant_agreements.csv", agreements)
    return payload


def run_beam_retention(
    positions: list[dict[str, Any]],
    selected: dict[str, dict[str, Any]],
    output_dir: Path,
    quick: bool,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    widths = (2, 4, 8, 12, 16)
    for position in positions:
        runtime, template = restore_position(position)
        reference = AlphaBetaAgent(
            time_limit_sec=0.5 if quick else 2.0,
            depth=max(4, int(selected["alpha_beta"]["depth"])),
            branch_limit=16,
            adaptive_depth=False,
        ).choose_edge(clone_state(template))
        beam = build_config_agent(
            selected["beam_negamax"],
            0.5 if quick else 2.0,
        ).choose_edge(clone_state(template))
        evaluations = {
            edge: evaluate_ordering_score(clone_state(template), *edge)
            for edge in template.available_edges()
        }
        ordered = sorted(
            evaluations,
            key=lambda edge: _edge_sort_key(edge, evaluations[edge], False),
        )
        reference_edge = (reference.start_id, reference.end_id)
        rank = (
            ordered.index(reference_edge) + 1
            if reference_edge in ordered
            else len(ordered) + 1
        )
        rows.append(
            {
                "position_id": position["position_id"],
                "seed": position["seed"],
                "phase": position["phase"],
                "risk_level": position["risk_level"],
                "reference_edge": f"{reference.start_id}→{reference.end_id}",
                "reference_score": reference.score,
                "reference_timed_out": reference.timed_out,
                "candidate_rank": rank,
                "beam_edge": f"{beam.start_id}→{beam.end_id}",
                "beam_score": beam.score,
                "same_move": reference_edge == (beam.start_id, beam.end_id),
                "score_difference": reference.score - beam.score,
                "win_impact": (
                    "none" if reference_edge == (beam.start_id, beam.end_id) else "unknown"
                ),
                **{f"top_{width}": rank <= width for width in widths},
            }
        )
    aggregate: list[dict[str, Any]] = []
    for risk in ("all", "normal", "caution", "danger", "critical"):
        subset = rows if risk == "all" else [row for row in rows if row["risk_level"] == risk]
        if not subset:
            continue
        aggregate.append(
            {
                "risk_level": risk,
                "position_count": len(subset),
                "same_move_rate": statistics.fmean(bool(row["same_move"]) for row in subset),
                **{
                    f"top_{width}_retention_rate": statistics.fmean(
                        bool(row[f"top_{width}"]) for row in subset
                    )
                    for width in widths
                },
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"positions": rows, "retention": aggregate}
    (output_dir / "beam_retention.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_csv(output_dir / "beam_retention_positions.csv", rows)
    write_csv(output_dir / "beam_retention_summary.csv", aggregate)
    return payload


def available_final_runtimes(quick: bool) -> list[Path]:
    candidates: list[Path] = []
    sizes = (1000, 3000, 5000, 10000, 20000)
    for size in sizes:
        paths = sorted(
            (PROJECT_ROOT / "data/dictionaries").glob(
                f"D{size}_L2-12_seed*.runtime.json"
            )
        )
        candidates.extend(paths)
    if quick:
        seed2 = [path for path in candidates if "D20000_" in path.name and "seed2" in path.name]
        smallest = candidates[:1]
        return smallest + seed2
    return candidates


def build_final_agent(name: str, setting: dict[str, Any], time_limit: float):
    if name == "greedy":
        return GreedyAgent(time_limit_sec=time_limit)
    if name == "minimax":
        return MinimaxAgent(
            time_limit_sec=time_limit,
            depth=3,
            branch_limit=8,
            adaptive_depth=False,
        )
    return build_config_agent(setting, time_limit)


def run_final_matches(
    selected: dict[str, dict[str, Any]],
    output_dir: Path,
    quick: bool,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "final_matches.json"
    rows: list[dict[str, Any]] = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.is_file()
        else []
    )
    completed = {
        (
            row["runtime"],
            row["first_agent"],
            row["second_agent"],
        )
        for row in rows
    }
    runtime_paths = available_final_runtimes(quick)
    for runtime_path in runtime_paths:
        runtime = RuntimeDictionary.load(runtime_path)
        metadata_path = runtime_path.with_name(
            runtime_path.name.removesuffix(".runtime.json") + ".metadata.json"
        )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        size = int(metadata.get("actual_word_count", runtime.word_count))
        seed = int(metadata.get("seed", 0))
        names = ["greedy", "alpha_beta", "beam_negamax", "pvs"]
        if size <= 5000:
            names.append("minimax")
        for first_name, second_name in itertools.permutations(names, 2):
            key = (str(runtime_path), first_name, second_name)
            if key in completed:
                continue
            first_setting = selected.get(first_name, {})
            second_setting = selected.get(second_name, {})
            result = simulate_runtime_match(
                runtime.to_edge_dictionary(),
                build_final_agent(first_name, first_setting, 0.2 if quick else 1.0),
                build_final_agent(second_name, second_setting, 0.2 if quick else 1.0),
                max_moves=100 if quick else 1000,
                max_match_time_sec=30.0 if quick else 300.0,
                match_id=f"D{size}_seed{seed}_{first_name}_vs_{second_name}",
            )
            rows.append(
                {
                    "runtime": str(runtime_path),
                    "dict_size": size,
                    "seed": seed,
                    "first_agent": first_name,
                    "second_agent": second_name,
                    "winner": result.winner,
                    "loss_reason": result.loss_reason,
                    "turn_count": result.turn_count,
                    "first_avg_time_sec": result.first_avg_time_sec,
                    "second_avg_time_sec": result.second_avg_time_sec,
                    "first_timeout_count": result.first_timeout_count,
                    "second_timeout_count": result.second_timeout_count,
                    "match_elapsed_time_sec": result.match_elapsed_time_sec,
                }
            )
            completed.add(key)
            result_path.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            write_csv(output_dir / "final_matches.csv", rows)
    return rows


def generate_report(root: Path) -> Path:
    tuning = json.loads((root / "tuning/tuning.json").read_text(encoding="utf-8"))
    retention = json.loads(
        (root / "beam_retention/beam_retention.json").read_text(encoding="utf-8")
    )
    final_rows = json.loads(
        (root / "final/final_matches.json").read_text(encoding="utf-8")
    )
    analysis = generate_analysis_outputs(root)
    selected = tuning["selected"]
    lines = [
        "# 既存探索AI改善・自動集計レポート",
        "",
        f"- commit: `{git_commit()}`",
        f"- mode: `{'quick' if tuning['quick'] else 'full'}`",
        "",
        "## 選択設定",
        "",
    ]
    for agent, setting in selected.items():
        lines.append(f"- {agent}: `{setting['config_id']}`")
    lines.extend(["", "## Beam参照手保持率", ""])
    for row in retention["retention"]:
        lines.append(
            f"- {row['risk_level']}: top2={row['top_2_retention_rate']:.3f}, "
            f"top4={row['top_4_retention_rate']:.3f}, "
            f"top8={row['top_8_retention_rate']:.3f}, "
            f"top12={row['top_12_retention_rate']:.3f}, "
            f"top16={row['top_16_retention_rate']:.3f}"
        )
    lines.extend(["", "## 最終対局", ""])
    lines.append(f"- 対局数: {len(final_rows)}")
    lines.append(
        f"- 内部タイムアウト: "
        f"{sum(int(row['first_timeout_count']) + int(row['second_timeout_count']) for row in final_rows)}"
    )
    lines.append(
        f"- 試合時間切れ: "
        f"{sum(row['loss_reason'] == 'match_time_limit' for row in final_rows)}"
    )
    lines.extend(["", "## 最終対局のAI別集計", ""])
    for row in analysis["agent_summary"]:
        lines.append(
            f"- {row['agent']}: {row['wins']}/{row['games']}勝 "
            f"(勝率{row['win_rate']:.3f})、平均思考時間"
            f"{row['mean_time_sec']:.6f}秒、内部タイムアウト"
            f"{row['internal_timeout_count']}"
        )
    lines.extend(["", "## 再実行用情報", ""])
    lines.append(f"- source fingerprint: `{source_fingerprint()}`")
    lines.append("- 集計CSV/JSON: `results/existing_agent_improvement/analysis`")
    lines.append("- 図: `results/existing_agent_improvement/figures`")
    report = root / "automated_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--quick", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--stage", choices=("all", *STAGES), default="all")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "results/existing_agent_improvement",
    )
    parser.add_argument("--runtime", nargs="+", type=Path, default=DEFAULT_RUNTIMES)
    parser.add_argument(
        "--reference-match-log",
        type=Path,
        default=PROJECT_ROOT
        / "results/existing_agent_improvement/before/matches/match_logs.jsonl",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    root = args.output_root
    quick = bool(args.quick)
    requested = STAGES if args.stage == "all" else (args.stage,)
    positions_path = root / "fixed_positions.json"
    positions: list[dict[str, Any]]
    if "positions" in requested or not positions_path.is_file():
        positions = collect_fixed_positions(args.runtime, args.reference_match_log)
        root.mkdir(parents=True, exist_ok=True)
        positions_path.write_text(
            json.dumps(positions, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        positions = json.loads(positions_path.read_text(encoding="utf-8"))
    if quick:
        positions = positions[:6]

    if "benchmark" in requested:
        stage_dir = root / "after"
        stage_config = {
            "stage": "benchmark",
            "quick": quick,
            "positions": config_hash(positions),
            "commit_id": git_commit(),
            "source_fingerprint": source_fingerprint(),
        }
        if args.force or not stage_current(stage_dir, stage_config):
            benchmark_positions(
                positions,
                stage_dir / "fixed",
                "current",
                1 if quick else 5,
                0.25 if quick else 1.0,
            )
            run_algorithm_variants(
                positions,
                stage_dir / "algorithm_variants",
                1 if quick else 5,
                0.25 if quick else 1.0,
            )
            write_manifest(stage_dir, stage_config)
        else:
            print("reused stage=benchmark")
    if "equal-depth" in requested:
        stage_dir = root / "equal_depth"
        stage_config = {
            "stage": "equal-depth",
            "quick": quick,
            "positions": config_hash(positions),
            "commit_id": git_commit(),
            "source_fingerprint": source_fingerprint(),
        }
        if args.force or not stage_current(stage_dir, stage_config):
            benchmark_positions(
                positions,
                stage_dir / "fixed",
                "equal_depth",
                1 if quick else 5,
                0.25 if quick else 1.0,
            )
            write_manifest(stage_dir, stage_config)
        else:
            print("reused stage=equal-depth")
    if "tuning" in requested:
        stage_dir = root / "tuning"
        stage_config = {
            "stage": "tuning",
            "quick": quick,
            "positions": config_hash(positions),
            "configs": tuning_configs(quick),
            "commit_id": git_commit(),
            "source_fingerprint": source_fingerprint(),
        }
        if args.force or not stage_current(stage_dir, stage_config):
            run_tuning(positions, stage_dir, quick)
            write_manifest(stage_dir, stage_config)
        else:
            print("reused stage=tuning")
    tuning_path = root / "tuning/tuning.json"
    if any(stage in requested for stage in ("beam-retention", "final", "report")):
        if not tuning_path.is_file():
            raise FileNotFoundError("run the tuning stage first")
        selected = json.loads(tuning_path.read_text(encoding="utf-8"))["selected"]
        if "beam-retention" in requested:
            stage_dir = root / "beam_retention"
            stage_config = {
                "stage": "beam-retention",
                "quick": quick,
                "positions": config_hash(positions),
                "selected": selected,
                "commit_id": git_commit(),
                "source_fingerprint": source_fingerprint(),
            }
            if args.force or not stage_current(stage_dir, stage_config):
                run_beam_retention(positions, selected, stage_dir, quick)
                write_manifest(stage_dir, stage_config)
            else:
                print("reused stage=beam-retention")
        if "final" in requested:
            stage_dir = root / "final"
            stage_config = {
                "stage": "final",
                "quick": quick,
                "selected": selected,
                "runtimes": [str(path) for path in available_final_runtimes(quick)],
                "commit_id": git_commit(),
                "source_fingerprint": source_fingerprint(),
            }
            if args.force or not stage_current(stage_dir, stage_config):
                run_final_matches(selected, stage_dir, quick)
                write_manifest(stage_dir, stage_config)
            else:
                print("reused stage=final")
        if "report" in requested:
            report = generate_report(root)
            print(f"report={report}")
    config = {
        "quick": quick,
        "stage": args.stage,
        "runtimes": [str(path) for path in args.runtime],
        "commit_id": git_commit(),
        "source_fingerprint": source_fingerprint(),
    }
    write_manifest(root / "_last_run", config)
    print(f"completed stage={args.stage} mode={'quick' if quick else 'full'}")


if __name__ == "__main__":
    main()
