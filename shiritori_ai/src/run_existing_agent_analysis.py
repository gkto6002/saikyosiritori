"""Run detailed analysis of existing agents without changing their decisions."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from existing_agent_detailed_analysis import (
    ANALYSIS_ROOT,
    IMPROVEMENT_ROOT,
    aggregate_beam,
    aggregate_length,
    aggregate_matchups,
    aggregate_turn_metrics,
    analyze_beam_reference,
    analyze_caution_survival,
    analyze_dictionaries,
    classify_beam_losses,
    compare_beam_reference_candidates,
    create_plots,
    dictionary_correlations,
    file_sha256,
    fixed_search_efficiency,
    flatten_turns,
    read_jsonl,
    run_counterfactuals,
    run_trace_experiment,
    select_representatives,
    validate_final_matches,
    write_csv,
    write_json,
    write_representative_markdown,
)


STAGES = (
    "validate",
    "traces",
    "matchups",
    "search-efficiency",
    "beam-analysis",
    "risk-analysis",
    "counterfactual",
    "representative-matches",
    "dictionary-analysis",
    "plots",
    "report",
)


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
    ).strip()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--quick", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--stage", choices=("all", *STAGES), default="all")
    parser.add_argument("--input-root", type=Path, default=IMPROVEMENT_ROOT)
    parser.add_argument("--output-root", type=Path, default=ANALYSIS_ROOT)
    return parser.parse_args(argv)


def _load_inputs(input_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    matches_path = input_root / "final/final_matches.json"
    selected_path = input_root / "tuning/selected_settings.json"
    return (
        json.loads(matches_path.read_text(encoding="utf-8")),
        json.loads(selected_path.read_text(encoding="utf-8")),
    )


def _write_stage_rows(root: Path, name: str, value: Any) -> None:
    write_json(root / name / f"{name}.json", value)
    if isinstance(value, list):
        write_csv(root / name / f"{name}.csv", value)


def write_automated_report(output_root: Path, payload: dict[str, Any]) -> Path:
    direct = payload["matchups"]["direct"]
    beam_all = next(
        row
        for row in payload["beam_summary"]
        if row["group_type"] == "all" and row["group"] == "all"
    )
    lines = [
        "# 既存AI詳細分析・自動要約",
        "",
        f"- 基準対局: {payload['baseline_match_count']}",
        f"- 追加トレース: {payload['trace_match_count']}局、"
        f"{payload['trace_turn_count']}手",
        f"- 元勝者一致: {payload['trace_baseline_winner_matches']}/"
        f"{payload['trace_match_count']}",
        f"- 追加トレース内部timeout: {payload['trace_internal_timeout_count']}",
        "",
        "## 主要AI直接対決",
        "",
    ]
    for row in direct:
        lines.append(
            f"- {row['agent']} vs {row['opponent']}: "
            f"{row['wins']}/{row['games']}勝"
        )
    lines.extend(
        [
            "",
            "## Beam参照手保持率（実対局局面）",
            "",
            *[
                f"- top {width}: "
                f"{beam_all[f'top_{width}_reference_retention_rate']:.3%}"
                for width in (2, 4, 6, 8, 12, 16)
            ],
            f"- 幅8外: {payload['beam_dropped_reference_count']}局面",
            f"- 反実仮想で敗北から勝利: "
            f"{payload['counterfactual_outcome_changes']}局面",
            "",
            "## 注意状態",
            "",
            f"- 対象: {len(payload['caution_survival'])}局面",
            f"- 候補間でsurvival scoreが異なる: "
            f"{sum(row['survival_varies'] for row in payload['caution_survival'])}",
            f"- survival込みで静的1位が変化: "
            f"{sum(row['survival_changes_static_best'] for row in payload['caution_survival'])}",
            "",
            "詳細は `docs/agent_analysis/existing_agent_detailed_analysis.md` を参照。",
        ]
    )
    path = output_root / "automated_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def generate_summary(
    input_root: Path,
    output_root: Path,
    *,
    quick: bool,
    requested: tuple[str, ...],
) -> dict[str, Any]:
    matches, selected = _load_inputs(input_root)
    validation = validate_final_matches(matches)
    write_json(output_root / "validation.json", validation)
    if not validation["valid"]:
        raise ValueError(f"invalid final match data: {validation}")

    trace_path = output_root / "traces/final_match_traces.jsonl"
    if "traces" in requested or not trace_path.is_file():
        traces = run_trace_experiment(
            matches, selected, trace_path, quick=quick
        )
    else:
        traces = read_jsonl(trace_path)
    if quick:
        traces = traces[:6]
    turns = flatten_turns(traces)

    matchups = aggregate_matchups(matches)
    length = aggregate_length(matches)
    turn_metrics = aggregate_turn_metrics(turns)
    fixed_efficiency = fixed_search_efficiency(input_root)

    beam_path = output_root / "beam_analysis/beam_positions.jsonl"
    if "beam-analysis" in requested or not beam_path.is_file():
        beam_rows = analyze_beam_reference(traces, beam_path, quick=quick)
    else:
        beam_rows = read_jsonl(beam_path)
    if quick:
        beam_rows = beam_rows[:12]
    beam_summary = aggregate_beam(beam_rows)
    beam_candidate_comparison = compare_beam_reference_candidates(
        traces, beam_rows
    )
    beam_loss_causes = classify_beam_losses(traces, beam_rows)
    caution_survival = analyze_caution_survival(traces)

    counterfactuals = run_counterfactuals(
        traces, beam_rows, selected, quick=quick
    )
    dictionaries = analyze_dictionaries(matches, traces)
    correlations = dictionary_correlations(dictionaries, beam_rows)
    representatives = select_representatives(
        traces, beam_rows, counterfactuals
    )

    for name, rows in matchups.items():
        write_csv(output_root / "matchups" / f"{name}.csv", rows)
        write_json(output_root / "matchups" / f"{name}.json", rows)
    write_csv(output_root / "matchups/length.csv", length)
    write_json(output_root / "matchups/length.json", length)
    for name, rows in turn_metrics.items():
        write_csv(output_root / "search_efficiency" / f"{name}.csv", rows)
        write_json(output_root / "search_efficiency" / f"{name}.json", rows)
    write_csv(output_root / "search_efficiency/fixed.csv", fixed_efficiency["rows"])
    write_json(output_root / "search_efficiency/fixed.json", fixed_efficiency)
    write_csv(
        output_root / "risk_analysis/fixed_move_agreements.csv",
        fixed_efficiency["risk_agreements"],
    )
    write_json(
        output_root / "risk_analysis/fixed_move_agreements.json",
        fixed_efficiency["risk_agreements"],
    )
    write_csv(output_root / "beam_analysis/summary.csv", beam_summary)
    write_json(output_root / "beam_analysis/summary.json", beam_summary)
    missed = [row for row in beam_rows if row["reference_rank"] > 8]
    write_csv(output_root / "beam_analysis/dropped_reference_moves.csv", missed)
    write_json(output_root / "beam_analysis/dropped_reference_moves.json", missed)
    write_csv(
        output_root / "beam_analysis/candidate_comparison.csv",
        beam_candidate_comparison,
    )
    write_json(
        output_root / "beam_analysis/candidate_comparison.json",
        beam_candidate_comparison,
    )
    write_csv(output_root / "beam_analysis/loss_causes.csv", beam_loss_causes)
    write_json(output_root / "beam_analysis/loss_causes.json", beam_loss_causes)
    write_csv(output_root / "counterfactual/counterfactuals.csv", counterfactuals)
    write_json(output_root / "counterfactual/counterfactuals.json", counterfactuals)
    write_csv(output_root / "dictionary_analysis/dictionaries.csv", dictionaries)
    write_json(output_root / "dictionary_analysis/dictionaries.json", dictionaries)
    write_csv(output_root / "dictionary_analysis/correlations.csv", correlations)
    write_json(output_root / "dictionary_analysis/correlations.json", correlations)
    write_json(output_root / "representative_matches/selections.json", representatives)
    write_representative_markdown(
        traces, representatives, output_root / "representative_matches"
    )

    risk_rows = turn_metrics["by_agent_risk"]
    write_csv(output_root / "risk_analysis/by_agent_risk.csv", risk_rows)
    write_json(output_root / "risk_analysis/by_agent_risk.json", risk_rows)
    write_csv(output_root / "risk_analysis/caution_survival.csv", caution_survival)
    write_json(output_root / "risk_analysis/caution_survival.json", caution_survival)

    payload = {
        "mode": "quick" if quick else "full",
        "commit_id": git_commit(),
        "input_hashes": {
            "final_matches": file_sha256(
                input_root / "final/final_matches.json"
            ),
            "selected_settings": file_sha256(
                input_root / "tuning/selected_settings.json"
            ),
        },
        "validation": validation,
        "baseline_match_count": len(matches),
        "trace_match_count": len(traces),
        "trace_turn_count": len(turns),
        "trace_internal_timeout_count": sum(
            bool(turn.get("timed_out")) for turn in turns
        ),
        "trace_baseline_winner_matches": sum(
            trace["matches_baseline_winner"] for trace in traces
        ),
        "trace_baseline_turn_matches": sum(
            trace["matches_baseline_turn_count"] for trace in traces
        ),
        "matchups": matchups,
        "length": length,
        "turn_metrics": turn_metrics,
        "fixed_efficiency": fixed_efficiency,
        "beam_summary": beam_summary,
        "beam_candidate_comparison": beam_candidate_comparison,
        "beam_loss_causes": beam_loss_causes,
        "beam_position_count": len(beam_rows),
        "beam_dropped_reference_count": len(missed),
        "counterfactuals": counterfactuals,
        "counterfactual_outcome_changes": sum(
            row["classification"] == "outcome_improved"
            for row in counterfactuals
        ),
        "dictionaries": dictionaries,
        "dictionary_correlations": correlations,
        "caution_survival": caution_survival,
        "representatives": representatives,
        "selected_settings": selected,
        "limitations": validation["unavailable_without_trace_rerun"],
    }
    write_json(output_root / "summary.json", payload)
    summary_rows = [
        {"metric": "baseline_match_count", "value": len(matches)},
        {"metric": "trace_match_count", "value": len(traces)},
        {"metric": "trace_turn_count", "value": len(turns)},
        {"metric": "beam_position_count", "value": len(beam_rows)},
        {"metric": "beam_dropped_reference_count", "value": len(missed)},
        {
            "metric": "counterfactual_outcome_changes",
            "value": payload["counterfactual_outcome_changes"],
        },
    ]
    write_csv(output_root / "summary.csv", summary_rows)
    if "plots" in requested or "report" in requested:
        payload["plots"] = create_plots(output_root, payload)
        write_json(output_root / "summary.json", payload)
    if "report" in requested:
        write_automated_report(output_root, payload)
    manifest = {
        "commit_id": git_commit(),
        "mode": payload["mode"],
        "input_hashes": payload["input_hashes"],
        "selected_settings": selected,
        "stages": list(requested),
    }
    write_json(output_root / "manifest.json", manifest)
    return payload


def main() -> None:
    args = parse_args()
    requested = STAGES if args.stage == "all" else (args.stage,)
    payload = generate_summary(
        args.input_root,
        args.output_root,
        quick=bool(args.quick),
        requested=requested,
    )
    print(
        f"mode={payload['mode']} matches={payload['baseline_match_count']} "
        f"traces={payload['trace_match_count']} turns={payload['trace_turn_count']} "
        f"output={args.output_root}"
    )


if __name__ == "__main__":
    main()
