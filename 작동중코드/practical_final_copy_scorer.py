from __future__ import annotations

import math
import os
import pickle
import re
import sys
import warnings
from pathlib import Path
from typing import Any, List

import numpy as np
from scipy.sparse import csr_matrix, hstack

from content_guard import DEFAULT_MAX_BODY_LINES, MAX_THREADS_TEXT_LENGTH, get_text_rejection
from copy_scorer_soft_ensemble import CopyScorerSoftEnsemble
from app_config import GlobalConfig

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


DEFAULT_ARTIFACT_PATH = Path(
    os.environ.get(
        "MADOYO_PRACTICAL_SCORER_ARTIFACT",
        str(GlobalConfig.BASE_DIR / "embedding_migration" / "practical_final_copy_scorer_20260527.pkl"),
    )
)


def _zscore(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    sd = float(np.std(arr))
    if sd <= 1e-9:
        return np.zeros_like(arr)
    return (arr - float(np.mean(arr))) / sd


def _sigmoid(raw: np.ndarray) -> np.ndarray:
    raw = np.clip(np.asarray(raw, dtype=np.float64), -40, 40)
    return 1.0 / (1.0 + np.exp(-raw))


def _score_model(model: Any, matrix: Any) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(matrix)[:, 1], dtype=np.float64)
    if hasattr(model, "decision_function"):
        return _sigmoid(model.decision_function(matrix))
    return np.asarray(model.predict(matrix), dtype=np.float64)


def _wf_style_features(texts: list[str]) -> np.ndarray:
    rows = []
    for text in texts:
        stripped = str(text or "").strip()
        lines = stripped.splitlines() or [stripped]
        line_lens = [len(line) for line in lines]
        length = len(stripped)
        spaces = sum(ch.isspace() for ch in stripped)
        hangul = sum(1 for ch in stripped if 0xAC00 <= ord(ch) <= 0xD7A3)
        latin = sum(1 for ch in stripped if ch.isascii() and ch.isalpha())
        digits = sum(ch.isdigit() for ch in stripped)
        emoji_like = sum(ord(ch) > 0xFFFF for ch in stripped)
        rows.append(
            [
                length,
                len(lines),
                length / max(1, len(lines)),
                line_lens[0] if line_lens else 0,
                max(line_lens) if line_lens else 0,
                min(line_lens) if line_lens else 0,
                float(np.std(line_lens)) if line_lens else 0.0,
                spaces,
                hangul,
                latin,
                digits,
                stripped.count("?"),
                stripped.count("!"),
                stripped.count("~"),
                stripped.count(";"),
                stripped.count(","),
                stripped.count("."),
                stripped.count("\n"),
                emoji_like,
                hangul / max(1, length),
                digits / max(1, length),
                spaces / max(1, length),
            ]
        )
    return np.asarray(rows, dtype=np.float32)


def _suite_style_feature_one(text: str) -> np.ndarray:
    text = str(text or "")
    length = max(len(text), 1)
    lines = text.count("\n") + 1
    spaces = sum(1 for ch in text if ch.isspace())
    digits = sum(1 for ch in text if ch.isdigit())
    hangul = len(re.findall(r"[\uac00-\ud7a3]", text))
    ascii_letters = len(re.findall(r"[A-Za-z]", text))
    punct = len(re.findall(r"[^\w\s]", text))
    emojis_or_symbols = len(re.findall(r"[^\w\s,\.\!\?\uac00-\ud7a3]", text))
    return np.asarray(
        [
            length,
            math.log1p(length),
            lines,
            spaces / length,
            digits / length,
            hangul / length,
            ascii_letters / length,
            punct / length,
            emojis_or_symbols / length,
            text.count("#"),
            text.count("@"),
            text.count("?"),
            text.count("!"),
            text.count(","),
            text.count("."),
            text.count("~"),
            text.count('"') + text.count("'"),
            text.count("(") + text.count(")"),
            len(text.split()),
            length / max(lines, 1),
        ],
        dtype=np.float32,
    )


def _suite_style_features(texts: list[str]) -> np.ndarray:
    return np.vstack([_suite_style_feature_one(t) for t in texts]).astype(np.float32)


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-8)


def _hygiene_score(text: str) -> float:
    t = "" if text is None else str(text)
    length = len(t)
    line_count = len([line for line in t.splitlines() if line.strip()])
    score = 0.0
    if length > 200:
        score += min(3.0, (length - 200) / 80.0)
    if length < 35:
        score += (35 - length) / 20.0
    if line_count > 8:
        score += (line_count - 8) * 0.5
    if re.search(r"([^\s])\1{5,}", t):
        score += 3.0
    if "```" in t or re.search(r"\b(?:assistant|system|output|answer|explanation)\s*[:：]", t, re.I):
        score += 3.0
    if re.search(r"https?://|www\.", t, re.I):
        score += 2.0
    hangul = len(re.findall(r"[\uac00-\ud7a3]", t))
    if length and hangul / max(1, length) < 0.35:
        score += 1.0
    punct = len(re.findall(r"[^\w\s]", t))
    if length and punct / max(1, length) > 0.18:
        score += 0.7
    return float(score)


def _batch_relative_features(
    texts: list[str],
    *,
    text_embeddings: np.ndarray,
    multi_embeddings: np.ndarray,
    visual_embeddings: np.ndarray,
) -> np.ndarray:
    text = _l2_normalize(text_embeddings)
    multi = _l2_normalize(multi_embeddings)
    visual = _l2_normalize(visual_embeddings)
    style = _suite_style_features(texts)
    lengths = np.asarray([len(t or "") for t in texts], dtype=np.float64)
    lines = np.asarray([max(1, str(t or "").count("\n") + 1) for t in texts], dtype=np.float64)
    length_z = _zscore(lengths)
    line_z = _zscore(lines)
    rows = []
    for i in range(len(texts)):
        local = [length_z[i], line_z[i], _hygiene_score(texts[i])]
        for mat in [text, multi, visual]:
            centroid = _l2_normalize(mat.mean(axis=0, keepdims=True))[0]
            sims = mat[i] @ mat.T
            if len(texts) > 1:
                siblings = np.delete(sims, i)
                local.extend(
                    [
                        float(mat[i] @ centroid),
                        float(np.mean(siblings)),
                        float(np.max(siblings)),
                        float(np.min(siblings)),
                        float(np.std(siblings)),
                    ]
                )
            else:
                local.extend([float(mat[i] @ centroid), 0.0, 0.0, 0.0, 0.0])
        rows.append(local)
    return np.hstack([style, np.asarray(rows, dtype=np.float32)]).astype(np.float32)


def _bad_rank_percentile(score: np.ndarray) -> np.ndarray:
    score = np.asarray(score, dtype=np.float64)
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score), dtype=np.float64)
    ranks[order] = np.arange(1, len(score) + 1)
    return ranks / max(1, len(score))


def _top_vote_score(score_bank: dict[str, np.ndarray], names: list[str], top_n: int) -> np.ndarray:
    votes = np.zeros(len(next(iter(score_bank.values()))), dtype=np.float64)
    avg_rank = np.zeros_like(votes)
    for name in names:
        score = np.asarray(score_bank[name], dtype=np.float64)
        order = np.argsort(-score, kind="mergesort")
        rank = np.empty(len(score), dtype=np.int32)
        rank[order] = np.arange(1, len(score) + 1)
        votes += (rank <= top_n).astype(np.float64)
        avg_rank += (len(score) - rank + 1) / len(score)
    return votes + 0.01 * avg_rank / max(1, len(names))


class PracticalFinalCopyScorer(CopyScorerSoftEnsemble):
    """Opt-in practical scorer package trained on the 2026-05-27 final policy."""

    def __init__(self, artifact_path: str | os.PathLike[str] | None = None):
        super().__init__()
        self.artifact_path = Path(artifact_path or DEFAULT_ARTIFACT_PATH)
        if not self.artifact_path.exists():
            raise FileNotFoundError(f"Practical scorer artifact not found: {self.artifact_path}")
        with self.artifact_path.open("rb") as f:
            self.practical_artifact = pickle.load(f)

    @staticmethod
    def _copy_hygiene_rejection(text: str) -> dict[str, Any] | None:
        return get_text_rejection(
            text,
            max_length=MAX_THREADS_TEXT_LENGTH,
            reject_repeated=True,
            reject_meta=True,
            reject_urls=True,
            reject_disclosure=True,
            max_lines=DEFAULT_MAX_BODY_LINES,
            min_hangul_chars=5,
        )

    def _ltr_scores(self, texts: list[str]) -> dict[str, Any]:
        ltr = self.practical_artifact["ltr_sidecar"]
        feature_pack = ltr["feature_pack"]
        vectorizer = feature_pack["vectorizer"]
        scaler = feature_pack["style_scaler"]
        x_text = vectorizer.transform(texts)
        style = _wf_style_features(texts)
        x = hstack([x_text, csr_matrix(scaler.transform(style))], format="csr")
        models = ltr["models"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            primary = np.asarray(models["lgbm_lambdarank_primary_median_resid"].predict(x), dtype=np.float64)
            robust = np.asarray(models["lgbm_lambdarank_robust_z"].predict(x), dtype=np.float64)
        cat_model = models.get("cat_yetirank_ndcg_top2_primary")
        if cat_model is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                cat = np.asarray(cat_model.predict(x), dtype=np.float64)
        else:
            cat = np.zeros(len(texts), dtype=np.float64)
        combined = _zscore(primary) + 0.5 * _zscore(robust) + 0.25 * _zscore(cat)
        order = np.argsort(-primary, kind="mergesort")
        gap = 0.0
        if len(order) > 1:
            gap = float(primary[order[0]] - primary[order[1]])
        cal = ltr["calibration"]["primary_median_resid"]
        return {
            "primary": primary,
            "robust": robust,
            "catboost": cat,
            "combined": combined,
            "primary_top_gap": gap,
            "primary_q70": cal.get("score_gap_q70"),
            "primary_q80": cal.get("score_gap_q80"),
        }

    def _qa_bad_scores(
        self,
        texts: list[str],
        *,
        multi_embeddings: np.ndarray | None,
        text_embeddings: np.ndarray | None,
        visual_embeddings: np.ndarray | None,
        existing_binary_bad: np.ndarray | None,
    ) -> dict[str, Any]:
        qa = self.practical_artifact["qa_gate"]
        n = len(texts)
        policy = qa["policy"]
        if n < int(policy["min_candidates_for_learned_drop"]):
            return {"available": False, "reason": "too_few_candidates", "bad_score": np.zeros(n), "rejected_indices": []}
        if multi_embeddings is None or text_embeddings is None or visual_embeddings is None:
            return {"available": False, "reason": "missing_text_multi_visual_embeddings", "bad_score": np.zeros(n), "rejected_indices": []}

        style_batch = _batch_relative_features(
            texts,
            text_embeddings=np.asarray(text_embeddings, dtype=np.float32),
            multi_embeddings=np.asarray(multi_embeddings, dtype=np.float32),
            visual_embeddings=np.asarray(visual_embeddings, dtype=np.float32),
        )
        score_bank: dict[str, np.ndarray] = {}
        models = qa["models"]
        for key in ["tfidf25_style_lr_bad20", "tfidf36_style_lr_bad20"]:
            pack = models[key]
            x_text = pack["vectorizer"].transform(texts)
            x = hstack([x_text, csr_matrix(pack["style_scaler"].transform(style_batch))], format="csr")
            score_bank[key] = _score_model(pack["model"], x)

        dense_pack = models["dense_style_extra_bad40"]
        score_bank["dense_style_extra_bad40"] = _score_model(
            dense_pack["model"],
            dense_pack["style_scaler"].transform(style_batch),
        )

        knn = models["knn_bad20"]
        text_norm = _l2_normalize(np.asarray(text_embeddings, dtype=np.float32))
        sims = text_norm @ np.asarray(knn["text_train"], dtype=np.float32).T
        y = np.asarray(knn["y"], dtype=np.float64)
        k = min(int(knn["k"]), sims.shape[1])
        knn_scores = np.zeros(n, dtype=np.float64)
        for i, row in enumerate(sims):
            idx = np.argpartition(-row, k - 1)[:k]
            weights = np.maximum(row[idx], 0.0) + 1e-4
            knn_scores[i] = float(np.average(y[idx], weights=weights))
        score_bank["knn_text20_bad20"] = knn_scores

        if existing_binary_bad is not None:
            score_bank["existing_binary_bad"] = np.asarray(existing_binary_bad, dtype=np.float64)

        consensus_names = [
            name
            for name in [
                "tfidf25_style_lr_bad20",
                "tfidf36_style_lr_bad20",
                "knn_text20_bad20",
                "existing_binary_bad",
            ]
            if name in score_bank
        ]
        consensus_ranks = [_bad_rank_percentile(score_bank[name]) for name in consensus_names]
        score_bank["qa_consensus_minrank"] = np.min(np.vstack(consensus_ranks), axis=0)
        bad_score = _top_vote_score(score_bank, consensus_names, top_n=8)
        if n >= int(policy.get("high_volume_min_candidates", 40)):
            requested_drop_n = int(policy.get("high_volume_drop_count", policy["default_drop_count_for_30"]))
        else:
            requested_drop_n = int(policy["default_drop_count_for_30"])
        drop_n = min(requested_drop_n, int(policy["max_drop_count"]), max(0, n - 1))
        rejected = np.argsort(-bad_score, kind="mergesort")[:drop_n].astype(int).tolist() if drop_n > 0 else []
        return {
            "available": True,
            "reason": "ok",
            "bad_score": bad_score,
            "rejected_indices": rejected,
            "drop_n": int(drop_n),
            "components": score_bank,
        }

    def score_candidates(
        self,
        candidates_embeddings: np.ndarray,
        orig_index: int = None,
        target_time=None,
        candidate_texts: List[str] = None,
        text_embeddings: np.ndarray | None = None,
        visual_embeddings: np.ndarray | None = None,
    ) -> List[dict]:
        base_results = super().score_candidates(
            candidates_embeddings,
            orig_index=orig_index,
            target_time=target_time,
            candidate_texts=candidate_texts,
        )
        if not candidate_texts or len(base_results) <= 1:
            return base_results

        texts = ["" if t is None else str(t) for t in candidate_texts]
        n = len(texts)
        by_index = {int(item["index"]): item for item in base_results}

        hygiene_rejections = [self._copy_hygiene_rejection(text) for text in texts]
        ltr_scores = self._ltr_scores(texts)
        existing_binary_bad = -np.asarray(self._binary_candidate_scores(texts), dtype=np.float64)
        qa_scores = self._qa_bad_scores(
            texts,
            multi_embeddings=np.asarray(candidates_embeddings, dtype=np.float32) if candidates_embeddings is not None else None,
            text_embeddings=text_embeddings,
            visual_embeddings=visual_embeddings,
            existing_binary_bad=existing_binary_bad,
        )
        qa_rejected = set(int(i) for i in qa_scores.get("rejected_indices", []))
        base_score = np.asarray(
            [float(by_index.get(i, {}).get("confidence_gate_final_score", by_index.get(i, {}).get("total_score", 0.0))) for i in range(n)],
            dtype=np.float64,
        )
        qa_bad_score = np.asarray(qa_scores.get("bad_score", np.zeros(n)), dtype=np.float64)
        if not bool(qa_scores.get("available")):
            qa_bad_score = existing_binary_bad

        ltr_z = _zscore(np.asarray(ltr_scores["combined"], dtype=np.float64))
        base_z = _zscore(base_score)
        qa_bad_z = _zscore(qa_bad_score)
        final_score = (0.55 * base_z) + (1.35 * ltr_z) - (0.70 * qa_bad_z)

        for idx in range(n):
            item = by_index.get(idx)
            if item is None:
                continue
            hygiene = hygiene_rejections[idx]
            qa_rejected_flag = idx in qa_rejected
            hard_rejected = hygiene is not None
            practical_score = float(final_score[idx])
            if qa_rejected_flag:
                practical_score -= 0.75
            if hard_rejected:
                practical_score = -1e9
            previous_total_score = float(item.get("total_score", 0.0))
            item["practical_final_score"] = practical_score
            item["pre_practical_total_score"] = previous_total_score
            item["total_score"] = -1e12 if hard_rejected else float(50000.0 + (practical_score * 10000.0))
            item["practical_final_artifact"] = str(self.artifact_path)
            item["practical_directional_mode"] = {
                "name": "directional_aggressive_v1",
                "base_weight": 0.55,
                "ltr_weight": 1.35,
                "qa_bad_penalty_weight": 0.70,
                "qa_marked_extra_penalty": 0.75,
                "overrides_total_score": True,
            }
            item["practical_hygiene_rejection"] = hygiene
            item["practical_learned_qa"] = {
                "available": bool(qa_scores.get("available")),
                "reason": qa_scores.get("reason"),
                "bad_score": float(qa_bad_score[idx]),
                "bad_z": float(qa_bad_z[idx]),
                "rejected": bool(qa_rejected_flag),
                "action": "downrank_not_hard_delete" if qa_rejected_flag else "keep",
                "drop_n": int(qa_scores.get("drop_n", 0) or 0),
            }
            item["practical_ltr_sidecar"] = {
                "primary_score": float(ltr_scores["primary"][idx]),
                "robust_score": float(ltr_scores["robust"][idx]),
                "catboost_score": float(ltr_scores["catboost"][idx]),
                "combined_score": float(ltr_scores["combined"][idx]),
                "batch_primary_top_gap": float(ltr_scores["primary_top_gap"]),
                "q70": ltr_scores["primary_q70"],
                "q80": ltr_scores["primary_q80"],
                "q70_or_higher": bool(
                    ltr_scores["primary_q70"] is not None
                    and float(ltr_scores["primary_top_gap"]) >= float(ltr_scores["primary_q70"])
                ),
                "q80_or_higher": bool(
                    ltr_scores["primary_q80"] is not None
                    and float(ltr_scores["primary_top_gap"]) >= float(ltr_scores["primary_q80"])
                ),
            }
            item["scorer_mode"] = "practical_final_copy_scorer_20260527"

        return sorted(by_index.values(), key=lambda x: float(x.get("practical_final_score", -1e9)), reverse=True)


if __name__ == "__main__":
    scorer = PracticalFinalCopyScorer()
    dummy_vecs = np.random.randn(30, 3072).astype(np.float32)
    dummy_texts = [f"요즘 이거 은근히 모르는 사람 많더라 {i}" for i in range(30)]
    result = scorer.score_candidates(dummy_vecs, candidate_texts=dummy_texts)
    print(f"PracticalFinalCopyScorer dry run ok. top_index={result[0]['index']}")
