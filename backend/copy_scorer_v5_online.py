import gc
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np

from app_config import GlobalConfig
from api.logging_utils import get_logger, log_event


CandidateData = Dict[str, Any]
ScoreResult = Dict[str, Any]
logger = get_logger(__name__)


class CopyScorerV5:
    """Online ML scorer for ranking generated copy candidates."""

    EMBEDDING_DIM = 3072
    META_FEATURE_DIM = 9
    FEATURE_DIM = EMBEDDING_DIM + META_FEATURE_DIM
    LEAGUE_SIZE = 5
    HURDLE_PASS_THRESHOLD = 0.5
    WILDCARD_THRESHOLD = 0.9

    def __init__(self, use_supabase: bool = False, supabase_url: str = ""):
        del use_supabase, supabase_url

        os.makedirs(GlobalConfig.MODEL_DIR, exist_ok=True)
        self.files = {
            "reg": os.path.join(GlobalConfig.MODEL_DIR, "viral_model.pkl"),
            "tour": os.path.join(GlobalConfig.MODEL_DIR, "tournament_model.pkl"),
            "hurdle": os.path.join(GlobalConfig.MODEL_DIR, "hurdle_model.pkl"),
        }

        log_event(logger, logging.INFO, "copy_scorer.models.loading", model_dir=str(GlobalConfig.MODEL_DIR))

        if not os.path.exists(self.files["tour"]):
            log_event(logger, logging.WARNING, "copy_scorer.models.missing", missing_key="tour")

        self.reg_model = joblib.load(self.files["reg"])
        self.hurdle_model = joblib.load(self.files["hurdle"])
        self.tour_model = joblib.load(self.files["tour"])
        log_event(logger, logging.INFO, "copy_scorer.models.loaded", file_count=len(self.files))

    def _extract_meta_features(self, text: str, dt: Optional[datetime] = None) -> np.ndarray:
        if dt is None:
            dt = datetime.now()

        day_sin = np.sin(2 * np.pi * dt.weekday() / 7)
        day_cos = np.cos(2 * np.pi * dt.weekday() / 7)
        hour_sin = np.sin(2 * np.pi * dt.hour / 24)
        hour_cos = np.cos(2 * np.pi * dt.hour / 24)

        if not isinstance(text, str):
            style = [0, 0, 0, 0]
            text_length = 0
        else:
            emoji_count = len(re.findall(r"[^\w\s,]", text))
            line_count = text.count("\n")
            question_count = text.count("?")
            exclamation_count = text.count("!")
            style = [emoji_count, line_count, question_count, exclamation_count]
            text_length = len(text)

        return np.array(
            [day_sin, day_cos, hour_sin, hour_cos, *style, text_length],
            dtype=float,
        )

    def _normalize_embedding(self, embedding: Any) -> Optional[np.ndarray]:
        if embedding is None:
            return None

        try:
            vector = np.asarray(embedding, dtype=float)
        except (TypeError, ValueError):
            return None

        if vector.shape != (self.EMBEDDING_DIM,):
            return None
        if np.any(np.isnan(vector)) or np.all(vector == 0):
            return None
        return vector

    def _build_feature_matrix(
        self, candidates_data: List[CandidateData], now: datetime
    ) -> Tuple[np.ndarray, List[bool]]:
        processed_vectors: List[np.ndarray] = []
        valid_mask: List[bool] = []

        for item in candidates_data:
            text = item.get("text", "")
            embedding = self._normalize_embedding(item.get("embedding"))

            if embedding is None:
                processed_vectors.append(np.zeros(self.FEATURE_DIM, dtype=float))
                valid_mask.append(False)
                continue

            meta_features = self._extract_meta_features(text, now)
            processed_vectors.append(np.hstack([embedding, meta_features]))
            valid_mask.append(True)

        return np.array(processed_vectors, dtype=float), valid_mask

    def _predict_reg_scores(self, feature_matrix: np.ndarray, valid_indices: List[int]) -> np.ndarray:
        reg_scores = np.zeros(len(feature_matrix), dtype=float)
        if not valid_indices:
            return reg_scores

        predictions = self.reg_model.predict(feature_matrix[valid_indices])
        clipped = np.clip(predictions, 0, 100)
        for idx, score in zip(valid_indices, clipped):
            reg_scores[idx] = float(score)
        return reg_scores

    def _predict_hurdle_probs(self, feature_matrix: np.ndarray, valid_indices: List[int]) -> np.ndarray:
        hurdle_probs = np.zeros(len(feature_matrix), dtype=float)
        if not valid_indices:
            return hurdle_probs

        predictions = self.hurdle_model.predict_proba(feature_matrix[valid_indices])[:, 1]
        for idx, probability in zip(valid_indices, predictions):
            hurdle_probs[idx] = float(probability)
        return hurdle_probs

    def _initialize_results(
        self, reg_scores: np.ndarray, hurdle_probs: np.ndarray
    ) -> List[ScoreResult]:
        results: List[ScoreResult] = []
        for index, reg_score in enumerate(reg_scores):
            hurdle_prob = float(hurdle_probs[index])
            results.append(
                {
                    "index": index,
                    "reg_score": float(reg_score),
                    "hurdle_prob": hurdle_prob,
                    "pass_hurdle": hurdle_prob >= self.HURDLE_PASS_THRESHOLD,
                    "final_wins": 0,
                    "league_wins": 0,
                }
            )
        return results

    def _apply_original_bonus(
        self,
        feature_matrix: np.ndarray,
        valid_mask: List[bool],
        reg_scores: np.ndarray,
        results: List[ScoreResult],
        orig_index: Optional[int],
    ) -> None:
        if orig_index is None or not (0 <= orig_index < len(feature_matrix)) or not valid_mask[orig_index]:
            return

        max_beaten_reg = -1.0
        beaten_count = 0

        for opponent_index, is_valid in enumerate(valid_mask):
            if opponent_index == orig_index or not is_valid:
                continue

            pair_vector = np.hstack([feature_matrix[orig_index], feature_matrix[opponent_index]]).reshape(1, -1)
            win_probability = self.tour_model.predict_proba(pair_vector)[0, 1]
            if win_probability > 0.5:
                beaten_count += 1
                max_beaten_reg = max(max_beaten_reg, reg_scores[opponent_index])

        if beaten_count == 0:
            return

        new_score = max_beaten_reg + 0.05
        reg_scores[orig_index] = new_score
        results[orig_index]["reg_score"] = float(new_score)

    def _select_league_participants(
        self, valid_mask: List[bool], reg_scores: np.ndarray, hurdle_probs: np.ndarray
    ) -> List[int]:
        league_participants = sorted(
            [index for index, is_valid in enumerate(valid_mask) if is_valid],
            key=lambda index: reg_scores[index],
            reverse=True,
        )[: self.LEAGUE_SIZE]

        wildcards = [
            index
            for index, is_valid in enumerate(valid_mask)
            if is_valid
            and hurdle_probs[index] >= self.WILDCARD_THRESHOLD
            and index not in league_participants
        ]

        return league_participants + wildcards

    def _run_league(
        self, feature_matrix: np.ndarray, participants: List[int], results: List[ScoreResult]
    ) -> None:
        if len(participants) <= 1:
            return

        for left in range(len(participants)):
            for right in range(left + 1, len(participants)):
                idx1 = participants[left]
                idx2 = participants[right]
                pair_input = np.hstack([feature_matrix[idx1], feature_matrix[idx2]]).reshape(1, -1)
                win_probability = self.tour_model.predict_proba(pair_input)[0, 1]
                if win_probability > 0.5:
                    results[idx1]["league_wins"] += 1
                else:
                    results[idx2]["league_wins"] += 1

    def _finalize_scores(self, results: List[ScoreResult], reg_scores: np.ndarray) -> None:
        for result in results:
            index = result["index"]
            result["total_score"] = (result["league_wins"] * 1000) + reg_scores[index]

    def score_candidates(
        self, candidates_data: List[CandidateData], orig_index: Optional[int] = None
    ) -> List[ScoreResult]:
        if not candidates_data:
            return []

        now = datetime.now()
        feature_matrix, valid_mask = self._build_feature_matrix(candidates_data, now)
        valid_indices = [index for index, is_valid in enumerate(valid_mask) if is_valid]

        reg_scores = self._predict_reg_scores(feature_matrix, valid_indices)
        hurdle_probs = self._predict_hurdle_probs(feature_matrix, valid_indices)
        results = self._initialize_results(reg_scores, hurdle_probs)

        self._apply_original_bonus(feature_matrix, valid_mask, reg_scores, results, orig_index)
        participants = self._select_league_participants(valid_mask, reg_scores, hurdle_probs)
        self._run_league(feature_matrix, participants, results)
        self._finalize_scores(results, reg_scores)

        del feature_matrix
        gc.collect()

        return sorted(results, key=lambda item: item["total_score"], reverse=True)
