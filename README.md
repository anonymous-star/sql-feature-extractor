# SQL Structural Feature Extractor

`sqlglot` 기반으로 SQL 쿼리에서 **51개의 구조적 특성(structural features)** 을 추출하는 Python 라이브러리입니다.

## Feature 목록

| 카테고리 | Feature | 설명 |
|----------|---------|------|
| **Clause** | `has_select` | SELECT 절 존재 여부 |
| | `has_where` | WHERE 절 존재 여부 |
| | `has_group_by` | GROUP BY 절 존재 여부 |
| | `has_having` | HAVING 절 존재 여부 |
| | `has_order_by` | ORDER BY 절 존재 여부 |
| | `has_limit` | LIMIT/TOP 절 존재 여부 |
| | `has_distinct` | DISTINCT 키워드 존재 여부 |
| | `has_subquery` | 서브쿼리 존재 여부 |
| | `has_union` | UNION/UNION ALL 존재 여부 |
| | `has_intersect` | INTERSECT 존재 여부 |
| | `has_except` | EXCEPT 존재 여부 |
| | `has_cte` | WITH (CTE) 절 존재 여부 |
| | `has_case_when` | CASE WHEN 존재 여부 |
| | `has_window_func` | 윈도우 함수 (OVER) 존재 여부 |
| **JOIN** | `has_join` | JOIN 존재 여부 |
| | `join_count` | JOIN 총 개수 |
| | `has_inner_join` | INNER JOIN 여부 |
| | `has_left_join` | LEFT JOIN 여부 |
| | `has_right_join` | RIGHT JOIN 여부 |
| | `has_full_join` | FULL OUTER JOIN 여부 |
| | `has_cross_join` | CROSS JOIN 여부 |
| | `has_self_join` | 동일 테이블 JOIN 여부 |
| **Aggregation** | `has_aggregation` | 집계함수 존재 여부 |
| | `agg_func_count` | 집계함수 총 개수 |
| | `has_count` | COUNT 사용 여부 |
| | `has_sum` | SUM 사용 여부 |
| | `has_avg` | AVG 사용 여부 |
| | `has_min` | MIN 사용 여부 |
| | `has_max` | MAX 사용 여부 |
| **Count** | `num_tables` | 참조 테이블 수 (유니크) |
| | `num_columns` | SELECT 컬럼 수 |
| | `num_conditions` | WHERE 조건 수 |
| | `num_subqueries` | 서브쿼리 개수 |
| | `num_ctes` | CTE 개수 |
| | `subquery_depth` | 서브쿼리 최대 중첩 깊이 |
| | `num_predicates` | 조건절 술어 수 |
| | `num_group_by_cols` | GROUP BY 컬럼 수 |
| | `num_order_by_cols` | ORDER BY 컬럼 수 |
| **Operator** | `has_in` | IN 연산자 여부 |
| | `has_not_in` | NOT IN 여부 |
| | `has_exists` | EXISTS 여부 |
| | `has_like` | LIKE 여부 |
| | `has_between` | BETWEEN 여부 |
| | `has_null_check` | IS NULL / IS NOT NULL 여부 |
| | `has_arithmetic` | 산술 연산(+,-,*,/) 여부 |
| | `has_string_func` | 문자열 함수 여부 |
| | `has_date_func` | 날짜 함수 여부 |
| | `has_cast` | CAST/CONVERT 여부 |
| **Type** | `query_type` | SELECT / INSERT / UPDATE / DELETE / DDL |
| | `is_select` | SELECT 쿼리 여부 |
| | `is_dml` | DML 쿼리 여부 (INSERT/UPDATE/DELETE) |

---

## 설치

### 1. 저장소 클론

```bash
git clone https://github.com/anonymous-star/sql-feature-extractor.git
cd sql-feature-extractor
```

### 2. 가상환경 생성 및 의존성 설치

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install sqlglot             # 필수
pip install pandas              # extract_batch() 사용 시
pip install pytest              # 테스트 실행 시
```

---

## 사용법

### 단건 쿼리

```python
from sql_feature_extractor import SQLStructuralFeatureExtractor

extractor = SQLStructuralFeatureExtractor()

sql = """
    SELECT department, COUNT(*) AS cnt, AVG(salary) AS avg_sal
    FROM employees
    WHERE status = 'active'
    GROUP BY department
    HAVING COUNT(*) > 5
    ORDER BY avg_sal DESC
    LIMIT 10
"""

features = extractor.extract(sql)
print(features["has_group_by"])     # True
print(features["agg_func_count"])   # 3
print(features["query_type"])       # 'SELECT'
```

### 배치 처리 (pandas DataFrame)

```python
sql_list = [
    "SELECT id FROM users WHERE age > 30",
    "SELECT COUNT(*) FROM orders GROUP BY status",
    "INSERT INTO logs VALUES (1, 'login')",
]

df = extractor.extract_batch(sql_list)
print(df[["query_type", "has_where", "has_group_by", "agg_func_count"]])
```

출력 예시:

```
  query_type  has_where  has_group_by  agg_func_count
0     SELECT       True         False               0
1     SELECT      False          True               1
2     INSERT      False         False               0
```

### SQL 방언(dialect) 지정

```python
# MySQL, PostgreSQL, BigQuery, Spark, Snowflake 등 지원
extractor = SQLStructuralFeatureExtractor(dialect="bigquery")
features = extractor.extract("SELECT * FROM `project.dataset.table` LIMIT 10")
```

### 파싱 실패 처리

파싱에 실패하면 예외 없이 모든 feature가 `False` / `0` / `"UNKNOWN"` 으로 채워진 dict를 반환합니다.

```python
features = extractor.extract("THIS IS NOT SQL")
print(features["query_type"])   # 'UNKNOWN'
print(features["has_select"])   # False
```

---

## 테스트 실행

```bash
# 가상환경 활성화 후
pytest test_sql_feature_extractor.py -v
```

### 테스트 구성 (118개)

| 클래스 | 테스트 수 | 검증 내용 |
|--------|-----------|-----------|
| `TestInterface` | 7 | 반환 키 51개 완전 일치, 타입 검증, 파싱 실패 처리 |
| `TestClauseFeatures` | 19 | 14개 clause 존재 여부 |
| `TestJoinFeatures` | 10 | JOIN 유형별 감지, join_count |
| `TestAggregationFeatures` | 8 | 집계함수 종류 및 개수 |
| `TestCountFeatures` | 17 | 테이블/컬럼/조건/서브쿼리/CTE 수, 중첩 깊이 |
| `TestOperatorFeatures` | 22 | IN/NOT IN 구분, 함수 종류별 감지 |
| `TestQueryTypeFeatures` | 9 | SELECT/INSERT/UPDATE/DELETE/DDL 분류 |
| `TestComplexScenarios` | 9 | 실전 복합 쿼리 end-to-end 검증 |
| `TestEdgeCases` | 11 | SELECT *, 빈 WHERE, dialect 옵션 등 경계값 |

예상 출력:

```
collected 118 items
...
118 passed in 0.46s
```

---

## 지원 환경

- Python 3.8+
- sqlglot 20.0+

---

---

# SQL Clustering Guide

SQL 쿼리를 구조적 특성 기반으로 클러스터링하는 가이드입니다.
`sql_clustering.py` 의 `SQLClusteringPipeline` 을 사용합니다.

## 추가 의존성 설치

```bash
pip install scikit-learn joblib tqdm numpy pandas pyarrow
```

---

## 파이프라인 구조

```
SQL 이터러블
    │
    ▼
병렬 Feature 추출 (joblib, chunk 단위)
    │  50개 구조적 특성 → float32 행렬 (N × 50)
    ▼
StandardScaler 정규화
    │
    ▼
PCA 차원 축소 (선택, 50 → 20차원)
    │  클러스터링 속도 향상
    ▼
MiniBatchKMeans 클러스터링
    │  1회 데이터 스캔, 10M+ 대응
    ▼
클러스터 레이블 (N,) + 프로파일 분석
```

---

## 빠른 시작

```python
from sql_clustering import SQLClusteringPipeline

pipeline = SQLClusteringPipeline(n_clusters=10)

sql_list = [
    "SELECT id FROM users WHERE age > 30",
    "SELECT dept, COUNT(*) FROM emp GROUP BY dept",
    "SELECT * FROM a JOIN b ON a.id = b.id",
    # ...
]

X, labels = pipeline.fit_from_sqls(sql_list)
print(pipeline.summary(X, labels))
```

---

## 천만 건 대용량 처리

### 핵심 설정

```python
pipeline = SQLClusteringPipeline(
    n_clusters   = 30,          # 클러스터 수
    algorithm    = "minibatch_kmeans",  # 10M+ 권장
    use_pca      = True,        # 차원 축소로 속도 향상
    pca_components = 20,        # 축소 목표 차원
    chunk_size   = 50_000,      # 청크당 SQL 수
    n_jobs       = -1,          # CPU 전체 코어 사용
)
```

### DB 커서 / 파일 연동

```python
# DB 커서 (전체 데이터를 메모리에 올리지 않고 스트리밍)
import psycopg2

conn = psycopg2.connect(DSN)
cur = conn.cursor("server_side_cursor")  # 서버 사이드 커서
cur.execute("SELECT query_text FROM query_log")

def sql_generator():
    for row in cur:
        yield row[0]

X, labels = pipeline.fit_from_sqls(
    sql_generator(),
    total=10_000_000,           # tqdm 진행률 표시용
    feature_cache="features.npz",  # 추출 결과 캐시
)
```

```python
# 파일 (한 줄에 SQL 1개)
def file_generator(path):
    with open(path) as f:
        for line in f:
            yield line.strip()

X, labels = pipeline.fit_from_sqls(
    file_generator("sqls.txt"),
    feature_cache="features.npz",
)
```

### feature 캐시 활용

```python
# 첫 실행: 추출 후 .npz 로 저장
X, labels = pipeline.fit_from_sqls(sqls, feature_cache="features.npz")

# 재실행: 캐시에서 즉시 로드 (추출 생략)
X, labels = pipeline.fit_from_sqls(sqls, feature_cache="features.npz")
# [cache] 기존 feature 파일 로드: features.npz
```

---

## 최적 클러스터 수(k) 탐색

클러스터 수를 모를 때 Elbow 분석으로 결정합니다.

```python
pipeline = SQLClusteringPipeline()
X = pipeline.extract_features(sqls, feature_cache="features.npz")

elbow_df = pipeline.find_optimal_k(
    X,
    k_range    = range(5, 51, 5),   # 5, 10, 15 ... 50
    sample_size = 100_000,           # 샘플에서 계산 (빠름)
)
print(elbow_df)
```

출력 예시:

```
  k      inertia
  5   8423.12
 10   5201.44
 15   3987.23     ← inertia 감소폭이 둔해지는 지점 선택
 20   3812.10
 25   3790.55
```

inertia 감소폭이 크게 줄어드는 **elbow point** 를 `n_clusters` 로 사용합니다.

---

## 알고리즘 선택

| 알고리즘 | 속도 | 품질 | 권장 규모 |
|----------|------|------|-----------|
| `minibatch_kmeans` | 매우 빠름 | 보통 | **10M+ 권장** |
| `bisecting_kmeans` | 보통 | 우수 | ~수백만 건 |

```python
# 수백만 건 이하: 품질 우선
pipeline = SQLClusteringPipeline(algorithm="bisecting_kmeans", n_clusters=20)

# 천만 건 이상: 속도 우선
pipeline = SQLClusteringPipeline(algorithm="minibatch_kmeans", n_clusters=20)
```

---

## 클러스터 분석 및 해석

### 전체 요약

```python
summary = pipeline.summary(X, labels)
print(summary)
```

```
         size   ratio               top_features  avg_tables  avg_joins  avg_depth
cluster
2        3821  0.382   has_where, is_select, ...        1.12       0.00       0.00
0        2145  0.215   has_aggregation, has_count       1.00       0.00       0.00
1        1834  0.183   has_join, has_inner_join, ...    2.67       1.43       0.00
3        1200  0.120   has_subquery, has_in, ...        2.10       0.00       1.25
```

| 컬럼 | 설명 |
|------|------|
| `size` | 클러스터 내 SQL 수 |
| `ratio` | 전체 대비 비율 |
| `top_features` | 평균값이 높은 상위 3개 feature |
| `avg_tables` | 평균 참조 테이블 수 |
| `avg_joins` | 평균 JOIN 수 |
| `avg_depth` | 평균 서브쿼리 중첩 깊이 |

### 특정 클러스터 상세 분석

```python
pipeline.describe_cluster(X, labels, cluster_id=1, top_n=10)
```

```
[Cluster 1]  size=1,834 (18.3%)
has_join          1.000000
has_inner_join    0.821000
num_tables        2.670000
has_select        1.000000
join_count        1.430000
...
```

### feature 프로파일 전체 조회

```python
profiles = pipeline.cluster_profiles(X, labels)
# index=cluster_id, columns=feature_cols + size + ratio
print(profiles[["num_tables", "join_count", "has_aggregation", "subquery_depth"]])
```

---

## 파이프라인 저장 / 로드

```python
# 학습 완료 후 저장
pipeline.save("sql_pipeline.joblib")

# 나중에 로드해서 새 SQL 분류
from sql_clustering import SQLClusteringPipeline

pipeline = SQLClusteringPipeline.load("sql_pipeline.joblib")

new_sqls = ["SELECT COUNT(*) FROM orders GROUP BY status"]
X_new    = pipeline.extract_features(new_sqls)
labels   = pipeline.predict(X_new)
print(labels)   # [2]
```

---

## 파라미터 튜닝 가이드

| 상황 | 권장 설정 |
|------|-----------|
| 10M+ 쿼리, 빠른 처리 우선 | `algorithm="minibatch_kmeans"`, `use_pca=True`, `n_jobs=-1` |
| 수백만 건, 품질 우선 | `algorithm="bisecting_kmeans"`, `use_pca=False` |
| 클러스터 수 모름 | `find_optimal_k()` 로 elbow 분석 후 결정 |
| 재현성 필요 | `random_state=42` 고정 |
| 메모리 부족 | `chunk_size` 축소 (예: 10_000) |
| 처리 느림 | `chunk_size` 확대 (예: 100_000), `n_jobs=-1` |

---

## 테스트 실행

```bash
pytest test_sql_clustering.py -v
```

### 테스트 구성 (61개)

| 클래스 | 테스트 수 | 검증 내용 |
|--------|-----------|-----------|
| `TestUtils` | 7 | 청크 분할, feature 추출 형태/타입 |
| `TestFeatureCols` | 4 | 50개 컬럼, 중복 없음 |
| `TestExtractFeatures` | 12 | shape/dtype, 캐시, 제너레이터, 청크 경계 |
| `TestFitPredict` | 11 | 모델 세팅, 레이블 범위, 결정론성, 알고리즘 분기 |
| `TestFitFromSqls` | 4 | 반환 타입/shape, 캐시 연동 |
| `TestClusterAnalysis` | 10 | 프로파일 shape, size 합계, ratio 합=1.0 |
| `TestFindOptimalK` | 5 | DataFrame 반환, inertia 단조감소 |
| `TestSaveLoad` | 5 | 저장/로드, 예측 일치, 하이퍼파라미터 보존 |
| `TestClusteringQuality` | 3 | 유사 SQL 동일 클러스터, DML/SELECT 분리 |

```
61 passed in 4.64s
```
