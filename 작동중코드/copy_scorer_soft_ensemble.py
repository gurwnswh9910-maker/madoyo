import os
from typing import Dict, List

import joblib
import numpy as np
from scipy.sparse import csr_matrix, hstack

from app_config import GlobalConfig
from copy_scorer_v4_local import CopyScorerV4


_MODEL_DIR = GlobalConfig.BASE_DIR / "embedding_migration"
_SOFT_ENSEMBLE_ARTIFACT = _MODEL_DIR / "copy_scorer_soft_ensemble_v1.pkl"
_CONFIDENCE_GATE_ARTIFACT = (
    GlobalConfig.BASE_DIR
    / "연구소"
    / "ml연구소"
    / "20260501_uploaded_pairwise_ranker"
    / "style_cap_ood_final_candidate_20260507.pkl"
)
_CONFIDENCE_GATE_STRONG_THRESHOLD = float(os.getenv("MADOYO_CONF_GATE_STRONG_THRESHOLD", "4.0"))
_CONFIDENCE_GATE_SOFT_WEIGHT = float(os.getenv("MADOYO_CONF_GATE_SOFT_WEIGHT", "2.0"))
_CONFIDENCE_GATE_MARGIN_CAP = float(os.getenv("MADOYO_CONF_GATE_MARGIN_CAP", "8.0"))


class CopyScorerSoftEnsemble(CopyScorerV4):
    """
    Test-only upgraded scorer.

    Keeps CopyScorerV4 legacy behavior intact, then replaces only multi-candidate
    final ranking with the best research soft ensemble:
    text high-low + curriculum good + vector highlow + binary prior.
    """

    def __init__(self):
        super().__init__()
        model_dir = str(_MODEL_DIR)
        self.vector_highlow_model = joblib.load(os.path.join(model_dir, "tournament_model_highlow.pkl"))
        self.soft_ensemble = joblib.load(_SOFT_ENSEMBLE_ARTIFACT)
        confidence_payload = joblib.load(_CONFIDENCE_GATE_ARTIFACT)
        if isinstance(confidence_payload, dict) and "confidence_gate" in confidence_payload:
            self.confidence_gate = confidence_payload["confidence_gate"]
            self.confidence_gate_ood_policy = confidence_payload.get("ood_policy") or {"kind": "none"}
            self.confidence_gate_threshold = float(
                confidence_payload.get(
                    "threshold",
                    self.confidence_gate["filter"]["confidence_threshold"],
                )
            )
        else:
            self.confidence_gate = confidence_payload
            self.confidence_gate_ood_policy = {"kind": "none"}
            self.confidence_gate_threshold = float(self.confidence_gate["filter"]["confidence_threshold"])
        self.confidence_gate_strong_threshold = _CONFIDENCE_GATE_STRONG_THRESHOLD
        self.confidence_gate_soft_weight = _CONFIDENCE_GATE_SOFT_WEIGHT
        self.confidence_gate_margin_cap = _CONFIDENCE_GATE_MARGIN_CAP
        print(f"✅ [CopyScorerSoftEnsemble] 적용: {self.soft_ensemble.get('version', 'unknown')}")
        print(
            "✅ [CopyConfidenceGate] 적용: "
            f"claim>={self.confidence_gate_threshold:.3f}, "
            f"strong>={self.confidence_gate_strong_threshold:.3f}, "
            f"soft_weight={self.confidence_gate_soft_weight:.2f}, "
            f"ood_policy={self.confidence_gate_ood_policy.get('name', self.confidence_gate_ood_policy.get('kind', 'none'))}"
        )

    @staticmethod
    def _zscore(values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.float64)
        std = float(np.std(values))
        if std <= 1e-12:
            return np.zeros_like(values, dtype=np.float64)
        return (values - float(np.mean(values))) / std

    @staticmethod
    def _clip_prob(prob: np.ndarray) -> np.ndarray:
        return np.clip(np.asarray(prob, dtype=np.float64), 1e-5, 1.0 - 1e-5)

    def _classifier_prob(self, model, matrix) -> np.ndarray:
        if hasattr(model, "predict_proba"):
            return self._clip_prob(model.predict_proba(matrix)[:, 1])
        raw = model.decision_function(matrix)
        return self._clip_prob(1.0 / (1.0 + np.exp(-np.clip(raw, -50.0, 50.0))))

    def _logit(self, prob: np.ndarray) -> np.ndarray:
        prob = self._clip_prob(prob)
        return np.log(prob / (1.0 - prob))

    @staticmethod
    def _scores_from_prob_matrix(prob: np.ndarray, mode: str) -> np.ndarray:
        if mode == "sum_prob":
            return np.sum(prob, axis=1) - 0.5
        if mode == "copeland":
            return np.sum(prob >= 0.5, axis=1) - 1
        raise ValueError(f"Unsupported score mode: {mode}")

    def _text_pair_probability_matrix(self, model, vectorizer, texts: List[str]) -> np.ndarray:
        x = vectorizer.transform(texts)
        n = x.shape[0]
        prob = np.full((n, n), 0.5, dtype=np.float64)
        if n <= 1:
            return prob
        row_pairs = [(i, j) for i in range(n) for j in range(n) if i != j]
        left = [i for i, _ in row_pairs]
        right = [j for _, j in row_pairs]
        rows = x[left] - x[right]
        pred = model.predict_proba(rows)[:, 1]
        for (i, j), p in zip(row_pairs, pred):
            prob[i, j] = float(p)
        return prob

    def _vector_pair_probability_matrix(self, model, vectors: np.ndarray) -> np.ndarray:
        vectors = np.asarray(vectors, dtype=np.float32)
        n = len(vectors)
        prob = np.full((n, n), 0.5, dtype=np.float64)
        if n <= 1:
            return prob
        row_pairs = [(i, j) for i in range(n) for j in range(n) if i != j]
        rows = np.asarray([np.hstack([vectors[i], vectors[j]]) for i, j in row_pairs], dtype=np.float32)
        pred = model.predict_proba(rows)[:, 1]
        for (i, j), p in zip(row_pairs, pred):
            prob[i, j] = float(p)
        return prob

    def _binary_candidate_scores(self, texts: List[str]) -> np.ndarray:
        x = self.soft_ensemble["binary_vectorizer"].transform(texts)
        top92 = self._classifier_prob(self.soft_ensemble["binary_top92"], x)
        low40 = self._classifier_prob(self.soft_ensemble["binary_low40"], x)
        return self._logit(top92) - self._logit(low40)

    @staticmethod
    def _confidence_style_features(texts: List[str]) -> np.ndarray:
        rows = []
        for text in texts:
            t = "" if text is None else str(text).strip()
            length = len(t)
            lines = max(1, t.count("\n") + 1)
            rows.append(
                [
                    length,
                    lines,
                    length / lines,
                    sum(ch.isdigit() for ch in t),
                    sum(ch.isspace() for ch in t),
                    t.count("?"),
                    t.count("!"),
                    t.count(";"),
                    t.count("\n"),
                    sum(1 for ch in t if 0xAC00 <= ord(ch) <= 0xD7A3),
                    sum(1 for ch in t if ch.isascii() and ch.isalpha()),
                    t.count("http://") + t.count("https://"),
                ]
            )
        return np.asarray(rows, dtype=np.float64)

    @staticmethod
    def _confidence_text_shape(text: str) -> Dict[str, float]:
        t = "" if text is None else str(text).strip()
        lines = t.splitlines() or [t]
        line_lengths = [len(line) for line in lines]
        length = len(t)
        return {
            "length": float(length),
            "first": float(line_lengths[0] if line_lengths else length),
            "max_line": float(max(line_lengths) if line_lengths else length),
            "avg_line": float(length / max(1, len(lines))),
        }

    def _confidence_ood_allowed(self, text: str) -> bool:
        policy = getattr(self, "confidence_gate_ood_policy", None) or {"kind": "none"}
        kind = policy.get("kind", "none")
        if kind == "none":
            return True
        shape = self._confidence_text_shape(text)
        if kind == "length_only":
            return shape["length"] <= float(policy.get("length", float("inf")))
        if kind == "length_first":
            return (
                shape["length"] <= float(policy.get("length", float("inf")))
                and shape["first"] <= float(policy.get("first", float("inf")))
            )
        return True

    def _confidence_component_matrix(self, feature_artifact: dict, texts: List[str]):
        x = feature_artifact["vectorizer"].transform(texts)
        scaler = feature_artifact.get("style_scaler")
        if scaler is not None:
            style_values = self._confidence_style_features(texts)
            style_caps = feature_artifact.get("style_caps")
            if style_caps is not None:
                caps = np.asarray(style_caps, dtype=np.float64).reshape(1, -1)
                style_values = np.minimum(style_values, caps)
            style = csr_matrix(scaler.transform(style_values))
            x = hstack([x, style], format="csr")
        return x

    def _confidence_gate_scores(self, texts: List[str]) -> tuple[np.ndarray, Dict]:
        n = len(texts)
        gate_score = np.zeros(n, dtype=np.float64)
        claimed_wins = np.zeros(n, dtype=np.int32)
        claimed_losses = np.zeros(n, dtype=np.int32)
        strong_wins = np.zeros(n, dtype=np.int32)
        strong_losses = np.zeros(n, dtype=np.int32)
        strong_edges = []
        claimed_edges = []
        eligible_candidates = np.asarray(
            [self._confidence_ood_allowed(text) for text in texts],
            dtype=bool,
        )

        if n <= 1:
            return gate_score, {
                "claimed_edges": claimed_edges,
                "strong_edges": strong_edges,
                "claimed_wins": claimed_wins,
                "claimed_losses": claimed_losses,
                "strong_wins": strong_wins,
                "strong_losses": strong_losses,
                "eligible_candidates": eligible_candidates,
            }

        component_matrices = [
            self._confidence_component_matrix(component["feature_artifact"], texts)
            for component in self.confidence_gate["components"]
        ]

        for i in range(n):
            for j in range(i + 1, n):
                if not (eligible_candidates[i] and eligible_candidates[j]):
                    continue
                values = []
                for component, matrix in zip(self.confidence_gate["components"], component_matrices):
                    row = matrix[i] - matrix[j]
                    values.append(float(np.ravel(component["model"].decision_function(row))[0]))
                feat = np.asarray(values, dtype=np.float64).reshape(1, -1)
                margin = float(np.ravel(self.confidence_gate["stack_model"].decision_function(feat))[0])
                abs_margin = abs(margin)
                if abs_margin < self.confidence_gate_threshold:
                    continue

                winner, loser = (i, j) if margin > 0 else (j, i)
                strength = min(abs_margin, self.confidence_gate_margin_cap) / self.confidence_gate_strong_threshold
                gate_score[winner] += strength
                gate_score[loser] -= strength
                claimed_wins[winner] += 1
                claimed_losses[loser] += 1
                claimed_edges.append((winner, loser, abs_margin))

                if abs_margin >= self.confidence_gate_strong_threshold:
                    strong_wins[winner] += 1
                    strong_losses[loser] += 1
                    strong_edges.append((winner, loser, abs_margin))

        return gate_score, {
            "claimed_edges": claimed_edges,
            "strong_edges": strong_edges,
            "claimed_wins": claimed_wins,
            "claimed_losses": claimed_losses,
            "strong_wins": strong_wins,
            "strong_losses": strong_losses,
            "eligible_candidates": eligible_candidates,
        }

    @staticmethod
    def _order_with_strong_edges(scores: np.ndarray, strong_edges: list[tuple[int, int, float]]) -> tuple[list[int], bool]:
        n = len(scores)
        if not strong_edges:
            return [int(i) for i in np.argsort(-scores, kind="mergesort")], False

        outgoing = {i: set() for i in range(n)}
        indegree = {i: 0 for i in range(n)}
        for winner, loser, _ in strong_edges:
            if loser not in outgoing[winner]:
                outgoing[winner].add(loser)
                indegree[loser] += 1

        available = [i for i in range(n) if indegree[i] == 0]
        order = []
        while available:
            available.sort(key=lambda idx: (-scores[idx], idx))
            node = available.pop(0)
            order.append(node)
            for nxt in sorted(outgoing[node]):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    available.append(nxt)

        if len(order) == n:
            return order, False

        strong_net = np.zeros(n, dtype=np.float64)
        for winner, loser, _ in strong_edges:
            strong_net[winner] += 1.0
            strong_net[loser] -= 1.0
        order = sorted(range(n), key=lambda idx: (-strong_net[idx], -scores[idx], idx))
        return [int(i) for i in order], True

    def _soft_ensemble_scores(self, vectors: np.ndarray, texts: List[str]) -> tuple[np.ndarray, Dict[str, np.ndarray]]:
        weights = self.soft_ensemble["weights"]
        text_prob = self._text_pair_probability_matrix(
            self.soft_ensemble["text_model"],
            self.soft_ensemble["text_vectorizer"],
            texts,
        )
        good_prob = self._text_pair_probability_matrix(
            self.soft_ensemble["good_model"],
            self.soft_ensemble["text_vectorizer"],
            texts,
        )
        vector_prob = self._vector_pair_probability_matrix(self.vector_highlow_model, vectors)

        text_score = self._scores_from_prob_matrix(text_prob, "sum_prob")
        good_score = self._scores_from_prob_matrix(good_prob, "copeland")
        vector_score = self._scores_from_prob_matrix(vector_prob, "sum_prob")
        binary_score = self._binary_candidate_scores(texts)

        total = (
            weights["text_sum_prob"] * self._zscore(text_score)
            + weights["good_copeland"] * self._zscore(good_score)
            + weights["vector_sum_prob"] * self._zscore(vector_score)
            + weights["binary_prior"] * self._zscore(binary_score)
        )
        return total, {
            "text_sum_prob": text_score,
            "good_copeland": good_score,
            "vector_sum_prob": vector_score,
            "binary_prior": binary_score,
        }

    @staticmethod
    def _valid_indices(candidates_embeddings: np.ndarray) -> list[int]:
        valid = []
        for i, vec in enumerate(candidates_embeddings):
            if vec is None or np.any(np.isnan(vec)) or np.all(vec == 0):
                continue
            valid.append(i)
        return valid

    def score_candidates(
        self,
        candidates_embeddings: np.ndarray,
        orig_index: int = None,
        target_time=None,
        candidate_texts: List[str] = None,
    ) -> List[Dict]:
        legacy_results = super().score_candidates(
            candidates_embeddings,
            orig_index=orig_index,
            target_time=target_time,
            candidate_texts=candidate_texts,
        )
        if not candidate_texts or len(legacy_results) <= 1:
            return legacy_results

        valid_indices = self._valid_indices(candidates_embeddings)
        if len(valid_indices) <= 1:
            return legacy_results

        by_index = {int(item["index"]): item for item in legacy_results}
        valid_texts = [
            candidate_texts[i] if i < len(candidate_texts) and candidate_texts[i] is not None else ""
            for i in valid_indices
        ]
        valid_vectors = np.asarray([candidates_embeddings[i] for i in valid_indices], dtype=np.float32)
        ensemble_scores, components = self._soft_ensemble_scores(valid_vectors, valid_texts)
        confidence_scores, confidence_meta = self._confidence_gate_scores(valid_texts)
        final_scores = ensemble_scores + (self.confidence_gate_soft_weight * self._zscore(confidence_scores))
        ensemble_order, strong_cycle = self._order_with_strong_edges(
            final_scores,
            confidence_meta["strong_edges"],
        )
        league_wins_by_local = {
            int(local_idx): len(ensemble_scores) - rank - 1
            for rank, local_idx in enumerate(ensemble_order)
        }

        for local_idx, global_idx in enumerate(valid_indices):
            item = by_index[global_idx]
            item["legacy_total_score"] = float(item.get("total_score", 0.0))
            item["upgraded_ensemble_score"] = float(ensemble_scores[local_idx])
            item["confidence_gate_score"] = float(confidence_scores[local_idx])
            item["confidence_gate_final_score"] = float(final_scores[local_idx])
            item["ensemble_components"] = {
                name: float(values[local_idx])
                for name, values in components.items()
            }
            item["ensemble_components"]["confidence_gate"] = float(confidence_scores[local_idx])
            item["scorer_mode"] = self.soft_ensemble.get("version", "soft_ensemble_v1")
            item["confidence_gate"] = {
                "claim_threshold": self.confidence_gate_threshold,
                "strong_threshold": self.confidence_gate_strong_threshold,
                "claimed_wins": int(confidence_meta["claimed_wins"][local_idx]),
                "claimed_losses": int(confidence_meta["claimed_losses"][local_idx]),
                "strong_wins": int(confidence_meta["strong_wins"][local_idx]),
                "strong_losses": int(confidence_meta["strong_losses"][local_idx]),
                "strong_cycle": bool(strong_cycle),
                "ood_eligible": bool(confidence_meta["eligible_candidates"][local_idx]),
                "ood_policy": self.confidence_gate_ood_policy.get(
                    "name",
                    self.confidence_gate_ood_policy.get("kind", "none"),
                ),
            }
            item["league_wins"] = int(league_wins_by_local.get(local_idx, 0))
            hard_rank = len(ensemble_scores) - item["league_wins"] - 1
            item["total_score"] = float(
                10000.0
                + ((len(ensemble_scores) - hard_rank) * 1000.0)
                + (final_scores[local_idx] * 100.0)
                + (item.get("reg_score", 0.0) / 1000.0)
            )

        print(
            f"      🧪 [CopyScorerSoftEnsemble] Top {len(valid_indices)} 후보 묶음 리랭킹 적용 완료. "
            f"confidence_claims={len(confidence_meta['claimed_edges'])}, "
            f"strong_edges={len(confidence_meta['strong_edges'])}, "
            f"cycle={strong_cycle}"
        )
        return sorted(by_index.values(), key=lambda x: x["total_score"], reverse=True)


if __name__ == "__main__":
    scorer = CopyScorerSoftEnsemble()
    dummy_vecs = np.random.randn(5, 3072)
    dummy_texts = ["오늘의 핫딜! 사야할 물건 #추천 #쿠팡" for _ in range(5)]
    res = scorer.score_candidates(dummy_vecs, candidate_texts=dummy_texts)
    print(f"✅ Soft Ensemble Dry Run Successful. Top Score: {res[0]['total_score']:.2f}")
