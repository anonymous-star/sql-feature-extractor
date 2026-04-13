"""
Tests for SQLStructuralFeatureExtractor
========================================
pytest 기반. 카테고리별로 클래스를 분리하여 각 feature 를 독립적으로 검증합니다.

실행:
    pytest test_sql_feature_extractor.py -v
"""

import pytest
from sql_feature_extractor import SQLStructuralFeatureExtractor


@pytest.fixture(scope="module")
def ex():
    return SQLStructuralFeatureExtractor()


# ============================================================================
# 헬퍼
# ============================================================================

EXPECTED_KEYS = {
    # Clause
    "has_select", "has_where", "has_group_by", "has_having",
    "has_order_by", "has_limit", "has_distinct", "has_subquery",
    "has_union", "has_intersect", "has_except", "has_cte",
    "has_case_when", "has_window_func",
    # JOIN
    "has_join", "join_count", "has_inner_join", "has_left_join",
    "has_right_join", "has_full_join", "has_cross_join", "has_self_join",
    # Aggregation
    "has_aggregation", "agg_func_count",
    "has_count", "has_sum", "has_avg", "has_min", "has_max",
    # Count
    "num_tables", "num_columns", "num_conditions", "num_subqueries",
    "num_ctes", "subquery_depth", "num_predicates",
    "num_group_by_cols", "num_order_by_cols",
    # Operators
    "has_in", "has_not_in", "has_exists", "has_like", "has_between",
    "has_null_check", "has_arithmetic", "has_string_func",
    "has_date_func", "has_cast",
    # Type
    "query_type", "is_select", "is_dml",
}


# ============================================================================
# 1. 공통 인터페이스 검증
# ============================================================================

class TestInterface:
    """extract() 반환값의 구조 및 타입을 검증."""

    def test_returns_all_51_keys(self, ex):
        f = ex.extract("SELECT 1")
        assert set(f.keys()) == EXPECTED_KEYS

    def test_boolean_features_are_bool(self, ex):
        f = ex.extract("SELECT id FROM t WHERE x = 1")
        bool_keys = [k for k in f if k.startswith("has_") or k.startswith("is_")]
        for k in bool_keys:
            assert isinstance(f[k], bool), f"{k} should be bool, got {type(f[k])}"

    def test_count_features_are_int(self, ex):
        f = ex.extract("SELECT id FROM t")
        int_keys = [k for k in f if k.startswith("num_") or k == "join_count" or k == "agg_func_count"]
        for k in int_keys:
            assert isinstance(f[k], int), f"{k} should be int, got {type(f[k])}"

    def test_query_type_is_str(self, ex):
        assert isinstance(ex.extract("SELECT 1")["query_type"], str)

    def test_invalid_sql_returns_null_features(self, ex):
        f = ex.extract("THIS IS NOT SQL @@###")
        assert f["has_select"] is False
        assert f["num_tables"] == 0
        assert f["query_type"] == "UNKNOWN"

    def test_empty_string_returns_null_features(self, ex):
        f = ex.extract("")
        assert f["query_type"] == "UNKNOWN"
        assert f["is_select"] is False

    def test_whitespace_only_returns_null_features(self, ex):
        f = ex.extract("   \n\t  ")
        assert f["query_type"] == "UNKNOWN"


# ============================================================================
# 2. Clause 존재 여부
# ============================================================================

class TestClauseFeatures:

    def test_has_select_true(self, ex):
        assert ex.extract("SELECT 1")["has_select"] is True

    def test_has_where_true(self, ex):
        assert ex.extract("SELECT id FROM t WHERE id = 1")["has_where"] is True

    def test_has_where_false(self, ex):
        assert ex.extract("SELECT id FROM t")["has_where"] is False

    def test_has_group_by(self, ex):
        f = ex.extract("SELECT dept, COUNT(*) FROM emp GROUP BY dept")
        assert f["has_group_by"] is True

    def test_no_group_by(self, ex):
        assert ex.extract("SELECT id FROM t")["has_group_by"] is False

    def test_has_having(self, ex):
        f = ex.extract("SELECT dept, COUNT(*) FROM emp GROUP BY dept HAVING COUNT(*) > 3")
        assert f["has_having"] is True

    def test_has_order_by(self, ex):
        assert ex.extract("SELECT id FROM t ORDER BY id DESC")["has_order_by"] is True

    def test_has_limit(self, ex):
        assert ex.extract("SELECT id FROM t LIMIT 10")["has_limit"] is True

    def test_has_distinct(self, ex):
        assert ex.extract("SELECT DISTINCT name FROM t")["has_distinct"] is True

    def test_no_distinct(self, ex):
        assert ex.extract("SELECT name FROM t")["has_distinct"] is False

    def test_has_subquery(self, ex):
        f = ex.extract("SELECT * FROM (SELECT id FROM t) sub")
        assert f["has_subquery"] is True

    def test_has_union(self, ex):
        f = ex.extract("SELECT id FROM a UNION SELECT id FROM b")
        assert f["has_union"] is True

    def test_has_union_all(self, ex):
        f = ex.extract("SELECT id FROM a UNION ALL SELECT id FROM b")
        assert f["has_union"] is True

    def test_has_intersect(self, ex):
        f = ex.extract("SELECT id FROM a INTERSECT SELECT id FROM b")
        assert f["has_intersect"] is True

    def test_has_except(self, ex):
        f = ex.extract("SELECT id FROM a EXCEPT SELECT id FROM b")
        assert f["has_except"] is True

    def test_has_cte(self, ex):
        f = ex.extract("WITH cte AS (SELECT 1 AS n) SELECT * FROM cte")
        assert f["has_cte"] is True

    def test_has_case_when(self, ex):
        f = ex.extract("SELECT CASE WHEN x > 0 THEN 'pos' ELSE 'neg' END FROM t")
        assert f["has_case_when"] is True

    def test_has_window_func(self, ex):
        f = ex.extract("SELECT ROW_NUMBER() OVER (ORDER BY id) FROM t")
        assert f["has_window_func"] is True

    def test_no_window_func(self, ex):
        assert ex.extract("SELECT id FROM t")["has_window_func"] is False


# ============================================================================
# 3. JOIN
# ============================================================================

class TestJoinFeatures:

    def test_no_join(self, ex):
        f = ex.extract("SELECT id FROM t")
        assert f["has_join"] is False
        assert f["join_count"] == 0

    def test_plain_join_is_inner(self, ex):
        f = ex.extract("SELECT * FROM a JOIN b ON a.id = b.id")
        assert f["has_join"] is True
        assert f["join_count"] == 1
        assert f["has_inner_join"] is True

    def test_explicit_inner_join(self, ex):
        f = ex.extract("SELECT * FROM a INNER JOIN b ON a.id = b.id")
        assert f["has_inner_join"] is True

    def test_left_join(self, ex):
        f = ex.extract("SELECT * FROM a LEFT JOIN b ON a.id = b.id")
        assert f["has_left_join"] is True
        assert f["has_right_join"] is False

    def test_right_join(self, ex):
        f = ex.extract("SELECT * FROM a RIGHT JOIN b ON a.id = b.id")
        assert f["has_right_join"] is True
        assert f["has_left_join"] is False

    def test_full_outer_join(self, ex):
        f = ex.extract("SELECT * FROM a FULL OUTER JOIN b ON a.id = b.id")
        assert f["has_full_join"] is True

    def test_cross_join(self, ex):
        f = ex.extract("SELECT * FROM a CROSS JOIN b")
        assert f["has_cross_join"] is True

    def test_multiple_joins_count(self, ex):
        sql = """
            SELECT * FROM orders o
            INNER JOIN customers c ON o.cid = c.id
            LEFT  JOIN products  p ON o.pid = p.id
        """
        f = ex.extract(sql)
        assert f["join_count"] == 2
        assert f["has_inner_join"] is True
        assert f["has_left_join"] is True

    def test_self_join(self, ex):
        f = ex.extract("SELECT a.id FROM emp a JOIN emp b ON a.mgr_id = b.id")
        assert f["has_self_join"] is True

    def test_no_self_join(self, ex):
        f = ex.extract("SELECT * FROM a JOIN b ON a.id = b.id")
        assert f["has_self_join"] is False


# ============================================================================
# 4. Aggregation
# ============================================================================

class TestAggregationFeatures:

    def test_no_aggregation(self, ex):
        f = ex.extract("SELECT id, name FROM t")
        assert f["has_aggregation"] is False
        assert f["agg_func_count"] == 0

    def test_count(self, ex):
        f = ex.extract("SELECT COUNT(*) FROM t")
        assert f["has_count"] is True
        assert f["has_aggregation"] is True
        assert f["agg_func_count"] == 1

    def test_sum(self, ex):
        f = ex.extract("SELECT SUM(amount) FROM orders")
        assert f["has_sum"] is True

    def test_avg(self, ex):
        f = ex.extract("SELECT AVG(salary) FROM emp")
        assert f["has_avg"] is True

    def test_min(self, ex):
        f = ex.extract("SELECT MIN(price) FROM products")
        assert f["has_min"] is True

    def test_max(self, ex):
        f = ex.extract("SELECT MAX(score) FROM results")
        assert f["has_max"] is True

    def test_multiple_agg_funcs(self, ex):
        f = ex.extract("SELECT COUNT(*), SUM(x), AVG(y), MIN(z), MAX(w) FROM t")
        assert f["agg_func_count"] == 5
        assert f["has_count"] is True
        assert f["has_sum"] is True
        assert f["has_avg"] is True
        assert f["has_min"] is True
        assert f["has_max"] is True

    def test_agg_func_count_accuracy(self, ex):
        f = ex.extract("SELECT COUNT(*), COUNT(DISTINCT id) FROM t")
        assert f["agg_func_count"] == 2


# ============================================================================
# 5. 수치/카운트
# ============================================================================

class TestCountFeatures:

    def test_num_tables_single(self, ex):
        assert ex.extract("SELECT id FROM users")["num_tables"] == 1

    def test_num_tables_with_join(self, ex):
        f = ex.extract("SELECT * FROM a JOIN b ON a.id = b.id JOIN c ON b.id = c.id")
        assert f["num_tables"] == 3

    def test_num_tables_dedup(self, ex):
        # self-join: 같은 테이블 두 번 → unique 기준 1
        f = ex.extract("SELECT * FROM emp a JOIN emp b ON a.mgr = b.id")
        assert f["num_tables"] == 1

    def test_num_columns_select_star(self, ex):
        # SELECT * → 1개 (Star expression)
        assert ex.extract("SELECT * FROM t")["num_columns"] == 1

    def test_num_columns_explicit(self, ex):
        f = ex.extract("SELECT id, name, email FROM users")
        assert f["num_columns"] == 3

    def test_num_conditions_single(self, ex):
        f = ex.extract("SELECT * FROM t WHERE x = 1")
        assert f["num_conditions"] == 1

    def test_num_conditions_multiple(self, ex):
        f = ex.extract("SELECT * FROM t WHERE x = 1 AND y > 2 AND z < 3")
        assert f["num_conditions"] == 3

    def test_num_conditions_no_where(self, ex):
        assert ex.extract("SELECT * FROM t")["num_conditions"] == 0

    def test_num_subqueries_none(self, ex):
        assert ex.extract("SELECT id FROM t")["num_subqueries"] == 0

    def test_num_subqueries_one(self, ex):
        f = ex.extract("SELECT * FROM t WHERE id IN (SELECT id FROM t2)")
        assert f["num_subqueries"] == 1

    def test_num_subqueries_two(self, ex):
        sql = """
            SELECT * FROM t1
            WHERE id IN (
                SELECT id FROM t2
                WHERE val > (SELECT MAX(val) FROM t3)
            )
        """
        f = ex.extract(sql)
        assert f["num_subqueries"] == 2

    def test_subquery_depth_zero(self, ex):
        assert ex.extract("SELECT id FROM t")["subquery_depth"] == 0

    def test_subquery_depth_one(self, ex):
        f = ex.extract("SELECT * FROM t WHERE id IN (SELECT id FROM t2)")
        assert f["subquery_depth"] == 1

    def test_subquery_depth_two(self, ex):
        sql = """
            SELECT * FROM t1
            WHERE id IN (
                SELECT id FROM t2
                WHERE val > (SELECT MAX(val) FROM t3)
            )
        """
        assert ex.extract(sql)["subquery_depth"] == 2

    def test_num_ctes_zero(self, ex):
        assert ex.extract("SELECT id FROM t")["num_ctes"] == 0

    def test_num_ctes_one(self, ex):
        f = ex.extract("WITH cte AS (SELECT 1) SELECT * FROM cte")
        assert f["num_ctes"] == 1

    def test_num_ctes_two(self, ex):
        f = ex.extract("WITH a AS (SELECT 1), b AS (SELECT 2) SELECT * FROM a, b")
        assert f["num_ctes"] == 2

    def test_num_group_by_cols(self, ex):
        f = ex.extract("SELECT a, b, COUNT(*) FROM t GROUP BY a, b")
        assert f["num_group_by_cols"] == 2

    def test_num_order_by_cols(self, ex):
        f = ex.extract("SELECT id FROM t ORDER BY name ASC, age DESC")
        assert f["num_order_by_cols"] == 2

    def test_num_group_by_zero(self, ex):
        assert ex.extract("SELECT id FROM t")["num_group_by_cols"] == 0

    def test_num_conditions_equals_num_predicates(self, ex):
        f = ex.extract("SELECT * FROM t WHERE a = 1 AND b > 2")
        assert f["num_conditions"] == f["num_predicates"]


# ============================================================================
# 6. 연산자/표현식
# ============================================================================

class TestOperatorFeatures:

    def test_has_in(self, ex):
        f = ex.extract("SELECT * FROM t WHERE id IN (1, 2, 3)")
        assert f["has_in"] is True

    def test_has_not_in(self, ex):
        f = ex.extract("SELECT * FROM t WHERE id NOT IN (1, 2, 3)")
        assert f["has_not_in"] is True
        assert f["has_in"] is True  # NOT IN 도 IN 의 일종

    def test_in_without_not(self, ex):
        f = ex.extract("SELECT * FROM t WHERE id IN (1, 2, 3)")
        assert f["has_not_in"] is False

    def test_has_exists(self, ex):
        f = ex.extract("SELECT * FROM t WHERE EXISTS (SELECT 1 FROM t2 WHERE t2.id = t.id)")
        assert f["has_exists"] is True

    def test_no_exists(self, ex):
        assert ex.extract("SELECT * FROM t WHERE id = 1")["has_exists"] is False

    def test_has_like(self, ex):
        f = ex.extract("SELECT * FROM t WHERE name LIKE '%foo%'")
        assert f["has_like"] is True

    def test_has_between(self, ex):
        f = ex.extract("SELECT * FROM t WHERE age BETWEEN 18 AND 65")
        assert f["has_between"] is True

    def test_has_null_check_is_null(self, ex):
        f = ex.extract("SELECT * FROM t WHERE email IS NULL")
        assert f["has_null_check"] is True

    def test_has_null_check_is_not_null(self, ex):
        f = ex.extract("SELECT * FROM t WHERE email IS NOT NULL")
        assert f["has_null_check"] is True

    def test_no_null_check(self, ex):
        assert ex.extract("SELECT * FROM t WHERE id = 1")["has_null_check"] is False

    def test_has_arithmetic_add(self, ex):
        f = ex.extract("SELECT price + 10 FROM products")
        assert f["has_arithmetic"] is True

    def test_has_arithmetic_mul(self, ex):
        f = ex.extract("SELECT price * 1.1 FROM products")
        assert f["has_arithmetic"] is True

    def test_no_arithmetic(self, ex):
        assert ex.extract("SELECT id FROM t")["has_arithmetic"] is False

    def test_has_string_func_upper(self, ex):
        f = ex.extract("SELECT UPPER(name) FROM t")
        assert f["has_string_func"] is True

    def test_has_string_func_lower(self, ex):
        f = ex.extract("SELECT LOWER(name) FROM t")
        assert f["has_string_func"] is True

    def test_has_string_func_trim(self, ex):
        f = ex.extract("SELECT TRIM(name) FROM t")
        assert f["has_string_func"] is True

    def test_has_string_func_concat(self, ex):
        f = ex.extract("SELECT CONCAT(first_name, ' ', last_name) FROM t")
        assert f["has_string_func"] is True

    def test_has_string_func_length(self, ex):
        f = ex.extract("SELECT LENGTH(name) FROM t")
        assert f["has_string_func"] is True

    def test_no_string_func(self, ex):
        assert ex.extract("SELECT id, age FROM t")["has_string_func"] is False

    def test_has_date_func_extract(self, ex):
        f = ex.extract("SELECT EXTRACT(YEAR FROM created_at) FROM t")
        assert f["has_date_func"] is True

    def test_has_date_func_current_date(self, ex):
        f = ex.extract("SELECT CURRENT_DATE FROM t")
        assert f["has_date_func"] is True

    def test_no_date_func(self, ex):
        assert ex.extract("SELECT id FROM t")["has_date_func"] is False

    def test_has_cast(self, ex):
        f = ex.extract("SELECT CAST(price AS INT) FROM products")
        assert f["has_cast"] is True

    def test_no_cast(self, ex):
        assert ex.extract("SELECT id FROM t")["has_cast"] is False


# ============================================================================
# 7. DML 타입
# ============================================================================

class TestQueryTypeFeatures:

    def test_select_type(self, ex):
        f = ex.extract("SELECT id FROM t")
        assert f["query_type"] == "SELECT"
        assert f["is_select"] is True
        assert f["is_dml"] is False

    def test_insert_type(self, ex):
        f = ex.extract("INSERT INTO t (id, name) VALUES (1, 'a')")
        assert f["query_type"] == "INSERT"
        assert f["is_select"] is False
        assert f["is_dml"] is True

    def test_update_type(self, ex):
        f = ex.extract("UPDATE t SET name = 'x' WHERE id = 1")
        assert f["query_type"] == "UPDATE"
        assert f["is_dml"] is True

    def test_delete_type(self, ex):
        f = ex.extract("DELETE FROM t WHERE id = 1")
        assert f["query_type"] == "DELETE"
        assert f["is_dml"] is True

    def test_create_type(self, ex):
        f = ex.extract("CREATE TABLE t (id INT)")
        assert f["query_type"] == "DDL"
        assert f["is_select"] is False
        assert f["is_dml"] is False

    def test_drop_type(self, ex):
        f = ex.extract("DROP TABLE t")
        assert f["query_type"] == "DDL"

    def test_alter_type(self, ex):
        f = ex.extract("ALTER TABLE t ADD COLUMN x INT")
        assert f["query_type"] == "DDL"

    def test_is_select_false_for_insert(self, ex):
        assert ex.extract("INSERT INTO t VALUES (1)")["is_select"] is False

    def test_is_dml_false_for_select(self, ex):
        assert ex.extract("SELECT 1")["is_dml"] is False


# ============================================================================
# 8. 복합 시나리오 (end-to-end)
# ============================================================================

class TestComplexScenarios:

    def test_analytics_query(self, ex):
        """GROUP BY + HAVING + ORDER BY + LIMIT + 집계함수"""
        sql = """
            SELECT department, COUNT(*) AS cnt, AVG(salary) AS avg_sal
            FROM employees
            WHERE status = 'active'
            GROUP BY department
            HAVING COUNT(*) > 5
            ORDER BY avg_sal DESC
            LIMIT 10
        """
        f = ex.extract(sql)
        assert f["has_where"] is True
        assert f["has_group_by"] is True
        assert f["has_having"] is True
        assert f["has_order_by"] is True
        assert f["has_limit"] is True
        assert f["has_aggregation"] is True
        assert f["has_count"] is True
        assert f["has_avg"] is True
        assert f["agg_func_count"] == 3   # COUNT(*), AVG(salary), COUNT(*) in HAVING
        assert f["num_group_by_cols"] == 1
        assert f["num_order_by_cols"] == 1

    def test_subquery_with_not_in_and_exists(self, ex):
        """서브쿼리 + NOT IN + EXISTS"""
        sql = """
            SELECT * FROM products
            WHERE category_id NOT IN (SELECT id FROM categories WHERE is_active = 0)
              AND EXISTS (SELECT 1 FROM inventory WHERE product_id = products.id)
        """
        f = ex.extract(sql)
        assert f["has_subquery"] is True
        assert f["has_not_in"] is True
        assert f["has_exists"] is True
        assert f["subquery_depth"] == 1

    def test_cte_with_window_and_case(self, ex):
        """CTE + WINDOW 함수 + CASE WHEN"""
        sql = """
            WITH ranked AS (
                SELECT employee_id, salary,
                       RANK() OVER (PARTITION BY dept ORDER BY salary DESC) AS rnk,
                       CASE WHEN salary > 100000 THEN 'high' ELSE 'normal' END AS tier
                FROM employees
            )
            SELECT * FROM ranked WHERE rnk <= 3
        """
        f = ex.extract(sql)
        assert f["has_cte"] is True
        assert f["has_window_func"] is True
        assert f["has_case_when"] is True
        assert f["num_ctes"] == 1

    def test_multi_join_query(self, ex):
        """INNER + LEFT JOIN 복합"""
        sql = """
            SELECT o.id, c.name, p.title
            FROM orders o
            INNER JOIN customers c ON o.customer_id = c.id
            LEFT  JOIN products  p ON o.product_id  = p.id
            WHERE o.amount > 0
        """
        f = ex.extract(sql)
        assert f["has_join"] is True
        assert f["join_count"] == 2
        assert f["has_inner_join"] is True
        assert f["has_left_join"] is True
        assert f["has_right_join"] is False
        assert f["num_tables"] == 3

    def test_nested_subquery_depth(self, ex):
        """서브쿼리 2단 중첩 깊이 검증"""
        sql = """
            SELECT * FROM t1
            WHERE id IN (
                SELECT id FROM t2
                WHERE val > (SELECT MAX(val) FROM t3)
            )
        """
        f = ex.extract(sql)
        assert f["subquery_depth"] == 2
        assert f["num_subqueries"] == 2
        assert f["has_max"] is True

    def test_operators_combined(self, ex):
        """CAST + 산술 + 문자열 + 날짜 + BETWEEN + LIKE + IS NOT NULL"""
        sql = """
            SELECT
                CAST(price * 1.1 AS DECIMAL(10,2)) AS price_with_tax,
                UPPER(TRIM(name))                  AS clean_name,
                EXTRACT(YEAR FROM created_at)      AS yr
            FROM products
            WHERE price BETWEEN 10 AND 500
              AND name LIKE '%widget%'
              AND created_at IS NOT NULL
        """
        f = ex.extract(sql)
        assert f["has_cast"] is True
        assert f["has_arithmetic"] is True
        assert f["has_string_func"] is True
        assert f["has_date_func"] is True
        assert f["has_between"] is True
        assert f["has_like"] is True
        assert f["has_null_check"] is True
        assert f["num_conditions"] == 3

    def test_self_join(self, ex):
        """Self-join 감지"""
        sql = "SELECT a.id, b.id AS parent FROM categories a JOIN categories b ON a.parent_id = b.id"
        f = ex.extract(sql)
        assert f["has_self_join"] is True
        assert f["has_join"] is True

    def test_union_all(self, ex):
        """UNION ALL"""
        sql = "SELECT id, name FROM customers UNION ALL SELECT id, name FROM suppliers"
        f = ex.extract(sql)
        assert f["has_union"] is True
        assert f["num_tables"] == 2

    def test_multiple_ctes(self, ex):
        """다중 CTE"""
        sql = """
            WITH a AS (SELECT 1 AS n),
                 b AS (SELECT 2 AS n)
            SELECT a.n + b.n FROM a, b
        """
        f = ex.extract(sql)
        assert f["has_cte"] is True
        assert f["num_ctes"] == 2


# ============================================================================
# 9. 경계값 / 엣지 케이스
# ============================================================================

class TestEdgeCases:

    def test_select_star(self, ex):
        f = ex.extract("SELECT * FROM t")
        assert f["has_select"] is True
        assert f["num_columns"] == 1  # Star 는 1개 expression

    def test_select_1(self, ex):
        f = ex.extract("SELECT 1")
        assert f["has_select"] is True
        assert f["num_tables"] == 0

    def test_no_where_predicates_zero(self, ex):
        f = ex.extract("SELECT id FROM t")
        assert f["num_conditions"] == 0
        assert f["num_predicates"] == 0

    def test_distinct_without_where(self, ex):
        f = ex.extract("SELECT DISTINCT name FROM t")
        assert f["has_distinct"] is True
        assert f["has_where"] is False

    def test_subquery_in_from(self, ex):
        f = ex.extract("SELECT sub.id FROM (SELECT id FROM t WHERE x > 1) sub")
        assert f["has_subquery"] is True
        assert f["subquery_depth"] == 1

    def test_in_subquery_not_counted_as_not_in(self, ex):
        f = ex.extract("SELECT * FROM t WHERE id IN (SELECT id FROM t2)")
        assert f["has_in"] is True
        assert f["has_not_in"] is False

    def test_multiple_string_funcs(self, ex):
        f = ex.extract("SELECT UPPER(first_name), LOWER(last_name), TRIM(email) FROM users")
        assert f["has_string_func"] is True

    def test_arithmetic_in_where(self, ex):
        f = ex.extract("SELECT * FROM t WHERE price * 0.9 > 100")
        assert f["has_arithmetic"] is True

    def test_cross_join_no_on(self, ex):
        f = ex.extract("SELECT * FROM a CROSS JOIN b")
        assert f["has_cross_join"] is True
        assert f["has_join"] is True
        assert f["join_count"] == 1

    def test_having_without_group_by_edge(self, ex):
        # HAVING 은 있고 GROUP BY 는 없는 비정상 케이스 (파싱은 되어야 함)
        f = ex.extract("SELECT COUNT(*) FROM t HAVING COUNT(*) > 0")
        assert f["has_having"] is True

    def test_dialect_mysql(self, ex):
        extractor_mysql = SQLStructuralFeatureExtractor(dialect="mysql")
        f = extractor_mysql.extract("SELECT id FROM t LIMIT 10")
        assert f["has_limit"] is True
        assert f["query_type"] == "SELECT"
