import argparse
import json
import math
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = DATA_DIR / "data" / "runs.sqlite"
DEFAULT_RUNS_DIR = DATA_DIR / "runs"


def find_code_dir() -> Path:
    for path in BASE_DIR.iterdir():
        if path.is_dir() and (path / "copy_scorer_soft_ensemble.py").exists():
            return path
    raise SystemExit("copy_scorer_soft_ensemble.py가 있는 운영 코드 폴더를 찾지 못했습니다.")


CODE_DIR = find_code_dir()
sys.path.insert(0, str(CODE_DIR))

from copy_scorer_soft_ensemble import CopyScorerSoftEnsemble


def decode_json(value, default):
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def load_posts(conn, run_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT *
        FROM source_posts
        WHERE run_id = ? AND status = 'completed'
        ORDER BY row_index
        """,
        conn,
        params=(run_id,),
    )


def load_candidates(conn, run_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT rowid AS db_rowid, *
        FROM raw_candidates
        WHERE run_id = ?
          AND accepted_after_filter = 1
          AND COALESCE(cleaned_copy, '') <> ''
        ORDER BY row_index, db_rowid
        """,
        conn,
        params=(run_id,),
    )


def original_rank_from_post(post: pd.Series) -> int | None:
    meta = decode_json(post.get("optimization_meta_json"), {})
    value = meta.get("original_rank")
    try:
        return int(value)
    except Exception:
        return None


def choose_candidates(df: pd.DataFrame, row_index: int, count: int, version_label: str) -> pd.DataFrame:
    selected = (
        df[df["row_index"] == row_index]
        .sort_values(["db_rowid"], kind="mergesort")
        .head(count)
        .copy()
    )
    selected["compare_version"] = version_label
    return selected


def edge_rows(meta: dict, pool: pd.DataFrame, row_index: int, url: str, edge_type: str) -> list[dict]:
    rows = []
    edges = meta.get(f"{edge_type}_edges", [])
    for winner, loser, margin in edges:
        winner_row = pool.iloc[int(winner)]
        loser_row = pool.iloc[int(loser)]
        rows.append(
            {
                "row_index": row_index,
                "url": url,
                "edge_type": edge_type,
                "winner_version": winner_row["compare_version"],
                "loser_version": loser_row["compare_version"],
                "winner_candidate_id": winner_row["candidate_id"],
                "loser_candidate_id": loser_row["candidate_id"],
                "margin": float(margin),
                "is_cross_version": winner_row["compare_version"] != loser_row["compare_version"],
            }
        )
    return rows


def summarize_edges(edges: list[dict], challenger_label: str, baseline_label: str, edge_type: str) -> dict:
    typed = [row for row in edges if row["edge_type"] == edge_type and row["is_cross_version"]]
    challenger_wins = [
        row for row in typed
        if row["winner_version"] == challenger_label and row["loser_version"] == baseline_label
    ]
    baseline_wins = [
        row for row in typed
        if row["winner_version"] == baseline_label and row["loser_version"] == challenger_label
    ]
    return {
        f"{edge_type}_cross_total": len(typed),
        f"{edge_type}_challenger_wins": len(challenger_wins),
        f"{edge_type}_baseline_wins": len(baseline_wins),
        f"{edge_type}_challenger_win_share": len(challenger_wins) / len(typed) if typed else None,
        f"{edge_type}_challenger_avg_margin": (
            sum(row["margin"] for row in challenger_wins) / len(challenger_wins)
            if challenger_wins else None
        ),
        f"{edge_type}_baseline_avg_margin": (
            sum(row["margin"] for row in baseline_wins) / len(baseline_wins)
            if baseline_wins else None
        ),
    }


def compare_row(
    scorer: CopyScorerSoftEnsemble,
    row_index: int,
    url: str,
    baseline_candidates: pd.DataFrame,
    challenger_candidates: pd.DataFrame,
    baseline_label: str,
    challenger_label: str,
) -> tuple[dict, list[dict], list[dict]]:
    usable_count = min(len(baseline_candidates), len(challenger_candidates))
    if usable_count <= 0:
        raise ValueError(f"row_index={row_index} 비교 가능한 후보가 없습니다.")

    base = baseline_candidates.head(usable_count).copy()
    chal = challenger_candidates.head(usable_count).copy()
    base["compare_version"] = baseline_label
    chal["compare_version"] = challenger_label
    pool = pd.concat([base, chal], ignore_index=True)
    texts = pool["cleaned_copy"].fillna("").astype(str).tolist()

    gate_scores, meta = scorer._confidence_gate_scores(texts)
    order, strong_cycle = scorer._order_with_strong_edges(gate_scores, meta["strong_edges"])

    rank_by_local = {local_idx: rank + 1 for rank, local_idx in enumerate(order)}
    ranking_rows = []
    for local_idx, row in pool.iterrows():
        ranking_rows.append(
            {
                "row_index": row_index,
                "url": url,
                "gate_rank": rank_by_local[int(local_idx)],
                "compare_version": row["compare_version"],
                "candidate_id": row["candidate_id"],
                "source_final_rank": row["final_rank"],
                "source_total_score": row["final_total_score"],
                "gate_score": float(gate_scores[int(local_idx)]),
                "claimed_wins": int(meta["claimed_wins"][int(local_idx)]),
                "claimed_losses": int(meta["claimed_losses"][int(local_idx)]),
                "strong_wins": int(meta["strong_wins"][int(local_idx)]),
                "strong_losses": int(meta["strong_losses"][int(local_idx)]),
                "cleaned_copy": row["cleaned_copy"],
            }
        )

    ranking_rows.sort(key=lambda row: row["gate_rank"])
    top50_n = math.ceil(len(pool) * 0.5)
    top5_n = min(5, len(pool))
    top50 = ranking_rows[:top50_n]
    top5 = ranking_rows[:top5_n]
    challenger_top50 = sum(1 for row in top50 if row["compare_version"] == challenger_label)
    challenger_top5 = sum(1 for row in top5 if row["compare_version"] == challenger_label)

    edges = []
    edges.extend(edge_rows(meta, pool, row_index, url, "claimed"))
    edges.extend(edge_rows(meta, pool, row_index, url, "strong"))

    summary = {
        "row_index": row_index,
        "url": url,
        "used_candidates_per_version": usable_count,
        "battle_count_per_candidate": len(pool) - 1,
        "top50_slots": top50_n,
        "challenger_top50_count": challenger_top50,
        "challenger_top50_share": challenger_top50 / top50_n if top50_n else 0.0,
        "top5_slots": top5_n,
        "challenger_top5_count": challenger_top5,
        "challenger_top5_share": challenger_top5 / top5_n if top5_n else 0.0,
        "top50_success": challenger_top50 / top50_n >= 0.9 if top50_n else False,
        "top5_success": challenger_top5 >= 4 if top5_n == 5 else False,
        "strong_cycle": bool(strong_cycle),
        "top1_version": ranking_rows[0]["compare_version"] if ranking_rows else "",
        "top1_candidate_id": ranking_rows[0]["candidate_id"] if ranking_rows else "",
        "top1_copy": ranking_rows[0]["cleaned_copy"] if ranking_rows else "",
    }
    summary.update(summarize_edges(edges, challenger_label, baseline_label, "claimed"))
    summary.update(summarize_edges(edges, challenger_label, baseline_label, "strong"))
    return summary, ranking_rows, edges


def write_markdown(
    path: Path,
    aggregate: dict,
    per_row: pd.DataFrame,
    original_rows: pd.DataFrame,
    baseline_label: str,
    challenger_label: str,
):
    lines = [
        f"# Prompt Compare: {baseline_label} vs {challenger_label}",
        "",
        "## Verdict",
        f"- aggregate_success: {aggregate['aggregate_success']}",
        f"- strict_all_rows_success: {aggregate['strict_all_rows_success']}",
        f"- top50 challenger share: {aggregate['challenger_top50_share']:.3f} ({aggregate['challenger_top50_count']}/{aggregate['top50_slots']})",
        f"- top5 challenger share: {aggregate['challenger_top5_share']:.3f} ({aggregate['challenger_top5_count']}/{aggregate['top5_slots']})",
        f"- rows meeting top50 >= 90%: {aggregate['rows_top50_success']}/{aggregate['row_count']}",
        f"- rows meeting top5 >= 4/5: {aggregate['rows_top5_success']}/{aggregate['row_count']}",
        "",
        "## Original Rank",
        f"- original rank lowered rows: {aggregate['original_rank_lowered_rows']}/{aggregate['row_count']}",
        f"- original rank improved rows: {aggregate['original_rank_improved_rows']}/{aggregate['row_count']}",
        f"- baseline original rank1 rows: {aggregate['baseline_original_rank1_rows']}",
        f"- baseline rank1 cleared by challenger: {aggregate['baseline_rank1_cleared_rows']}/{aggregate['baseline_original_rank1_rows']}",
        "",
        "## Per Row",
        "| row | original legacy -> new | top50 new | top5 new | strong new/base | url |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    original_by_row = original_rows.set_index("row_index")
    for _, row in per_row.sort_values("row_index").iterrows():
        orig = original_by_row.loc[int(row["row_index"])]
        strong = f"{int(row['strong_challenger_wins'])}/{int(row['strong_baseline_wins'])}"
        lines.append(
            f"| {int(row['row_index']) + 1} | "
            f"{orig['baseline_original_rank']} -> {orig['challenger_original_rank']} | "
            f"{row['challenger_top50_count']}/{row['top50_slots']} ({row['challenger_top50_share']:.2f}) | "
            f"{row['challenger_top5_count']}/{row['top5_slots']} | "
            f"{strong} | {row['url']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="두 프롬프트 run을 confidence-gate 전체대결로 비교합니다.")
    parser.add_argument("--baseline-run-id", required=True)
    parser.add_argument("--challenger-run-id", required=True)
    parser.add_argument("--baseline-label", default="legacy_current_v1")
    parser.add_argument("--challenger-label", default="upgrade_v1")
    parser.add_argument("--db-path")
    parser.add_argument("--runs-dir")
    args = parser.parse_args()

    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else DEFAULT_DB_PATH
    runs_dir = Path(args.runs_dir).expanduser().resolve() if args.runs_dir else DEFAULT_RUNS_DIR
    compare_id = (
        f"compare_{args.baseline_label}_vs_{args.challenger_label}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    out_dir = runs_dir / compare_id
    out_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        baseline_posts = load_posts(conn, args.baseline_run_id)
        challenger_posts = load_posts(conn, args.challenger_run_id)
        baseline_candidates = load_candidates(conn, args.baseline_run_id)
        challenger_candidates = load_candidates(conn, args.challenger_run_id)

    common_rows = sorted(set(baseline_posts["row_index"]) & set(challenger_posts["row_index"]))
    if not common_rows:
        raise SystemExit("비교 가능한 공통 row_index가 없습니다.")

    scorer = CopyScorerSoftEnsemble()
    per_row_rows = []
    ranking_rows = []
    edge_rows_all = []
    original_rank_rows = []

    baseline_post_by_row = baseline_posts.set_index("row_index")
    challenger_post_by_row = challenger_posts.set_index("row_index")

    for row_index in common_rows:
        row_index = int(row_index)
        base_post = baseline_post_by_row.loc[row_index]
        chal_post = challenger_post_by_row.loc[row_index]
        url = str(base_post["url"])
        base_cands = baseline_candidates[baseline_candidates["row_index"] == row_index]
        chal_cands = challenger_candidates[challenger_candidates["row_index"] == row_index]
        summary, rankings, edges = compare_row(
            scorer,
            row_index,
            url,
            base_cands,
            chal_cands,
            args.baseline_label,
            args.challenger_label,
        )
        per_row_rows.append(summary)
        ranking_rows.extend(rankings)
        edge_rows_all.extend(edges)

        baseline_rank = original_rank_from_post(base_post)
        challenger_rank = original_rank_from_post(chal_post)
        delta = None
        if baseline_rank is not None and challenger_rank is not None:
            delta = challenger_rank - baseline_rank
        original_rank_rows.append(
            {
                "row_index": row_index,
                "url": url,
                "baseline_original_rank": baseline_rank,
                "challenger_original_rank": challenger_rank,
                "rank_delta_positive_means_original_lower": delta,
                "original_rank_lowered": delta is not None and delta > 0,
                "original_rank_improved": delta is not None and delta < 0,
                "baseline_original_rank1": baseline_rank == 1,
                "baseline_rank1_cleared": baseline_rank == 1 and challenger_rank is not None and challenger_rank > 1,
            }
        )

    per_row = pd.DataFrame(per_row_rows)
    rankings = pd.DataFrame(ranking_rows)
    edges = pd.DataFrame(edge_rows_all)
    original_ranks = pd.DataFrame(original_rank_rows)

    top50_slots = int(per_row["top50_slots"].sum())
    top5_slots = int(per_row["top5_slots"].sum())
    challenger_top50 = int(per_row["challenger_top50_count"].sum())
    challenger_top5 = int(per_row["challenger_top5_count"].sum())
    baseline_rank1_rows = int(original_ranks["baseline_original_rank1"].sum())

    aggregate = {
        "compare_id": compare_id,
        "baseline_run_id": args.baseline_run_id,
        "challenger_run_id": args.challenger_run_id,
        "baseline_label": args.baseline_label,
        "challenger_label": args.challenger_label,
        "row_count": int(len(per_row)),
        "top50_slots": top50_slots,
        "challenger_top50_count": challenger_top50,
        "challenger_top50_share": challenger_top50 / top50_slots if top50_slots else 0.0,
        "top5_slots": top5_slots,
        "challenger_top5_count": challenger_top5,
        "challenger_top5_share": challenger_top5 / top5_slots if top5_slots else 0.0,
        "rows_top50_success": int(per_row["top50_success"].sum()),
        "rows_top5_success": int(per_row["top5_success"].sum()),
        "original_rank_lowered_rows": int(original_ranks["original_rank_lowered"].sum()),
        "original_rank_improved_rows": int(original_ranks["original_rank_improved"].sum()),
        "baseline_original_rank1_rows": baseline_rank1_rows,
        "baseline_rank1_cleared_rows": int(original_ranks["baseline_rank1_cleared"].sum()),
    }
    aggregate["aggregate_success"] = (
        aggregate["challenger_top50_share"] >= 0.9
        and aggregate["challenger_top5_share"] >= 0.8
    )
    aggregate["strict_all_rows_success"] = (
        aggregate["rows_top50_success"] == aggregate["row_count"]
        and aggregate["rows_top5_success"] == aggregate["row_count"]
    )

    summary_df = pd.DataFrame([aggregate])
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    per_row.to_csv(out_dir / "per_row.csv", index=False, encoding="utf-8-sig")
    original_ranks.to_csv(out_dir / "original_ranks.csv", index=False, encoding="utf-8-sig")
    rankings.to_csv(out_dir / "gate_rankings.csv", index=False, encoding="utf-8-sig")
    edges.to_csv(out_dir / "gate_edges.csv", index=False, encoding="utf-8-sig")

    xlsx_path = out_dir / "prompt_compare.xlsx"
    with pd.ExcelWriter(xlsx_path) as writer:
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        per_row.to_excel(writer, sheet_name="per_row", index=False)
        original_ranks.to_excel(writer, sheet_name="original_ranks", index=False)
        rankings.to_excel(writer, sheet_name="gate_rankings", index=False)
        edges.to_excel(writer, sheet_name="gate_edges", index=False)

    write_markdown(
        out_dir / "prompt_compare.md",
        aggregate,
        per_row,
        original_ranks,
        args.baseline_label,
        args.challenger_label,
    )

    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    print(f"output_dir: {out_dir}")


if __name__ == "__main__":
    main()
