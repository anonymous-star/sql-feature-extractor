"""
SQL Structural Feature Extractor
=================================
sqlglot 기반으로 SQL 쿼리에서 ~50개의 구조적 특성(structural features)을 추출합니다.

Requirements:
    pip install sqlglot

Supported dialects:
    None (generic), 'mysql', 'postgres', 'bigquery', 'spark', 'snowflake', etc.
"""

import sqlglot
from sqlglot import exp
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Main Extractor
# ---------------------------------------------------------------------------

class SQLStructuralFeatureExtractor:
    """
    SQL 쿼리의 구조적 특성을 추출하는 클래스.

    Usage:
        extractor = SQLStructuralFeatureExtractor()
        features = extractor.extract(sql)

        # 복수 쿼리 배치 처리
        df = extractor.extract_batch(sql_list)
    """

    def __init__(self, dialect: Optional[str] = None):
        """
        Args:
            dialect: SQL 방언 (예: 'mysql', 'postgres', 'bigquery', 'spark').
                     None 이면 일반(generic) 파서를 사용.
        """
        self.dialect = dialect

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, sql: str) -> Dict[str, Any]:
        """SQL 문자열에서 모든 구조적 특성을 추출하여 dict 로 반환."""
        stmt = self._parse(sql)
        if stmt is None:
            return self._null_features()

        features: Dict[str, Any] = {}
        features.update(self._clause_features(stmt))
        features.update(self._join_features(stmt))
        features.update(self._aggregation_features(stmt))
        features.update(self._count_features(stmt))
        features.update(self._operator_features(stmt))
        features.update(self._query_type_features(stmt, sql))
        return features

    def extract_batch(self, sql_list: List[str]):
        """
        여러 SQL 쿼리를 일괄 처리하여 pandas DataFrame 으로 반환.

        Returns:
            pandas.DataFrame: 각 행이 한 쿼리, 각 열이 feature.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError("extract_batch() requires pandas: pip install pandas") from e

        rows = [self.extract(sql) for sql in sql_list]
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Parsing helper
    # ------------------------------------------------------------------

    def _parse(self, sql: str) -> Optional[exp.Expression]:
        try:
            statements = sqlglot.parse(sql.strip(), dialect=self.dialect)
            return statements[0] if statements else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 1. Clause 존재 여부 (14개)
    # ------------------------------------------------------------------

    def _clause_features(self, stmt: exp.Expression) -> Dict[str, Any]:
        return {
            "has_select":      bool(stmt.find(exp.Select)),
            "has_where":       bool(stmt.find(exp.Where)),
            "has_group_by":    bool(stmt.find(exp.Group)),
            "has_having":      bool(stmt.find(exp.Having)),
            "has_order_by":    bool(stmt.find(exp.Order)),
            "has_limit":       bool(stmt.find(exp.Limit)),
            "has_distinct":    bool(stmt.find(exp.Distinct)),
            "has_subquery":    bool(stmt.find(exp.Subquery)),
            "has_union":       bool(stmt.find(exp.Union)),
            "has_intersect":   bool(stmt.find(exp.Intersect)),
            "has_except":      bool(stmt.find(exp.Except)),
            "has_cte":         bool(stmt.find(exp.With)),
            "has_case_when":   bool(stmt.find(exp.Case)),
            "has_window_func": bool(stmt.find(exp.Window)),
        }

    # ------------------------------------------------------------------
    # 2. JOIN (8개)
    # ------------------------------------------------------------------

    def _join_features(self, stmt: exp.Expression) -> Dict[str, Any]:
        joins = list(stmt.find_all(exp.Join))

        def kind(j: exp.Join) -> str:
            return str(j.args.get("kind") or "").upper()

        def side(j: exp.Join) -> str:
            return str(j.args.get("side") or "").upper()

        # sqlglot 분리 표현:
        #   INNER JOIN → kind='INNER' or both None
        #   LEFT JOIN  → side='LEFT'
        #   RIGHT JOIN → side='RIGHT'
        #   FULL OUTER → side='FULL', kind='OUTER'
        #   CROSS JOIN → kind='CROSS'
        has_inner = any(kind(j) in ("", "INNER") and side(j) == "" for j in joins)
        has_left  = any(side(j) == "LEFT"                           for j in joins)
        has_right = any(side(j) == "RIGHT"                          for j in joins)
        has_full  = any(side(j) == "FULL"                           for j in joins)
        has_cross = any(kind(j) == "CROSS"                          for j in joins)

        # Self-join: 동일한 테이블 이름이 두 번 이상 등장
        table_names = [t.name.lower() for t in stmt.find_all(exp.Table)]
        has_self_join = len(table_names) != len(set(table_names))

        return {
            "has_join":       len(joins) > 0,
            "join_count":     len(joins),
            "has_inner_join": has_inner and len(joins) > 0,
            "has_left_join":  has_left,
            "has_right_join": has_right,
            "has_full_join":  has_full,
            "has_cross_join": has_cross,
            "has_self_join":  has_self_join,
        }

    # ------------------------------------------------------------------
    # 3. Aggregation (7개)
    # ------------------------------------------------------------------

    def _aggregation_features(self, stmt: exp.Expression) -> Dict[str, Any]:
        agg_nodes = list(stmt.find_all(exp.AggFunc))
        return {
            "has_aggregation": len(agg_nodes) > 0,
            "agg_func_count":  len(agg_nodes),
            "has_count":       bool(stmt.find(exp.Count)),
            "has_sum":         bool(stmt.find(exp.Sum)),
            "has_avg":         bool(stmt.find(exp.Avg)),
            "has_min":         bool(stmt.find(exp.Min)),
            "has_max":         bool(stmt.find(exp.Max)),
        }

    # ------------------------------------------------------------------
    # 4. 수치/카운트 (9개)
    # ------------------------------------------------------------------

    def _count_features(self, stmt: exp.Expression) -> Dict[str, Any]:
        # 테이블 수 (유니크 이름 기준)
        all_tables  = list(stmt.find_all(exp.Table))
        table_names = [t.name.lower() for t in all_tables]
        num_tables  = len(set(table_names))

        # SELECT 컬럼 수
        select_node = stmt.find(exp.Select)
        num_columns = len(select_node.expressions) if select_node else 0

        # WHERE 조건/술어 수
        where_node     = stmt.find(exp.Where)
        num_predicates = self._count_predicates(where_node) if where_node else 0

        # 서브쿼리 수 & 최대 중첩 깊이
        subqueries     = list(stmt.find_all(exp.Subquery))
        num_subqueries = len(subqueries)
        subquery_depth = self._get_subquery_depth(stmt)

        # CTE 수
        num_ctes = len(list(stmt.find_all(exp.CTE)))

        # GROUP BY 컬럼 수
        group_node     = stmt.find(exp.Group)
        num_group_cols = len(group_node.expressions) if group_node else 0

        # ORDER BY 컬럼 수
        order_node     = stmt.find(exp.Order)
        num_order_cols = len(order_node.expressions) if order_node else 0

        return {
            "num_tables":        num_tables,
            "num_columns":       num_columns,
            "num_conditions":    num_predicates,   # WHERE 조건 수
            "num_subqueries":    num_subqueries,
            "num_ctes":          num_ctes,
            "subquery_depth":    subquery_depth,
            "num_predicates":    num_predicates,   # 조건절 술어 수 (= num_conditions)
            "num_group_by_cols": num_group_cols,
            "num_order_by_cols": num_order_cols,
        }

    def _count_predicates(self, node: exp.Expression) -> int:
        """WHERE 절 안의 비교 연산자(술어) 개수를 반환."""
        pred_types = (
            exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
            exp.In, exp.Like, exp.ILike, exp.Between, exp.Is,
        )
        return sum(len(list(node.find_all(t))) for t in pred_types)

    def _get_subquery_depth(self, root: exp.Expression) -> int:
        """서브쿼리의 최대 중첩 깊이를 반환 (최상위 = 0)."""
        max_depth = 0

        def _dfs(node: exp.Expression, depth: int) -> None:
            nonlocal max_depth
            for child in node.args.values():
                items: List[exp.Expression] = (
                    child if isinstance(child, list) else
                    [child] if isinstance(child, exp.Expression) else
                    []
                )
                for item in items:
                    if not isinstance(item, exp.Expression):
                        continue
                    new_depth = depth + 1 if isinstance(item, exp.Subquery) else depth
                    if new_depth > max_depth:
                        max_depth = new_depth
                    _dfs(item, new_depth)

        _dfs(root, 0)
        return max_depth

    # ------------------------------------------------------------------
    # 5. 연산자/표현식 (10개)
    # ------------------------------------------------------------------

    def _operator_features(self, stmt: exp.Expression) -> Dict[str, Any]:
        # NOT IN: In 노드의 부모가 Not 인 경우
        has_not_in = any(
            isinstance(node.parent, exp.Not)
            for node in stmt.find_all(exp.In)
        )

        # 문자열 함수
        _STR_FUNCS = (
            exp.Concat, exp.Upper, exp.Lower, exp.Trim,
            exp.Substring, exp.Length, exp.Replace,
            exp.Left, exp.Right,
        )
        has_string_func = any(stmt.find(t) is not None for t in _STR_FUNCS)

        # 날짜 함수
        _DATE_FUNCS = (
            exp.DateAdd, exp.DateDiff, exp.DateTrunc,
            exp.TsOrDsToDate, exp.Extract,
            exp.CurrentDate, exp.CurrentTimestamp, exp.CurrentTime,
            exp.DateStrToDate,
        )
        has_date_func = any(stmt.find(t) is not None for t in _DATE_FUNCS)

        # 산술 연산
        _ARITH_OPS = (exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod)
        has_arithmetic = any(stmt.find(t) is not None for t in _ARITH_OPS)

        return {
            "has_in":          bool(stmt.find(exp.In)),
            "has_not_in":      has_not_in,
            "has_exists":      bool(stmt.find(exp.Exists)),
            "has_like":        bool(stmt.find(exp.Like)) or bool(stmt.find(exp.ILike)),
            "has_between":     bool(stmt.find(exp.Between)),
            "has_null_check":  bool(stmt.find(exp.Is)),   # IS NULL / IS NOT NULL
            "has_arithmetic":  has_arithmetic,
            "has_string_func": has_string_func,
            "has_date_func":   has_date_func,
            "has_cast":        bool(stmt.find(exp.Cast)),
        }

    # ------------------------------------------------------------------
    # 6. DML 타입 (3개)
    # ------------------------------------------------------------------

    def _query_type_features(self, stmt: exp.Expression, sql: str) -> Dict[str, Any]:
        _TYPE_MAP = {
            exp.Select: "SELECT",
            exp.Insert: "INSERT",
            exp.Update: "UPDATE",
            exp.Delete: "DELETE",
            exp.Create: "DDL",
            exp.Drop:   "DDL",
            exp.Alter:  "DDL",
        }
        qtype = next(
            (v for cls, v in _TYPE_MAP.items() if isinstance(stmt, cls)),
            None,
        )
        if qtype is None:
            first = sql.strip().split()[0].upper() if sql.strip() else ""
            qtype = first if first in {"SELECT", "INSERT", "UPDATE", "DELETE"} else "OTHER"

        return {
            "query_type": qtype,
            "is_select":  qtype == "SELECT",
            "is_dml":     qtype in {"INSERT", "UPDATE", "DELETE"},
        }

    # ------------------------------------------------------------------
    # Null features (파싱 실패 시 반환)
    # ------------------------------------------------------------------

    @staticmethod
    def _null_features() -> Dict[str, Any]:
        return {
            # Clause
            "has_select": False, "has_where": False, "has_group_by": False,
            "has_having": False, "has_order_by": False, "has_limit": False,
            "has_distinct": False, "has_subquery": False, "has_union": False,
            "has_intersect": False, "has_except": False, "has_cte": False,
            "has_case_when": False, "has_window_func": False,
            # JOIN
            "has_join": False, "join_count": 0,
            "has_inner_join": False, "has_left_join": False,
            "has_right_join": False, "has_full_join": False,
            "has_cross_join": False, "has_self_join": False,
            # Aggregation
            "has_aggregation": False, "agg_func_count": 0,
            "has_count": False, "has_sum": False, "has_avg": False,
            "has_min": False, "has_max": False,
            # Count
            "num_tables": 0, "num_columns": 0, "num_conditions": 0,
            "num_subqueries": 0, "num_ctes": 0, "subquery_depth": 0,
            "num_predicates": 0, "num_group_by_cols": 0, "num_order_by_cols": 0,
            # Operators
            "has_in": False, "has_not_in": False, "has_exists": False,
            "has_like": False, "has_between": False, "has_null_check": False,
            "has_arithmetic": False, "has_string_func": False,
            "has_date_func": False, "has_cast": False,
            # Type
            "query_type": "UNKNOWN", "is_select": False, "is_dml": False,
        }


# ---------------------------------------------------------------------------
# CLI / Demo
# ---------------------------------------------------------------------------

DEMO_QUERIES = [
    # 1. 단순 SELECT
    "SELECT id, name FROM users WHERE age > 30",

    # 2. GROUP BY + HAVING + ORDER BY + LIMIT
    """
    SELECT department, COUNT(*) AS cnt, AVG(salary) AS avg_sal
    FROM employees
    WHERE status = 'active'
    GROUP BY department
    HAVING COUNT(*) > 5
    ORDER BY avg_sal DESC
    LIMIT 10
    """,

    # 3. 다중 JOIN
    """
    SELECT o.id, c.name, p.title
    FROM orders o
    INNER JOIN customers c ON o.customer_id = c.id
    LEFT  JOIN products  p ON o.product_id  = p.id
    WHERE o.created_at >= '2024-01-01'
    """,

    # 4. 서브쿼리 + EXISTS + NOT IN
    """
    SELECT *
    FROM products
    WHERE category_id NOT IN (SELECT id FROM categories WHERE is_active = 0)
      AND EXISTS (SELECT 1 FROM inventory WHERE product_id = products.id AND qty > 0)
    """,

    # 5. CTE + WINDOW 함수 + CASE WHEN
    """
    WITH ranked AS (
        SELECT
            employee_id,
            salary,
            RANK() OVER (PARTITION BY department ORDER BY salary DESC) AS rnk,
            CASE WHEN salary > 100000 THEN 'high' ELSE 'normal' END AS tier
        FROM employees
    )
    SELECT * FROM ranked WHERE rnk <= 3
    """,

    # 6. UNION
    """
    SELECT id, name FROM customers
    UNION ALL
    SELECT id, name FROM suppliers
    """,

    # 7. 산술/문자열/날짜 함수 + CAST + BETWEEN + LIKE
    """
    SELECT
        CAST(price * 1.1 AS DECIMAL(10,2)) AS price_with_tax,
        UPPER(TRIM(name))                  AS clean_name,
        EXTRACT(YEAR FROM created_at)      AS yr
    FROM products
    WHERE price BETWEEN 10 AND 500
      AND name LIKE '%widget%'
      AND created_at IS NOT NULL
    """,

    # 8. Self-join
    """
    SELECT a.id, b.id AS parent_id
    FROM categories a
    JOIN categories b ON a.parent_id = b.id
    """,

    # 9. 중첩 서브쿼리 (깊이 2)
    """
    SELECT * FROM t1
    WHERE id IN (
        SELECT id FROM t2
        WHERE val > (SELECT MAX(val) FROM t3)
    )
    """,

    # 10. INSERT DML
    "INSERT INTO logs (user_id, action) VALUES (1, 'login')",
]


def main():
    extractor = SQLStructuralFeatureExtractor()

    print("=" * 70)
    print("SQL Structural Feature Extractor — Demo")
    print("=" * 70)

    for i, sql in enumerate(DEMO_QUERIES, 1):
        features = extractor.extract(sql)
        print(f"\n[Query {i}]")
        print(sql.strip()[:120])
        print("-" * 50)
        # 범주별 출력
        groups = {
            "Clause":      [k for k in features if k.startswith("has_") and k not in
                            ("has_join","has_inner_join","has_left_join","has_right_join",
                             "has_full_join","has_cross_join","has_self_join",
                             "has_aggregation","has_count","has_sum","has_avg","has_min","has_max",
                             "has_in","has_not_in","has_exists","has_like","has_between",
                             "has_null_check","has_arithmetic","has_string_func","has_date_func","has_cast",
                             "has_select","has_where","has_group_by","has_having","has_order_by",
                             "has_limit","has_distinct","has_subquery","has_union","has_intersect",
                             "has_except","has_cte","has_case_when","has_window_func",
                             "is_select","is_dml")],
        }
        # 간단 출력: True/non-zero 인 항목만
        active = {k: v for k, v in features.items() if v not in (False, 0, "OTHER", "UNKNOWN")}
        for k, v in active.items():
            print(f"  {k:<22} = {v}")

    print("\n" + "=" * 70)
    print("Feature 전체 목록 (총 %d개):" % len(extractor.extract("SELECT 1")))
    print("=" * 70)
    for k in extractor.extract("SELECT 1").keys():
        print(f"  {k}")


if __name__ == "__main__":
    main()
