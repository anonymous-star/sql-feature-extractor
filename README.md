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
