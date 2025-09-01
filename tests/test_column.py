import unittest
from athena_bridge import functions
from athena_bridge import window

class DummyColumn:
    def __init__(self, name):
        self.name = name

    def to_sql(self):
        return self.name

    def __str__(self):
        return self.name


class TestColumnClass(unittest.TestCase):

    def test_alias_and_to_sql(self):
        col = functions.Column("columna_base")
        col.alias("alias_col")
        self.assertEqual(col.alias_name, "alias_col")
        self.assertEqual(col.to_sql(), "columna_base AS alias_col")

    def test_to_sql_without_alias(self):
        col = functions.Column("otra_columna")
        self.assertIsNone(col.alias_name)
        self.assertEqual(col.to_sql(), "otra_columna")

    def test_asc(self):
        col = functions.Column("edad")
        asc_col = col.asc()
        self.assertEqual(asc_col.to_sql(), "edad ASC")

    def test_desc(self):
        col = functions.Column("edad")
        desc_col = col.desc()
        self.assertEqual(desc_col.to_sql(), "edad DESC")

    # Operadores aritméticos
    def test_add_operator(self):
        c1 = functions.Column("a")
        c2 = functions.Column("b")
        result = c1 + c2
        self.assertEqual(result.to_sql(), "(a + b)")

    def test_sub_operator(self):
        c1 = functions.Column("a")
        c2 = functions.Column("b")
        result = c1 - c2
        self.assertEqual(result.to_sql(), "(a - b)")

    def test_mul_operator(self):
        c1 = functions.Column("a")
        c2 = functions.Column("b")
        result = c1 * c2
        self.assertEqual(result.to_sql(), "(a * b)")

    def test_div_operator(self):
        c1 = functions.Column("a")
        c2 = functions.Column("b")
        result = c1 / c2
        self.assertEqual(result.to_sql(), "(a / b)")

    # Comparaciones
    def test_eq_operator(self):
        c1 = functions.Column("a")
        c2 = functions.Column("b")
        result = c1 == c2
        self.assertEqual(result.to_sql(), "(a = b)")

    def test_ne_operator(self):
        c1 = functions.Column("a")
        c2 = functions.Column("b")
        result = c1 != c2
        self.assertEqual(result.to_sql(), "(a != b)")

    def test_gt_operator(self):
        c1 = functions.Column("a")
        c2 = functions.Column("b")
        result = c1 > c2
        self.assertEqual(result.to_sql(), "(a > b)")

    def test_lt_operator(self):
        c1 = functions.Column("a")
        c2 = functions.Column("b")
        result = c1 < c2
        self.assertEqual(result.to_sql(), "(a < b)")

    def test_ge_operator(self):
        c1 = functions.Column("a")
        c2 = functions.Column("b")
        result = c1 >= c2
        self.assertEqual(result.to_sql(), "(a >= b)")

    def test_le_operator(self):
        c1 = functions.Column("a")
        c2 = functions.Column("b")
        result = c1 <= c2
        self.assertEqual(result.to_sql(), "(a <= b)")

    # Operadores lógicos
    def test_and_operator(self):
        c1 = functions.Column("a = 1")
        c2 = functions.Column("b = 2")
        result = c1 & c2
        self.assertEqual(result.to_sql(), "(a = 1 AND b = 2)")

    def test_or_operator(self):
        c1 = functions.Column("a = 1")
        c2 = functions.Column("b = 2")
        result = c1 | c2
        self.assertEqual(result.to_sql(), "(a = 1 OR b = 2)")

    def test_not_operator(self):
        c = functions.Column("a = 1")
        result = ~c
        self.assertEqual(result.to_sql(), "NOT (a = 1)")
        self.assertEqual(result._data_type, "boolean")
        
    def test_cast_known_type(self):
        col = functions.Column("col1")
        result = col.cast("string")
        self.assertEqual(result.to_sql(), "CAST(col1 AS VARCHAR)")
        self.assertEqual(result._data_type, "string")

    def test_cast_unknown_type(self):
        col = functions.Column("col1")
        result = col.cast("CUSTOMTYPE")
        self.assertEqual(result.to_sql(), "CAST(col1 AS CUSTOMTYPE)")
        self.assertEqual(result._data_type, "customtype")

    '''
    def test_cast_invalid_type(self):
        col = functions.Column("col1")
        class InvalidType: pass
        with self.assertRaises(TypeError):
            col.cast(InvalidType())
    '''
    
    def test_astype_alias(self):
        col = functions.Column("edad")
        result = col.astype("int")
        self.assertEqual(result.to_sql(), "CAST(edad AS INTEGER)")
        self.assertEqual(result._data_type, "int")

    def test_isNull(self):
        col = functions.Column("col1")
        result = col.isNull()
        self.assertEqual(result.to_sql(), "col1 IS NULL")
        self.assertEqual(result._data_type, "boolean")

    def test_isNotNull(self):
        col = functions.Column("col1")
        result = col.isNotNull()
        self.assertEqual(result.to_sql(), "col1 IS NOT NULL")
        self.assertEqual(result._data_type, "boolean")

    def test_isin_with_multiple_values(self):
        col = functions.Column("nombre")
        result = col.isin("Ana", "Luis", "Sofía")
        self.assertEqual(result.to_sql(), "nombre IN ('Ana', 'Luis', 'Sofía')")
        self.assertEqual(result._data_type, "boolean")

    def test_isin_with_list(self):
        col = functions.Column("id")
        result = col.isin([1, 2, 3])
        self.assertEqual(result.to_sql(), "id IN (1, 2, 3)")

    def test_isin_empty(self):
        col = functions.Column("estado")
        with self.assertRaises(ValueError):
            col.isin()

    def test_startswith_valid(self):
        col = functions.Column("nombre")
        result = col.startswith("Lu")
        self.assertEqual(result.to_sql(), "nombre LIKE 'Lu%'")

    def test_startswith_invalid(self):
        col = functions.Column("nombre")
        with self.assertRaises(TypeError):
            col.startswith(123)

    def test_endswith_valid(self):
        col = functions.Column("apellido")
        result = col.endswith("ez")
        self.assertEqual(result.to_sql(), "apellido LIKE '%ez'")

    def test_endswith_invalid(self):
        col = functions.Column("apellido")
        with self.assertRaises(TypeError):
            col.endswith(None)

    def test_contains_valid(self):
        col = functions.Column("texto")
        result = col.contains("abc")
        self.assertEqual(result.to_sql(), "texto LIKE '%abc%'")

    def test_contains_invalid(self):
        col = functions.Column("texto")
        with self.assertRaises(TypeError):
            col.contains(123)
            
    def test_substr_valid(self):
        col = functions.Column("descripcion")
        result = col.substr(2, 5)
        self.assertEqual(result.to_sql(), "SUBSTRING(descripcion, 2, 5)")
        self.assertEqual(result._data_type, "string")

    def test_substr_invalid_args(self):
        col = functions.Column("descripcion")
        with self.assertRaises(TypeError):
            col.substr("inicio", 5)
        with self.assertRaises(TypeError):
            col.substr(2, "longitud")

    def test_like_valid(self):
        col = functions.Column("mensaje")
        result = col.like("%error%")
        self.assertEqual(result.to_sql(), "mensaje LIKE '%error%'")
        self.assertEqual(result._data_type, "boolean")

    def test_like_invalid(self):
        col = functions.Column("mensaje")
        with self.assertRaises(TypeError):
            col.like(123)

    def test_between_with_ints(self):
        col = functions.Column("edad")
        result = col.between(18, 30)
        self.assertEqual(result.to_sql(), "edad BETWEEN 18 AND 30")
        self.assertEqual(result._data_type, "boolean")

    def test_between_with_strings(self):
        col = functions.Column("nombre")
        result = col.between("Ana", "Luis")
        self.assertEqual(result.to_sql(), "nombre BETWEEN 'Ana' AND 'Luis'")

    def test_between_with_dates(self):
        col = functions.Column("fecha")
        result = col.between("2023-01-01", "2023-12-31")
        self.assertEqual(result.to_sql(), "fecha BETWEEN DATE '2023-01-01' AND DATE '2023-12-31'")
    
    def test_over_with_partition_by_only(self):
        col = functions.Column("columna")
        w = window.Window(partition_by=["user_id"])
        result = col.over(w)
        self.assertIn("PARTITION BY user_id", result.to_sql())
        self.assertTrue(result.to_sql().startswith("columna OVER ("))
        self.assertEqual(result._data_type, "string")

    def test_over_with_order_by_only(self):
        col = functions.Column("columna")
        order_col = DummyColumn("fecha")
        w = window.Window(order_by=[order_col])
        result = col.over(w)
        self.assertIn("ORDER BY fecha", result.to_sql())
        self.assertTrue(result.to_sql().startswith("columna OVER ("))

    def test_over_with_partition_and_order(self):
        col = functions.Column("columna")
        order_col = DummyColumn("fecha")
        w = window.Window(partition_by=["user_id"], order_by=[order_col])
        result = col.over(w)
        self.assertIn("PARTITION BY user_id", result.to_sql())
        self.assertIn("ORDER BY fecha", result.to_sql())
        self.assertTrue(result.to_sql().startswith("columna OVER ("))

    def test_over_invalid_argument(self):
        col = functions.Column("columna")
        with self.assertRaises(TypeError):
            col.over("no_es_una_ventana")