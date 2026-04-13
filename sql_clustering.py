"""
SQL Clustering Pipeline
========================
SQL 쿼리를 구조적 특성(structural features) 기반으로 클러스터링합니다.
천만 건 단위의 대용량 처리를 위해 아래 전략을 사용합니다.

  - 병렬 Feature 추출  : joblib.Parallel + 청크 단위 처리
  - 메모리 효율        : float32 numpy 배열 (10M×51 ≈ 2GB)
  - 빠른 클러스터링    : MiniBatchKMeans (전체 데이터 1회 스캔)
  - 체크포인트 저장    : .npz / parquet 으로 재사용

Requirements:
    pip install sqlglot scikit-learn joblib tqdm numpy pandas pyarrow
"""

from __future__ import annotations

import os
import time
import warnings
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd
from joblib import Parallel, delayed, dump, load
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import MiniBatchKMeans, BisectingKMeans
from tqdm import tqdm

from sql_feature_extractor import SQLStructuralFeatureExtractor

warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# Feature 컬럼 정의
# ---------------------------------------------------------------------------

BOOL_FEATURES = [
    "has_select", "has_where", "has_group_by", "has_having",
    "has_order_by", "has_limit", "has_distinct", "has_subquery",
    "has_union", "has_intersect", "has_except", "has_cte",
    "has_case_when", "has_window_func",
    "has_join", "has_inner_join", "has_left_join", "has_right_join",
    "has_full_join", "has_cross_join", "has_self_join",
    "has_aggregation", "has_count", "has_sum", "has_avg", "has_min", "has_max",
    "has_in", "has_not_in", "has_exists", "has_like", "has_between",
    "has_null_check", "has_arithmetic", "has_string_func", "has_date_func",
    "has_cast", "is_select", "is_dml",
]

NUM_FEATURES = [
    "join_count", "agg_func_count",
    "num_tables", "num_columns", "num_conditions", "num_subqueries",
    "num_ctes", "subquery_depth", "num_predicates",
    "num_group_by_cols", "num_order_by_cols",
]

FEATURE_COLS = BOOL_FEATURES + NUM_FEATURES   # 총 50개 (query_type 제외)


# ---------------------------------------------------------------------------
# 유틸: 청크 분할
# ---------------------------------------------------------------------------

def _chunked(iterable: Iterable, size: int) -> Iterator[List]:
    """이터러블을 size 단위 청크 리스트로 분할."""
    buf: List = []
    for item in iterable:
        buf.append(item)
        if len(buf) == size:
            yield buf
            buf = []
    if buf:
        yield buf


# ---------------------------------------------------------------------------
# 단일 청크 feature 추출 (subprocess 에서 실행)
# ---------------------------------------------------------------------------

def _extract_chunk(sqls: List[str], dialect: Optional[str]) -> np.ndarray:
    """청크 단위로 feature 를 추출하여 float32 배열로 반환."""
    ex = SQLStructuralFeatureExtractor(dialect=dialect)
    rows = []
    for sql in sqls:
        f = ex.extract(sql)
        rows.append([float(f[c]) for c in FEATURE_COLS])
    return np.array(rows, dtype=np.float32)


# ---------------------------------------------------------------------------
# 메인 파이프라인
# ---------------------------------------------------------------------------

class SQLClusteringPipeline:
    """
    대용량 SQL 클러스터링 파이프라인.

    Parameters
    ----------
    n_clusters : int
        클러스터 수. None 이면 elbow 분석 후 자동 결정.
    algorithm : {'minibatch_kmeans', 'bisecting_kmeans'}
        클러스터링 알고리즘.
        - minibatch_kmeans : 가장 빠름, 10M+ 권장
        - bisecting_kmeans : 품질 우수, 수백만 건까지
    use_pca : bool
        PCA로 차원 축소 여부 (클러스터링 속도 향상).
    pca_components : int
        PCA 축소 목표 차원 수.
    chunk_size : int
        병렬 처리 청크 크기.
    n_jobs : int
        병렬 워커 수. -1 이면 CPU 전체 사용.
    dialect : str | None
        SQL 방언.
    random_state : int
        재현성을 위한 시드값.
    """

    def __init__(
        self,
        n_clusters: int = 20,
        algorithm: str = "minibatch_kmeans",
        use_pca: bool = True,
        pca_components: int = 20,
        chunk_size: int = 50_000,
        n_jobs: int = -1,
        dialect: Optional[str] = None,
        random_state: int = 42,
    ):
        self.n_clusters = n_clusters
        self.algorithm = algorithm
        self.use_pca = use_pca
        self.pca_components = pca_components
        self.chunk_size = chunk_size
        self.n_jobs = n_jobs
        self.dialect = dialect
        self.random_state = random_state

        self.scaler_: Optional[StandardScaler] = None
        self.pca_: Optional[PCA] = None
        self.model_: Optional[MiniBatchKMeans | BisectingKMeans] = None
        self.feature_cols_ = FEATURE_COLS

    # ------------------------------------------------------------------
    # 1. Feature 추출
    # ------------------------------------------------------------------

    def extract_features(
        self,
        sql_iter: Iterable[str],
        total: Optional[int] = None,
        save_path: Optional[str] = None,
    ) -> np.ndarray:
        """
        SQL 이터러블에서 feature 행렬을 병렬로 추출.

        Parameters
        ----------
        sql_iter : Iterable[str]
            SQL 문자열 이터러블 (파일, DB 커서, 리스트 등).
        total : int | None
            전체 건수 (tqdm 진행률 표시용).
        save_path : str | None
            .npz 로 중간 저장할 경로. 이미 존재하면 로드해서 반환.

        Returns
        -------
        X : np.ndarray, shape (N, 50), dtype float32
        """
        if save_path and Path(save_path).exists():
            print(f"[cache] 기존 feature 파일 로드: {save_path}")
            return np.load(save_path)["X"]

        t0 = time.time()
        chunks = list(_chunked(
            tqdm(sql_iter, total=total, desc="reading SQLs", unit="sql"),
            self.chunk_size,
        ))

        print(f"[extract] {len(chunks)}개 청크 × {self.chunk_size} | "
              f"워커 수: {self.n_jobs}")

        results: List[np.ndarray] = Parallel(n_jobs=self.n_jobs, backend="loky")(
            delayed(_extract_chunk)(chunk, self.dialect)
            for chunk in tqdm(chunks, desc="extracting features", unit="chunk")
        )

        X = np.vstack(results).astype(np.float32)
        elapsed = time.time() - t0
        print(f"[extract] 완료: {X.shape[0]:,}건 | {elapsed:.1f}s "
              f"({X.shape[0]/elapsed:,.0f} SQL/s)")

        if save_path:
            np.savez_compressed(save_path, X=X)
            print(f"[cache] feature 저장 완료: {save_path}")

        return X

    # ------------------------------------------------------------------
    # 2. 전처리
    # ------------------------------------------------------------------

    def _preprocess(self, X: np.ndarray, fit: bool = True) -> np.ndarray:
        """StandardScaler → (선택) PCA."""
        if fit:
            self.scaler_ = StandardScaler()
            X = self.scaler_.fit_transform(X)
        else:
            X = self.scaler_.transform(X)

        if self.use_pca:
            n_comp = min(self.pca_components, X.shape[1], X.shape[0])
            if fit:
                self.pca_ = PCA(n_components=n_comp, random_state=self.random_state)
                X = self.pca_.fit_transform(X)
                var = self.pca_.explained_variance_ratio_.sum()
                print(f"[PCA] {n_comp}차원 | 설명 분산: {var:.1%}")
            else:
                X = self.pca_.transform(X)

        return X.astype(np.float32)

    # ------------------------------------------------------------------
    # 3. 클러스터링
    # ------------------------------------------------------------------

    def fit(self, X: np.ndarray) -> "SQLClusteringPipeline":
        """
        feature 행렬로 클러스터링 모델을 학습.

        Parameters
        ----------
        X : np.ndarray, shape (N, 50)
            extract_features() 의 반환값.
        """
        print(f"\n[fit] 입력 크기: {X.shape[0]:,} × {X.shape[1]}")

        # 전처리
        Xt = self._preprocess(X, fit=True)

        # 클러스터링
        t0 = time.time()
        if self.algorithm == "minibatch_kmeans":
            self.model_ = MiniBatchKMeans(
                n_clusters=self.n_clusters,
                batch_size=min(10_000, X.shape[0]),
                max_iter=100,
                n_init=3,
                random_state=self.random_state,
                verbose=0,
            )
        elif self.algorithm == "bisecting_kmeans":
            self.model_ = BisectingKMeans(
                n_clusters=self.n_clusters,
                random_state=self.random_state,
            )
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")

        self.model_.fit(Xt)
        elapsed = time.time() - t0
        inertia = self.model_.inertia_
        print(f"[fit] 완료: {elapsed:.1f}s | inertia={inertia:,.1f}")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """학습된 모델로 클러스터 레이블 예측."""
        Xt = self._preprocess(X, fit=False)
        return self.model_.predict(Xt)

    def fit_predict(self, X: np.ndarray) -> np.ndarray:
        """fit 후 레이블 반환."""
        self.fit(X)
        Xt = self._preprocess(X, fit=False)
        return self.model_.predict(Xt)

    # ------------------------------------------------------------------
    # 4. 엔드-투-엔드
    # ------------------------------------------------------------------

    def fit_from_sqls(
        self,
        sql_iter: Iterable[str],
        total: Optional[int] = None,
        feature_cache: Optional[str] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        SQL 이터러블에서 feature 추출 → 클러스터링까지 한 번에 실행.

        Returns
        -------
        X      : np.ndarray (N, 50)  — 원본 feature 행렬
        labels : np.ndarray (N,)     — 클러스터 레이블
        """
        X = self.extract_features(sql_iter, total=total, save_path=feature_cache)
        labels = self.fit_predict(X)
        return X, labels

    # ------------------------------------------------------------------
    # 5. 클러스터 분석
    # ------------------------------------------------------------------

    def cluster_profiles(
        self,
        X: np.ndarray,
        labels: np.ndarray,
    ) -> pd.DataFrame:
        """
        클러스터별 feature 평균 프로파일 DataFrame 반환.

        Returns
        -------
        pd.DataFrame : index=cluster_id, columns=feature_cols + ['size', 'ratio']
        """
        df = pd.DataFrame(X, columns=self.feature_cols_)
        df["cluster"] = labels

        agg = df.groupby("cluster").mean()
        sizes = df["cluster"].value_counts().sort_index().rename("size")
        agg["size"] = sizes
        agg["ratio"] = agg["size"] / len(labels)
        return agg.sort_values("size", ascending=False)

    def describe_cluster(
        self,
        X: np.ndarray,
        labels: np.ndarray,
        cluster_id: int,
        top_n: int = 10,
    ) -> pd.Series:
        """
        특정 클러스터의 대표 feature (평균이 높은 순) 출력.
        """
        mask = labels == cluster_id
        size = mask.sum()
        mean = X[mask].mean(axis=0)
        s = pd.Series(mean, index=self.feature_cols_).sort_values(ascending=False)
        print(f"\n[Cluster {cluster_id}]  size={size:,} ({size/len(labels):.1%})")
        print(s.head(top_n).to_string())
        return s

    def summary(self, X: np.ndarray, labels: np.ndarray) -> pd.DataFrame:
        """
        전체 클러스터 요약 (크기 + 주요 특성).
        """
        profiles = self.cluster_profiles(X, labels)
        bool_cols = [c for c in BOOL_FEATURES if c in self.feature_cols_]
        num_cols  = [c for c in NUM_FEATURES  if c in self.feature_cols_]

        # 각 클러스터에서 가장 높은 boolean feature 3개
        def top_flags(row):
            return ", ".join(
                row[bool_cols].sort_values(ascending=False).head(3).index.tolist()
            )

        summary_df = profiles[["size", "ratio"]].copy()
        summary_df["top_features"] = profiles.apply(top_flags, axis=1)
        summary_df["avg_tables"]   = profiles["num_tables"].round(2)
        summary_df["avg_joins"]    = profiles["join_count"].round(2)
        summary_df["avg_depth"]    = profiles["subquery_depth"].round(2)
        return summary_df

    # ------------------------------------------------------------------
    # 6. 최적 k 탐색 (Elbow)
    # ------------------------------------------------------------------

    def find_optimal_k(
        self,
        X: np.ndarray,
        k_range: range = range(5, 51, 5),
        sample_size: int = 100_000,
    ) -> pd.DataFrame:
        """
        샘플에 대해 여러 k 로 MiniBatchKMeans를 실행하여 inertia 반환.
        결과를 보고 elbow point를 선택하세요.
        """
        if len(X) > sample_size:
            idx = np.random.choice(len(X), sample_size, replace=False)
            Xs = X[idx]
            print(f"[elbow] 샘플링 {sample_size:,} / {len(X):,}")
        else:
            Xs = X

        scaler = StandardScaler()
        Xs = scaler.fit_transform(Xs).astype(np.float32)

        rows = []
        for k in tqdm(k_range, desc="elbow search"):
            m = MiniBatchKMeans(n_clusters=k, n_init=3, random_state=self.random_state)
            m.fit(Xs)
            rows.append({"k": k, "inertia": m.inertia_})

        df = pd.DataFrame(rows)
        print("\n[elbow] k vs inertia:")
        print(df.to_string(index=False))
        return df

    # ------------------------------------------------------------------
    # 7. 저장 / 로드
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """파이프라인 전체 (scaler + pca + model) 저장."""
        dump(self, path)
        print(f"[save] 파이프라인 저장: {path}")

    @classmethod
    def load(cls, path: str) -> "SQLClusteringPipeline":
        """저장된 파이프라인 로드."""
        pipeline = load(path)
        print(f"[load] 파이프라인 로드: {path}")
        return pipeline


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

DEMO_SQLS = [
    # 단순 조회
    "SELECT id, name FROM users WHERE age > 30",
    "SELECT * FROM products WHERE price < 100",
    "SELECT id FROM orders WHERE status = 'pending'",
    "SELECT email FROM customers WHERE country = 'KR'",

    # 집계
    "SELECT dept, COUNT(*) FROM emp GROUP BY dept",
    "SELECT category, SUM(revenue) FROM sales GROUP BY category ORDER BY 2 DESC",
    "SELECT user_id, AVG(score) FROM ratings GROUP BY user_id HAVING AVG(score) > 4",
    "SELECT MIN(price), MAX(price), AVG(price) FROM products",

    # JOIN
    "SELECT o.id, c.name FROM orders o JOIN customers c ON o.cid = c.id",
    "SELECT * FROM a LEFT JOIN b ON a.id = b.id LEFT JOIN c ON b.id = c.id",
    "SELECT * FROM emp a JOIN emp b ON a.mgr_id = b.id",  # self-join

    # 서브쿼리
    "SELECT * FROM t WHERE id IN (SELECT id FROM t2 WHERE val > 100)",
    "SELECT * FROM products WHERE price > (SELECT AVG(price) FROM products)",
    "SELECT * FROM t1 WHERE id IN (SELECT id FROM t2 WHERE x > (SELECT MAX(x) FROM t3))",

    # CTE + 윈도우
    "WITH top AS (SELECT id, RANK() OVER (ORDER BY score DESC) r FROM t) SELECT * FROM top WHERE r <= 10",
    "WITH a AS (SELECT 1), b AS (SELECT 2) SELECT * FROM a, b",

    # DML
    "INSERT INTO logs (uid, action) VALUES (1, 'login')",
    "UPDATE users SET status = 'inactive' WHERE last_login < '2023-01-01'",
    "DELETE FROM sessions WHERE expires_at < NOW()",

    # 복합
    "SELECT UPPER(name), CAST(price*1.1 AS INT) FROM t WHERE name LIKE '%sale%' AND price BETWEEN 10 AND 500",
    "SELECT DISTINCT category FROM products WHERE id NOT IN (SELECT pid FROM banned)",
    "SELECT * FROM a CROSS JOIN b",
    "SELECT id FROM t UNION ALL SELECT id FROM t2 UNION ALL SELECT id FROM t3",
]


def main():
    print("=" * 65)
    print("SQL Clustering Pipeline — Demo")
    print("=" * 65)

    pipeline = SQLClusteringPipeline(
        n_clusters=5,
        algorithm="minibatch_kmeans",
        use_pca=True,
        pca_components=10,
        chunk_size=100,
        n_jobs=1,           # 데모: 단일 프로세스
    )

    # Feature 추출 + 클러스터링
    X, labels = pipeline.fit_from_sqls(DEMO_SQLS, total=len(DEMO_SQLS))

    # 요약
    print("\n[Summary]")
    print(pipeline.summary(X, labels).to_string())

    # 각 클러스터 상위 feature
    for cid in sorted(set(labels)):
        pipeline.describe_cluster(X, labels, cid, top_n=5)

    # 어느 SQL이 어느 클러스터인지
    print("\n[SQL → Cluster 할당]")
    for sql, label in zip(DEMO_SQLS, labels):
        print(f"  [{label}] {sql[:70]}")

    # 파이프라인 저장 예시
    pipeline.save("sql_clustering_pipeline.joblib")
    loaded = SQLClusteringPipeline.load("sql_clustering_pipeline.joblib")
    print("\n[reload] 새 SQL 예측:")
    new_sqls = ["SELECT COUNT(*) FROM orders GROUP BY status"]
    X_new = loaded.extract_features(new_sqls)
    print(f"  클러스터 = {loaded.predict(X_new)[0]}")


if __name__ == "__main__":
    main()
