import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

from app_config import GlobalConfig
from api.logging_utils import get_logger, log_event

CandidateData = Dict[str, Any]
ScoreResult = Dict[str, Any]
logger = get_logger(__name__)


class CopyScorerV4HighLowOnline:
    """
    Promoted scorer based on the legacy v4.5 scoring structure with the
    `highlow_raw_only` tournament model swapped in.

    This keeps:
    - legacy 3081 reg / hurdle stack
    - legacy percentile mapping
    - legacy top40 -> tournament sort -> score aggregation path

    And changes only:
    - tournament model artifact to `tournament_model_highlow.pkl`
    """

    EMBEDDING_DIM = 3072
    META_DIM = 9

    def __init__(self):
        model_dir = os.path.join(GlobalConfig.BASE_DIR.parent, "embedding_migration")
        log_event(logger, logging.INFO, "copy_scorer.v4_highlow.init", model_dir=model_dir)
        try:
            self.reg_model = joblib.load(os.path.join(model_dir, "viral_model.pkl"))
            self.hurdle_model = joblib.load(os.path.join(model_dir, "hurdle_model.pkl"))
            self.p_map = joblib.load(os.path.join(model_dir, "percentile_map.pkl"))
            self.tour_model = joblib.load(os.path.join(model_dir, "tournament_model_highlow.pkl"))
            log_event(logger, logging.INFO, "copy_scorer.v4_highlow.models_loaded")
        except Exception as e:
            log_event(logger, logging.ERROR, "copy_scorer.v4_highlow.load_failed", error=str(e))
            raise

    def extract_style_3081(self, text: str, target_time: Optional[datetime] = None) -> List[float]:
        if target_time is None:
            target_time = datetime.now()

        day_sin = np.sin(2 * np.pi * target_time.weekday() / 7)
        day_cos = np.cos(2 * np.pi * target_time.weekday() / 7)
        hour_sin = np.sin(2 * np.pi * target_time.hour / 24)
        hour_cos = np.cos(2 * np.pi * target_time.hour / 24)

        if not isinstance(text, str):
            return [day_sin, day_cos, hour_sin, hour_cos, 0.0, 0.0, 0.0, 0.0, 0.0]

        text = text.strip()
        length = float(len(text))
        emoji_count = float(len(re.findall(r"[^\w\s,]", text)))
        line_count = float(text.count("\n"))
        q_count = float(text.count("?"))
        ex_count = float(text.count("!"))
        return [day_sin, day_cos, hour_sin, hour_cos, emoji_count, line_count, q_count, ex_count, length]

    def map_to_percentile(self, val: float) -> float:
        if self.p_map is None:
            return float(val)
        idx = np.searchsorted(self.p_map["targets"], val)
        return float(self.p_map["percentiles"][min(idx, len(self.p_map["percentiles"]) - 1)])

    def score_candidates(
        self,
        candidates_data: List[CandidateData],
        orig_index: Optional[int] = None,
        target_time: Optional[datetime] = None,
    ) -> List[ScoreResult]:
        if not candidates_data:
            return []

        if target_time is None:
            target_time = datetime.now()

        processed_vecs_3081 = []
        raw_embeddings = []
        valid_mask = []

        for item in candidates_data:
            vec = item.get("embedding")
            text = item.get("text", "")
            if vec is None or np.any(np.isnan(vec)) or np.all(vec == 0):
                processed_vecs_3081.append(np.zeros(self.EMBEDDING_DIM + self.META_DIM))
                raw_embeddings.append(np.zeros(self.EMBEDDING_DIM))
                valid_mask.append(False)
            else:
                meta = self.extract_style_3081(text, target_time)
                v_full = np.hstack([vec, meta])
                processed_vecs_3081.append(v_full)
                raw_embeddings.append(vec)
                valid_mask.append(True)

        x_3081 = np.asarray(processed_vecs_3081, dtype=np.float32)
        valid_indices = [i for i, ok in enumerate(valid_mask) if ok]
        if not valid_indices:
            return []

        reg_scores = np.zeros(len(x_3081), dtype=np.float64)
        hurdle_probs = np.zeros(len(x_3081), dtype=np.float64)

        v_input = x_3081[valid_indices]
        reg_preds = self.reg_model.predict(v_input)
        for idx, val in zip(valid_indices, reg_preds):
            reg_scores[idx] = self.map_to_percentile(val)

        h_probs_raw = self.hurdle_model.predict_proba(v_input)[:, 1]
        for idx, val in zip(valid_indices, h_probs_raw):
            hurdle_probs[idx] = val

        results = []
        for i in range(len(x_3081)):
            results.append(
                {
                    "index": i,
                    "reg_score": float(reg_scores[i]),
                    "hurdle_prob": float(hurdle_probs[i]),
                    "pass_hurdle": bool(hurdle_probs[i] >= 0.5),
                    "league_wins": 0,
                }
            )

        initial_pool_indices = sorted(valid_indices, key=lambda i: reg_scores[i], reverse=True)[:40]

        def compare_pair_raw(idx1: int, idx2: int) -> bool:
            v1, v2 = raw_embeddings[idx1], raw_embeddings[idx2]
            tour_input = np.hstack([v1, v2]).reshape(1, -1)
            try:
                win_prob = self.tour_model.predict_proba(tour_input)[0, 1]
                return bool(win_prob >= 0.5)
            except Exception:
                return bool(reg_scores[idx1] >= reg_scores[idx2])

        if orig_index is not None:
            finalists_indices = [i for i in initial_pool_indices if i == orig_index or compare_pair_raw(i, orig_index)]
        else:
            finalists_indices = initial_pool_indices

        from functools import cmp_to_key

        def tournament_cmp(idx_a: int, idx_b: int) -> int:
            return -1 if compare_pair_raw(idx_a, idx_b) else 1

        sorted_finalists = sorted(finalists_indices, key=cmp_to_key(tournament_cmp))

        for rank, f_idx in enumerate(sorted_finalists):
            tour_score = max(0.0, 5000.0 - (rank * 50.0))
            results[f_idx]["total_score"] = float(tour_score + (results[f_idx]["reg_score"] / 10.0))
            results[f_idx]["league_wins"] = len(sorted_finalists) - rank - 1

        for i, res in enumerate(results):
            if "total_score" not in res:
                res["total_score"] = float(reg_scores[i])

        return sorted(results, key=lambda x: x["total_score"], reverse=True)
