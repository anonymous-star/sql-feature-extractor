"""
Tests for SQLClusteringPipeline
=================================
pytest 기반. 각 기능을 독립적으로 검증합니다.

실행:
    pytest test_sql_clustering.py -v
"""

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sql_clustering import (
    SQLClusteringPipeline,
    FEATURE_COLS,
    BOOL_FEATURES,
    NUM_FEATURES,
    _chunked,
    _extract_chunk,
)


# ============================================================================
# 공통 픽스처
# ============================================================================

# 카테고리별 대표 SQL (의미있는 클러스터 구분을 위해 충분히 다양하게)
SIMPLE_SQLS = [
    "SELECT id FROM users WHERE age > 30",
    "SELECT name FROM products WHERE price < 100",
    "SELECT email FROM customers WHERE country = 'KR'",
    "SELECT * FROM orders WHERE status = 'pending'",
    "SELECT title FROM posts WHERE active = 1",
]

AGG_SQLS = [
    "SELECT dept, COUNT(*) FROM emp GROUP BY dept",
    "SELECT category, SUM(revenue) FROM sales GROUP BY category",
    "SELECT user_id, AVG(score) FROM ratings GROUP BY user_id HAVING AVG(score) > 4",
    "SELECT MIN(price), MAX(price) FROM products",
    "SELECT COUNT(DISTINCT user_id) FROM sessions GROUP BY date",
]

JOIN_SQLS = [
    "SELECT o.id, c.name FROM orders o JOIN customers c ON o.cid = c.id",
    "SELECT * FROM a LEFT JOIN b ON a.id = b.id",
    "SELECT * FROM a RIGHT JOIN b ON a.id = b.id",
    "SELECT p.name, s.qty FROM products p INNER JOIN stock s ON p.id = s.pid",
    "SELECT * FROM emp a JOIN emp b ON a.mgr_id = b.id",
]

SUBQUERY_SQLS = [
    "SELECT * FROM t WHERE id IN (SELECT id FROM t2 WHERE val > 100)",
    "SELECT * FROM products WHERE price > (SELECT AVG(price) FROM products)",
    "SELECT * FROM t WHERE EXISTS (SELECT 1 FROM t2 WHERE t2.ref = t.id)",
    "SELECT * FROM t WHERE id NOT IN (SELECT blocked_id FROM blacklist)",
    "SELECT * FROM t1 WHERE id IN (SELECT id FROM t2 WHERE x > (SELECT MAX(x) FROM t3))",
]

ALL_SQLS = SIMPLE_SQLS + AGG_SQLS + JOIN_SQLS + SUBQUERY_SQLS  # 20개


def make_pipeline(**kwargs) -> SQLClusteringPipeline:
    """테스트용 기본 파이프라인 (빠른 실행 설정)."""
    defaults = dict(
        n_clusters=4,
        algorithm="minibatch_kmeans",
        use_pca=False,
        chunk_size=50,
        n_jobs=1,
        random_state=42,
    )
    defaults.update(kwargs)
    return SQLClusteringPipeline(**defaults)


@pytest.fixture(scope="module")
def fitted_pipeline():
    """fit 완료된 파이프라인 + (X, labels) 반환."""
    p = make_pipeline(n_clusters=4)
    X, labels = p.fit_from_sqls(ALL_SQLS, total=len(ALL_SQLS))
    return p, X, labels


# ============================================================================
# 1. 유틸 함수
# ============================================================================

class TestUtils:

    def test_chunked_exact_multiple(self):
        result = list(_chunked(range(9), 3))
        assert result == [[0,1,2],[3,4,5],[6,7,8]]

    def test_chunked_with_remainder(self):
        result = list(_chunked(range(10), 3))
        assert len(result) == 4
        assert result[-1] == [9]

    def test_chunked_smaller_than_size(self):
        result = list(_chunked([1, 2], 100))
        assert result == [[1, 2]]

    def test_chunked_empty(self):
        assert list(_chunked([], 10)) == []

    def test_extract_chunk_shape(self):
        sqls = ["SELECT id FROM t", "SELECT * FROM t WHERE x = 1"]
        arr = _extract_chunk(sqls, dialect=None)
        assert arr.shape == (2, len(FEATURE_COLS))

    def test_extract_chunk_dtype(self):
        arr = _extract_chunk(["SELECT 1"], dialect=None)
        assert arr.dtype == np.float32

    def test_extract_chunk_invalid_sql(self):
        # 파싱 실패 → 0으로 채워진 행 (예외 없음)
        arr = _extract_chunk(["NOT VALID SQL!!!"], dialect=None)
        assert arr.shape == (1, len(FEATURE_COLS))
        assert not np.any(np.isnan(arr))


# ============================================================================
# 2. Feature 정의
# ============================================================================

class TestFeatureCols:

    def test_feature_cols_total(self):
        assert len(FEATURE_COLS) == 50

    def test_bool_plus_num_equals_total(self):
        assert len(BOOL_FEATURES) + len(NUM_FEATURES) == len(FEATURE_COLS)

    def test_no_duplicate_cols(self):
        assert len(FEATURE_COLS) == len(set(FEATURE_COLS))

    def test_query_type_excluded(self):
        # query_type 은 문자열 → feature 행렬에서 제외
        assert "query_type" not in FEATURE_COLS


# ============================================================================
# 3. extract_features
# ============================================================================

class TestExtractFeatures:

    def test_output_shape(self):
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        assert X.shape == (len(ALL_SQLS), len(FEATURE_COLS))

    def test_output_dtype(self):
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        assert X.dtype == np.float32

    def test_no_nan_or_inf(self):
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        assert not np.any(np.isnan(X))
        assert not np.any(np.isinf(X))

    def test_single_sql(self):
        p = make_pipeline()
        X = p.extract_features(["SELECT 1"])
        assert X.shape == (1, len(FEATURE_COLS))

    def test_invalid_sqls_no_exception(self):
        p = make_pipeline()
        X = p.extract_features(["INVALID", "ALSO INVALID"])
        assert X.shape == (2, len(FEATURE_COLS))

    def test_cache_save_and_load(self, tmp_path):
        cache = str(tmp_path / "features.npz")
        p = make_pipeline()

        X1 = p.extract_features(ALL_SQLS, save_path=cache)
        assert Path(cache).exists()

        # 두 번째 호출 → 캐시에서 로드
        X2 = p.extract_features(["DIFFERENT SQL"], save_path=cache)
        np.testing.assert_array_equal(X1, X2)

    def test_generator_input(self):
        """리스트 외 이터러블(제너레이터)도 처리 가능."""
        p = make_pipeline()
        gen = (sql for sql in ALL_SQLS)
        X = p.extract_features(gen)
        assert X.shape[0] == len(ALL_SQLS)

    def test_chunk_boundary(self):
        """청크 경계에서 데이터 손실 없음."""
        sqls = [f"SELECT {i} FROM t" for i in range(17)]
        p = make_pipeline(chunk_size=5)
        X = p.extract_features(sqls)
        assert X.shape[0] == 17

    def test_feature_values_are_nonnegative(self):
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        assert (X >= 0).all()

    def test_known_feature_value(self):
        """COUNT 쿼리에서 has_count=1.0 확인."""
        p = make_pipeline()
        X = p.extract_features(["SELECT COUNT(*) FROM t"])
        col_idx = FEATURE_COLS.index("has_count")
        assert X[0, col_idx] == 1.0

    def test_dialect_option(self):
        p = make_pipeline(dialect="mysql")
        X = p.extract_features(["SELECT id FROM t LIMIT 10"])
        assert X.shape == (1, len(FEATURE_COLS))


# ============================================================================
# 4. fit / predict
# ============================================================================

class TestFitPredict:

    def test_fit_returns_self(self):
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        result = p.fit(X)
        assert result is p

    def test_model_is_set_after_fit(self):
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        p.fit(X)
        assert p.model_ is not None
        assert p.scaler_ is not None

    def test_pca_is_set_when_enabled(self):
        p = make_pipeline(use_pca=True, pca_components=5)
        X = p.extract_features(ALL_SQLS)
        p.fit(X)
        assert p.pca_ is not None

    def test_pca_is_none_when_disabled(self):
        p = make_pipeline(use_pca=False)
        X = p.extract_features(ALL_SQLS)
        p.fit(X)
        assert p.pca_ is None

    def test_predict_label_range(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        assert set(labels).issubset(set(range(p.n_clusters)))

    def test_predict_output_length(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        assert len(labels) == len(ALL_SQLS)

    def test_predict_deterministic(self, fitted_pipeline):
        """같은 입력 → 같은 예측."""
        p, X, _ = fitted_pipeline
        labels1 = p.predict(X)
        labels2 = p.predict(X)
        np.testing.assert_array_equal(labels1, labels2)

    def test_fit_predict_consistent(self):
        """fit_predict 결과와 fit 후 predict 결과 일치."""
        p1 = make_pipeline(n_clusters=4, random_state=0)
        p2 = make_pipeline(n_clusters=4, random_state=0)
        X = p1.extract_features(ALL_SQLS)

        labels_fp = p1.fit_predict(X)
        p2.fit(X)
        labels_p = p2.predict(X)
        np.testing.assert_array_equal(labels_fp, labels_p)

    def test_bisecting_kmeans_algorithm(self):
        p = make_pipeline(algorithm="bisecting_kmeans", n_clusters=3)
        X = p.extract_features(ALL_SQLS)
        labels = p.fit_predict(X)
        assert set(labels).issubset(set(range(3)))

    def test_invalid_algorithm_raises(self):
        p = make_pipeline(algorithm="unknown_algo")
        X = p.extract_features(ALL_SQLS)
        with pytest.raises(ValueError, match="Unknown algorithm"):
            p.fit(X)

    def test_predict_before_fit_raises(self):
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        with pytest.raises((AttributeError, TypeError)):
            p.predict(X)

    def test_all_clusters_used(self, fitted_pipeline):
        """n_clusters 만큼 클러스터가 실제로 사용됨 (충분한 데이터)."""
        p, X, labels = fitted_pipeline
        assert len(set(labels)) == p.n_clusters


# ============================================================================
# 5. fit_from_sqls (엔드-투-엔드)
# ============================================================================

class TestFitFromSqls:

    def test_returns_tuple(self):
        p = make_pipeline()
        result = p.fit_from_sqls(ALL_SQLS)
        assert isinstance(result, tuple) and len(result) == 2

    def test_X_shape(self):
        p = make_pipeline()
        X, _ = p.fit_from_sqls(ALL_SQLS)
        assert X.shape == (len(ALL_SQLS), len(FEATURE_COLS))

    def test_labels_shape(self):
        p = make_pipeline()
        _, labels = p.fit_from_sqls(ALL_SQLS)
        assert labels.shape == (len(ALL_SQLS),)

    def test_with_feature_cache(self, tmp_path):
        cache = str(tmp_path / "cache.npz")
        p = make_pipeline()
        X1, l1 = p.fit_from_sqls(ALL_SQLS, feature_cache=cache)
        assert Path(cache).exists()

        # 캐시 재사용
        p2 = make_pipeline()
        X2, _ = p2.fit_from_sqls(ALL_SQLS, feature_cache=cache)
        np.testing.assert_array_equal(X1, X2)


# ============================================================================
# 6. 클러스터 분석
# ============================================================================

class TestClusterAnalysis:

    def test_cluster_profiles_shape(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        profiles = p.cluster_profiles(X, labels)
        assert len(profiles) == p.n_clusters

    def test_cluster_profiles_columns(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        profiles = p.cluster_profiles(X, labels)
        assert "size" in profiles.columns
        assert "ratio" in profiles.columns
        for col in FEATURE_COLS:
            assert col in profiles.columns

    def test_cluster_profiles_size_sum(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        profiles = p.cluster_profiles(X, labels)
        assert profiles["size"].sum() == len(ALL_SQLS)

    def test_cluster_profiles_ratio_sum(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        profiles = p.cluster_profiles(X, labels)
        assert abs(profiles["ratio"].sum() - 1.0) < 1e-6

    def test_cluster_profiles_ratio_range(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        profiles = p.cluster_profiles(X, labels)
        assert (profiles["ratio"] >= 0).all()
        assert (profiles["ratio"] <= 1).all()

    def test_describe_cluster_returns_series(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        cid = labels[0]
        result = p.describe_cluster(X, labels, cid)
        assert isinstance(result, pd.Series)
        assert len(result) == len(FEATURE_COLS)

    def test_describe_cluster_sorted_descending(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        cid = labels[0]
        s = p.describe_cluster(X, labels, cid)
        assert list(s.values) == sorted(s.values, reverse=True)

    def test_summary_shape(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        s = p.summary(X, labels)
        assert len(s) == p.n_clusters

    def test_summary_columns(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        s = p.summary(X, labels)
        for col in ["size", "ratio", "top_features", "avg_tables", "avg_joins", "avg_depth"]:
            assert col in s.columns

    def test_summary_top_features_nonempty(self, fitted_pipeline):
        p, X, labels = fitted_pipeline
        s = p.summary(X, labels)
        assert s["top_features"].str.len().gt(0).all()


# ============================================================================
# 7. Elbow (최적 k 탐색)
# ============================================================================

class TestFindOptimalK:

    def test_returns_dataframe(self):
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        df = p.find_optimal_k(X, k_range=range(2, 6))
        assert isinstance(df, pd.DataFrame)

    def test_columns(self):
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        df = p.find_optimal_k(X, k_range=range(2, 5))
        assert list(df.columns) == ["k", "inertia"]

    def test_row_count(self):
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        k_range = range(2, 6)
        df = p.find_optimal_k(X, k_range=k_range)
        assert len(df) == len(k_range)

    def test_inertia_decreases_with_k(self):
        """k 가 커질수록 inertia 는 단조 감소."""
        p = make_pipeline()
        X = p.extract_features(ALL_SQLS)
        df = p.find_optimal_k(X, k_range=range(2, 7))
        inertias = df["inertia"].tolist()
        assert all(inertias[i] >= inertias[i+1] for i in range(len(inertias)-1))

    def test_sampling_when_large(self):
        """sample_size 보다 데이터가 많으면 샘플링."""
        sqls = ALL_SQLS * 10   # 200개
        p = make_pipeline()
        X = p.extract_features(sqls)
        # sample_size=50 으로 실행해도 예외 없음
        df = p.find_optimal_k(X, k_range=range(2, 4), sample_size=50)
        assert len(df) == 2


# ============================================================================
# 8. 저장 / 로드
# ============================================================================

class TestSaveLoad:

    def test_save_creates_file(self, fitted_pipeline, tmp_path):
        p, _, _ = fitted_pipeline
        path = str(tmp_path / "pipeline.joblib")
        p.save(path)
        assert Path(path).exists()

    def test_load_returns_pipeline(self, fitted_pipeline, tmp_path):
        p, _, _ = fitted_pipeline
        path = str(tmp_path / "pipeline.joblib")
        p.save(path)
        loaded = SQLClusteringPipeline.load(path)
        assert isinstance(loaded, SQLClusteringPipeline)

    def test_loaded_predict_matches_original(self, fitted_pipeline, tmp_path):
        p, X, labels = fitted_pipeline
        path = str(tmp_path / "pipeline.joblib")
        p.save(path)
        loaded = SQLClusteringPipeline.load(path)

        labels_loaded = loaded.predict(X)
        np.testing.assert_array_equal(labels, labels_loaded)

    def test_loaded_preserves_hyperparams(self, fitted_pipeline, tmp_path):
        p, _, _ = fitted_pipeline
        path = str(tmp_path / "pipeline.joblib")
        p.save(path)
        loaded = SQLClusteringPipeline.load(path)

        assert loaded.n_clusters == p.n_clusters
        assert loaded.algorithm == p.algorithm
        assert loaded.random_state == p.random_state

    def test_loaded_can_extract_and_predict_new_sqls(self, fitted_pipeline, tmp_path):
        p, _, _ = fitted_pipeline
        path = str(tmp_path / "pipeline.joblib")
        p.save(path)
        loaded = SQLClusteringPipeline.load(path)

        new_sqls = ["SELECT COUNT(*) FROM orders GROUP BY status"]
        p2 = make_pipeline()
        p2.n_jobs = 1
        p2.chunk_size = 50
        X_new = p2.extract_features(new_sqls)
        label = loaded.predict(X_new)
        assert label[0] in range(loaded.n_clusters)


# ============================================================================
# 9. 클러스터 의미 검증 (smoke test)
# ============================================================================

class TestClusteringQuality:

    def test_similar_sqls_tend_to_same_cluster(self):
        """구조가 유사한 SQL들이 같은 클러스터에 몰리는 경향 검증."""
        sqls = (
            # 그룹 A: 단순 WHERE 조회 × 6
            ["SELECT id FROM t WHERE x = 1"] * 6 +
            # 그룹 B: GROUP BY 집계 × 6
            ["SELECT dept, COUNT(*) FROM emp GROUP BY dept"] * 6 +
            # 그룹 C: JOIN × 6
            ["SELECT * FROM a JOIN b ON a.id = b.id"] * 6
        )
        p = make_pipeline(n_clusters=3, use_pca=False, random_state=0)
        X, labels = p.fit_from_sqls(sqls)

        # 각 그룹(6개) 내 레이블이 동일해야 함
        for start in [0, 6, 12]:
            group_labels = labels[start:start+6]
            assert len(set(group_labels)) == 1, (
                f"그룹 {start//6} 내 레이블이 혼재됨: {group_labels}"
            )

    def test_dml_separated_from_select(self):
        """DML(INSERT/UPDATE/DELETE)과 SELECT 가 다른 클러스터에 배정."""
        sqls = (
            ["SELECT id FROM users WHERE age > 30"] * 8 +
            ["INSERT INTO t VALUES (1, 'a')"] * 8
        )
        p = make_pipeline(n_clusters=2, use_pca=False, random_state=0)
        X, labels = p.fit_from_sqls(sqls)

        select_cluster = set(labels[:8])
        insert_cluster = set(labels[8:])
        assert select_cluster != insert_cluster

    def test_n_clusters_parameter_respected(self):
        for k in [2, 3, 5]:
            p = make_pipeline(n_clusters=k)
            sqls = ALL_SQLS * 2  # 40개로 충분히 확보
            _, labels = p.fit_from_sqls(sqls)
            assert len(set(labels)) == k
