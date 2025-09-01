import unittest
from athena_bridge import functions

class DummyDataFrame:
    pass

class DummyCondition:
    def to_sql(self):
        return "condición_dummy"

class DummyWhenResult:
    def __init__(self, sql):
        self.sql = sql

class FunctionsTest(unittest.TestCase):
    
    def test_broadcast_warns_and_returns_df(self):
        df = DummyDataFrame()
        with self.assertWarns(UserWarning) as cm:
            result = functions.broadcast(df)
        self.assertEqual(result, df)
        self.assertIn("no tiene efecto en Athena", str(cm.warning))

    def test_when_returns_when_instance(self):
        condition = DummyCondition()
        value = functions.lit(1)
        result = functions.when(condition, value)
        self.assertIsInstance(result, functions._When)

    def test_col_returns_column(self):
        c = functions.col("mi_columna")
        self.assertIsInstance(c, functions.Column)
        self.assertEqual(c.to_sql(), "mi_columna")
        self.assertEqual(c.referenced_columns, ["mi_columna"])

    def test_column_alias_is_col(self):
        c = functions.column("otra_columna")
        self.assertIsInstance(c, functions.Column)
        self.assertEqual(c.to_sql(), "otra_columna")
        self.assertEqual(c.referenced_columns, ["otra_columna"])

    def test_lit_int(self):
        c = functions.lit(10)
        self.assertEqual(c.to_sql(), "10")
        self.assertEqual(c._data_type, "int")

    def test_lit_float(self):
        c = functions.lit(3.14)
        self.assertEqual(c.to_sql(), "3.14")
        self.assertEqual(c._data_type, "double")

    def test_lit_string(self):
        c = functions.lit("hola")
        self.assertEqual(c.to_sql(), "'hola'")
        self.assertEqual(c._data_type, "string")

    def test_lit_bool(self):
        c = functions.lit(True)
        self.assertEqual(c.to_sql(), "True")
        self.assertEqual(c._data_type, "boolean")

    def test_lit_none(self):
        c = functions.lit(None)
        self.assertEqual(c.to_sql(), "NULL")
        self.assertEqual(c._data_type, "null")
        
    def test_isnull_with_column(self):
        col = functions.Column("columna", data_type="string")
        result = functions.isnull(col)
        self.assertEqual(result.to_sql(), "columna IS NULL")
        self.assertEqual(result._data_type, "boolean")

    def test_isnull_with_invalid_type(self):
        with self.assertRaises(TypeError):
            functions.isnull(123)

    def test_contains_success(self):
        col = functions.Column("nombre")
        col.contains = lambda substr: functions.Column(f"{col.to_sql()} LIKE '%{substr}%'")
        result = functions.contains(col, "ana")
        self.assertEqual(result.to_sql(), "nombre LIKE '%ana%'")

    def test_contains_invalid_args(self):
        with self.assertRaises(TypeError):
            functions.contains(123, "ana")
        with self.assertRaises(TypeError):
            functions.contains("nombre", 42)

    def test_endswith_success(self):
        col = functions.Column("nombre")
        col.endswith = lambda suffix: functions.Column(f"{col.to_sql()} LIKE '%{suffix}'")
        result = functions.endswith(col, "ito")
        self.assertEqual(result.to_sql(), "nombre LIKE '%ito'")

    def test_endswith_invalid_args(self):
        with self.assertRaises(TypeError):
            functions.endswith(123, "ito")
        with self.assertRaises(TypeError):
            functions.endswith("nombre", 123)

    def test_left_function(self):
        col = functions.Column("texto")
        result = functions.left(col, 5)
        self.assertEqual(result.to_sql(), "SUBSTRING(texto, 1, 5)")
        self.assertEqual(result._data_type, "string")

    def test_left_invalid_args(self):
        with self.assertRaises(TypeError):
            functions.left(123, 3)
        with self.assertRaises(TypeError):
            functions.left("texto", "tres")

    def test_length_function(self):
        col = functions.Column("cadena")
        result = functions.length(col)
        self.assertEqual(result.to_sql(), "LENGTH(cadena)")
        self.assertEqual(result._data_type, "int")

    def test_length_invalid(self):
        with self.assertRaises(TypeError):
            functions.length(99)

    def test_like_function(self):
        col = functions.Column("campo")
        col.like = lambda val: functions.Column(f"{col.to_sql()} LIKE '{val}'")
        result = functions.like(col, "%fin")
        self.assertEqual(result.to_sql(), "campo LIKE '%fin'")

    def test_like_invalid_args(self):
        with self.assertRaises(TypeError):
            functions.like(123, "%fin")
        with self.assertRaises(TypeError):
            functions.like("campo", 999)

    def test_ltrim_function(self):
        col = functions.Column("mi_columna")
        result = functions.ltrim(col)
        self.assertEqual(result.to_sql(), "LTRIM(mi_columna)")
        self.assertEqual(result._data_type, "string")

    def test_ltrim_invalid(self):
        with self.assertRaises(TypeError):
            functions.ltrim(123)

    def test_upper_function(self):
        result = functions.upper("columna")
        self.assertEqual(result.to_sql(), "UPPER(columna)")
        self.assertEqual(result._data_type, "string")

    def test_lower_function(self):
        result = functions.lower("columna")
        self.assertEqual(result.to_sql(), "LOWER(columna)")
        self.assertEqual(result._data_type, "string")

    def test_lpad_function(self):
        result = functions.lpad("nombre", 10, "-")
        self.assertEqual(result.to_sql(), "LPAD(nombre, 10, '-')")
        self.assertEqual(result._data_type, "string")
        
        
    def test_right_function(self):
        col = functions.Column("texto")
        result = functions.right(col, 3)
        expected_sql = "SUBSTRING(texto, LENGTH(texto) - 2, 3)"
        self.assertEqual(result.to_sql(), expected_sql)
        self.assertEqual(result._data_type, "string")

    def test_right_invalid_args(self):
        with self.assertRaises(TypeError):
            functions.right(123, 3)
        with self.assertRaises(TypeError):
            functions.right("col", "tres")

    def test_rpad_function(self):
        result = functions.rpad("nombre", 10, "*")
        self.assertEqual(result.to_sql(), "RPAD(nombre, 10, '*')")
        self.assertEqual(result._data_type, "string")

    def test_rtrim_function(self):
        col = functions.Column("campo")
        result = functions.rtrim(col)
        self.assertEqual(result.to_sql(), "RTRIM(campo)")
        self.assertEqual(result._data_type, "string")

    def test_rtrim_invalid(self):
        with self.assertRaises(TypeError):
            functions.rtrim(123)

    def test_startswith_function(self):
        col = functions.Column("palabra")
        col.startswith = lambda suf: functions.Column(f"{col.to_sql()} LIKE '{suf}%'")
        result = functions.startswith(col, "pre")
        self.assertEqual(result.to_sql(), "palabra LIKE 'pre%'")

    def test_startswith_invalid(self):
        with self.assertRaises(TypeError):
            functions.startswith(123, "pre")
        with self.assertRaises(TypeError):
            functions.startswith("palabra", 999)

    def test_split_function(self):
        col = functions.Column("frase")
        result = functions.split(col, " ")
        self.assertEqual(result.to_sql(), "SPLIT(frase, ' ')")
        self.assertEqual(result._data_type, "array<string>")

    def test_split_invalid_args(self):
        with self.assertRaises(TypeError):
            functions.split(123, " ")
        with self.assertRaises(TypeError):
            functions.split("frase", 5)

    def test_substr_function(self):
        col = functions.Column("mensaje")
        col.substr = lambda pos, length: functions.Column(f"SUBSTRING({col.to_sql()}, {pos}, {length})")
        result = functions.substr(col, 2, 4)
        self.assertEqual(result.to_sql(), "SUBSTRING(mensaje, 2, 4)")

    def test_substring_alias(self):
        col = functions.Column("mensaje")
        col.substr = lambda pos, length: functions.Column(f"SUBSTRING({col.to_sql()}, {pos}, {length})")
        result = functions.substring(col, 1, 2)
        self.assertEqual(result.to_sql(), "SUBSTRING(mensaje, 1, 2)")

    def test_substr_invalid(self):
        with self.assertRaises(TypeError):
            functions.substr(123, 1, 2)
        with self.assertRaises(TypeError):
            functions.substr("mensaje", "uno", "dos")

        
    def test_to_char_with_column(self):
        input_col = functions.Column("fecha", data_type="date")
        result = functions.to_char(input_col)
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), "CAST(fecha AS VARCHAR)")
        self.assertEqual(result._data_type, "string")
        self.assertEqual(result.referenced_columns, input_col.referenced_columns)

    def test_to_char_with_column_name_str(self):
        result = functions.to_char("fecha")  # col("fecha") debería estar bien implementado
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), "CAST(fecha AS VARCHAR)")
        self.assertEqual(result._data_type, "string")

    def test_to_char_with_invalid_type(self):
        with self.assertRaises(TypeError) as context:
            functions.to_char(123)
        self.assertIn("to_char() espera una columna", str(context.exception))

    def test_to_char_with_format_raises_not_implemented(self):
        col_obj = functions.Column("monto", data_type="int")
        with self.assertRaises(NotImplementedError) as context:
            functions.to_char(col_obj, format="999.99")
        self.assertIn("to_char() con formato numérico", str(context.exception))
        
        
    def test_to_number_with_column(self):
        input_col = functions.Column("monto", data_type="string")
        result = functions.to_number(input_col)
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), "CAST(monto AS DOUBLE)")
        self.assertEqual(result._data_type, "double")
        self.assertEqual(result.referenced_columns, input_col.referenced_columns)

    def test_to_number_with_column_name_str(self):
        result = functions.to_number("monto")  # col("monto") debe devolver Column("monto")
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), "CAST(monto AS DOUBLE)")
        self.assertEqual(result._data_type, "double")

    def test_to_number_with_invalid_type(self):
        with self.assertRaises(TypeError) as context:
            functions.to_number(123)
        self.assertIn("to_number() espera una columna", str(context.exception))

    def test_to_number_with_format_raises_not_implemented(self):
        col_obj = functions.Column("monto", data_type="string")
        with self.assertRaises(NotImplementedError) as context:
            functions.to_number(col_obj, format="999.99")
        self.assertIn("Athena no soporta to_number() con formato", str(context.exception))
        
    def test_trim_with_column(self):
        col = functions.Column("mi_columna")
        result = functions.trim(col)
        self.assertEqual(result.to_sql(), "TRIM(mi_columna)")
        self.assertEqual(result._data_type, "string")

    def test_trim_invalid_type(self):
        with self.assertRaises(TypeError):
            functions.trim(123)

    def test_concat_with_columns(self):
        col1 = functions.Column("nombre")
        col2 = functions.Column("apellido")
        result = functions.concat(col1, col2)
        self.assertEqual(result.to_sql(), "CONCAT(nombre, apellido)")
        self.assertEqual(result._data_type, "string")

    def test_concat_with_strs(self):
        result = functions.concat("nombre", "apellido")
        self.assertEqual(result.to_sql(), "CONCAT(nombre, apellido)")

    def test_concat_empty_raises(self):
        with self.assertRaises(ValueError):
            functions.concat()

    def test_concat_with_invalid_type(self):
        with self.assertRaises(TypeError):
            functions.concat("nombre", 123)

    def test_concat_ws_valid(self):
        col1 = functions.Column("nombre")
        col2 = functions.Column("apellido")
        result = functions.concat_ws("-", col1, col2)
        self.assertEqual(result.to_sql(), "CONCAT_WS('-', nombre, apellido)")
        self.assertEqual(result._data_type, "string")

    def test_concat_ws_with_strs(self):
        result = functions.concat_ws("_", "nombre", "apellido")
        self.assertEqual(result.to_sql(), "CONCAT_WS('_', nombre, apellido)")

    def test_concat_ws_no_columns(self):
        with self.assertRaises(ValueError):
            functions.concat_ws("-")  # solo el separador, sin columnas

    def test_concat_ws_invalid_separator(self):
        with self.assertRaises(TypeError):
            functions.concat_ws(1, "columna")

    def test_concat_ws_invalid_column(self):
        with self.assertRaises(TypeError):
            functions.concat_ws("-", "columna", 99)

    # --------- Colection Functions ----------
    def test_array_size_with_column(self):
        c = functions.col("items")
        result = functions.array_size(c)
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), f"CARDINALITY({c.to_sql()})")
        self.assertEqual(result._data_type, "int")
        self.assertEqual(result.referenced_columns, c.referenced_columns)

    def test_array_size_invalid(self):
        with self.assertRaises(TypeError) as context:
            functions.array_size(123)
        self.assertIn("array_size() espera un string", str(context.exception))

    def test_size_and_cardinality_aliases(self):
        result_size = functions.size("mi_array")
        result_card = functions.cardinality("mi_array")
        self.assertEqual(result_size.to_sql(), result_card.to_sql())
        self.assertEqual(result_size._data_type, "int")
        self.assertEqual(result_card._data_type, "int")

    # ----------------------------
    # sort_array
    # ----------------------------
    def test_sort_array_ascending(self):
        result = functions.sort_array("my_array")
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), "ARRAY_SORT(my_array)")
        self.assertEqual(result._data_type, "array")
        self.assertEqual(result.referenced_columns, ["my_array"])

    def test_sort_array_descending(self):
        result = functions.sort_array("my_array", asc=False)
        self.assertEqual(result.to_sql(), "REVERSE(ARRAY_SORT(my_array))")
        self.assertEqual(result._data_type, "array")

    def test_sort_array_with_column(self):
        c = functions.col("items")
        result = functions.sort_array(c)
        self.assertEqual(result.to_sql(), f"ARRAY_SORT({c.to_sql()})")
        self.assertEqual(result.referenced_columns, c.referenced_columns)

    def test_sort_array_invalid(self):
        with self.assertRaises(TypeError):
            functions.sort_array(3.14)
    
    # ----------------------------
    # array_sort alias
    # ----------------------------
    def test_array_sort_alias(self):
        result = functions.array_sort("my_array")
        self.assertEqual(result.to_sql(), "ARRAY_SORT(my_array)")

    
    # ----------------------------
    # array_position
    # ----------------------------
    def test_array_position_with_literals(self):
        result = functions.array_position("arr", "valor")
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), "ARRAY_POSITION(arr, 'valor')")
        self.assertEqual(result._data_type, "int")

        result2 = functions.array_position("arr", 5)
        self.assertEqual(result2.to_sql(), "ARRAY_POSITION(arr, 5)")

    def test_array_position_with_columns(self):
        arr_col = functions.col("arr")
        val_col = functions.col("target")
        result = functions.array_position(arr_col, val_col)
        self.assertEqual(result.to_sql(), "ARRAY_POSITION(arr, target)")
        self.assertEqual(sorted(result.referenced_columns), ["arr", "target"])

    def test_array_position_invalid_inputs(self):
        with self.assertRaises(TypeError):
            functions.array_position(5, "x")
        with self.assertRaises(TypeError):
            functions.array_position("arr", object())

    def test_element_at_with_literals(self):
        result = functions.element_at("arr", 2)
        self.assertEqual(result.to_sql(), "ELEMENT_AT(arr, 2)")
        self.assertEqual(result._data_type, "unknown")

    def test_element_at_with_columns(self):
        arr_col = functions.col("data")
        index_col = functions.col("pos")
        result = functions.element_at(arr_col, index_col)
        self.assertEqual(result.to_sql(), "ELEMENT_AT(data, pos)")
        self.assertEqual(sorted(result.referenced_columns), ["data", "pos"])

    def test_element_at_invalid_inputs(self):
        with self.assertRaises(TypeError):
            functions.element_at(7, 1)
        with self.assertRaises(TypeError):
            functions.element_at("arr", object())
    

    # ----------------------------
    # array_max
    # ----------------------------
    def test_array_max_with_string(self):
        result = functions.array_max("my_array")
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), "ARRAY_MAX(my_array)")
        self.assertEqual(result._data_type, "unknown")
        self.assertEqual(result.referenced_columns, ["my_array"])

    def test_array_max_with_column(self):
        c = functions.col("items")
        result = functions.array_max(c)
        self.assertEqual(result.to_sql(), f"ARRAY_MAX({c.to_sql()})")
        self.assertEqual(result.referenced_columns, c.referenced_columns)

    def test_array_max_invalid(self):
        with self.assertRaises(TypeError):
            functions.array_max(42)

    # ----------------------------
    # array_min
    # ----------------------------
    def test_array_min_with_string(self):
        result = functions.array_min("my_array")
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), "ARRAY_MIN(my_array)")
        self.assertEqual(result._data_type, "unknown")
        self.assertEqual(result.referenced_columns, ["my_array"])

    def test_array_min_with_column(self):
        c = functions.col("items")
        result = functions.array_min(c)
        self.assertEqual(result.to_sql(), f"ARRAY_MIN({c.to_sql()})")
        self.assertEqual(result.referenced_columns, c.referenced_columns)

    def test_array_min_invalid(self):
        with self.assertRaises(TypeError):
            functions.array_min(None)

    # ----------------------------
    # reverse
    # ----------------------------
    def test_reverse_with_string(self):
        result = functions.reverse("texto")
        self.assertEqual(result.to_sql(), "REVERSE(texto)")
        self.assertEqual(result._data_type, "string")
        self.assertEqual(result.referenced_columns, ["texto"])

    def test_reverse_with_column(self):
        c = functions.col("array_col")
        c._data_type = "array"
        result = functions.reverse(c)
        self.assertEqual(result.to_sql(), f"REVERSE({c.to_sql()})")
        self.assertEqual(result._data_type, "array")
        self.assertEqual(result.referenced_columns, c.referenced_columns)

    def test_reverse_invalid(self):
        with self.assertRaises(TypeError):
            functions.reverse({"not": "valid"})

    # --------- Agregaciones ---------

    def test_count_function(self):
        col = functions.Column("valor")
        result = functions.count(col)
        self.assertEqual(result.to_sql(), "COUNT(valor) AS count_valor")

    def test_sum_function(self):
        col = functions.Column("valor")
        result = functions.sum(col)
        self.assertEqual(result.to_sql(), "SUM(valor) AS sum_valor")

    def test_avg_function(self):
        col = functions.Column("nota")
        result = functions.avg(col)
        self.assertEqual(result.to_sql(), "AVG(nota) AS avg_nota")

    def test_mean_alias(self):
        col = functions.Column("nota")
        result = functions.mean(col)
        self.assertEqual(result.to_sql(), "AVG(nota) AS avg_nota")

    def test_min_function(self):
        col = functions.Column("edad")
        result = functions.min(col)
        self.assertEqual(result.to_sql(), "MIN(edad) AS min_edad")

    def test_max_function(self):
        col = functions.Column("altura")
        result = functions.max(col)
        self.assertEqual(result.to_sql(), "MAX(altura) AS max_altura")

    def test_std_function(self):
        col = functions.Column("valor")
        result = functions.std(col)
        self.assertEqual(result.to_sql(), "STDDEV_SAMP(valor) AS stddev_samp_valor")

    def test_stddev_aliases(self):
        col = functions.Column("valor")
        self.assertEqual(functions.stddev(col).to_sql(), "STDDEV_SAMP(valor) AS stddev_samp_valor")
        self.assertEqual(functions.stddev_samp(col).to_sql(), "STDDEV_SAMP(valor) AS stddev_samp_valor")

    # --------- Ordenación ---------

    def test_asc_function_with_column(self):
        col = functions.Column("nombre")
        result = functions.asc(col)
        self.assertEqual(result.to_sql(), "nombre ASC")

    def test_asc_function_with_str(self):
        result = functions.asc("nombre")
        self.assertEqual(result.to_sql(), "nombre ASC")

    def test_desc_function_with_column(self):
        col = functions.Column("fecha")
        result = functions.desc(col)
        self.assertEqual(result.to_sql(), "fecha DESC")

    def test_desc_function_with_str(self):
        result = functions.desc("fecha")
        self.assertEqual(result.to_sql(), "fecha DESC")
    
    # -------- Math Functions --------
        
    def test_abs_function(self):
        col = functions.Column("valor")
        result = functions.abs(col)
        self.assertEqual(result.to_sql(), "ABS(valor)")
        self.assertEqual(result._data_type, "double")

    def test_abs_invalid(self):
        with self.assertRaises(TypeError):
            functions.abs(123)

    def test_ceil_with_column(self):
        col = functions.Column("precio")
        result = functions.ceil(col)
        self.assertEqual(result.to_sql(), "CEIL(precio)")
        self.assertEqual(result._data_type, "int")

    def test_ceil_with_column_name_as_string(self):
        result = functions.ceil("precio")
        self.assertEqual(result.to_sql(), "CEIL(precio)")
        self.assertEqual(result._data_type, "int")

    def test_ceiling_alias(self):
        result = functions.ceiling("valor")
        self.assertEqual(result.to_sql(), "CEIL(valor)")
        self.assertEqual(result._data_type, "int")

    def test_ceil_invalid_column_type(self):
        with self.assertRaises(TypeError):
            functions.ceil(123.45)


    def test_sqrt_with_column(self):
        col = functions.Column("importe")
        result = functions.sqrt(col)
        self.assertEqual(result.to_sql(), "SQRT(importe)")
        self.assertEqual(result._data_type, "double")

    def test_sqrt_with_column_name_as_string(self):
        result = functions.sqrt("importe")
        self.assertEqual(result.to_sql(), "SQRT(importe)")
        self.assertEqual(result._data_type, "double")

    def test_sqrt_invalid_column_type(self):
        with self.assertRaises(TypeError):
            functions.sqrt([1, 2, 3])  # lista no válida

    def test_floor_function(self):
        col = functions.Column("monto")
        result = functions.floor(col)
        self.assertEqual(result.to_sql(), "FLOOR(monto)")
        self.assertEqual(result._data_type, "int")

    def test_floor_invalid(self):
        with self.assertRaises(TypeError):
            functions.floor(None)

    def test_round_function_default_scale(self):
        col = functions.Column("nota")
        result = functions.round(col)
        self.assertEqual(result.to_sql(), "ROUND(nota, 0)")
        self.assertEqual(result._data_type, "int")

    def test_round_function_with_scale(self):
        col = functions.Column("nota")
        result = functions.round(col, 2)
        self.assertEqual(result.to_sql(), "ROUND(nota, 2)")
        self.assertEqual(result._data_type, "double")

    def test_round_invalid_args(self):
        with self.assertRaises(TypeError):
            functions.round(123)
        with self.assertRaises(TypeError):
            functions.round("nota", "dos")

    def test_sign_function(self):
        col = functions.Column("valor")
        result = functions.sign(col)
        self.assertEqual(result.to_sql(), "SIGN(valor)")
        self.assertEqual(result._data_type, "int")

    def test_sign_invalid(self):
        with self.assertRaises(TypeError):
            functions.sign([])

    def test_signum_alias(self):
        col = functions.Column("valor")
        result = functions.signum(col)
        self.assertEqual(result.to_sql(), "SIGN(valor)")
        
    # -------- Date Functions ----------
    
    def test_current_date(self):
        result = functions.current_date()
        self.assertEqual(result.to_sql(), "CURRENT_DATE")
        self.assertEqual(result._data_type, "date")

    def test_curdate_alias(self):
        result = functions.curdate()
        self.assertEqual(result.to_sql(), "CURRENT_DATE")

    def test_date_format(self):
        col = functions.Column("fecha")
        result = functions.date_format(col, "%Y-%m-%d")
        self.assertEqual(result.to_sql(), "format_datetime(fecha, '%Y-%m-%d')")
        self.assertEqual(result._data_type, "string")

    def test_date_format_invalid_args(self):
        with self.assertRaises(TypeError):
            functions.date_format(123, "%Y")
        with self.assertRaises(TypeError):
            functions.date_format("fecha", 2020)

    def test_dateadd_with_int(self):
        col = functions.Column("fecha")
        result = functions.dateadd(col, 7)
        self.assertEqual(result.to_sql(), "DATE_ADD('day', 7, fecha)")
        self.assertEqual(result._data_type, "date")

    def test_dateadd_with_column(self):
        fecha = functions.Column("fecha")
        dias = functions.Column("dias")
        result = functions.dateadd(fecha, dias)
        self.assertEqual(result.to_sql(), "DATE_ADD('day', dias, fecha)")

    def test_dateadd_with_invalid_type(self):
        with self.assertRaises(TypeError):
            functions.dateadd(123, 5)
        with self.assertRaises(TypeError):
            functions.dateadd("fecha", {})

    def test_date_add_alias(self):
        result1 = functions.dateadd("fecha", 1)
        result2 = functions.date_add("fecha", 1)
        self.assertEqual(result1.to_sql(), result2.to_sql())

    def test_datediff_valid(self):
        start = functions.Column("inicio")
        end = functions.Column("fin")
        result = functions.datediff(end, start)
        self.assertEqual(result.to_sql(), "DATE_DIFF('day', inicio, fin)")
        self.assertEqual(result._data_type, "int")

    def test_datediff_invalid(self):
        with self.assertRaises(TypeError):
            functions.datediff(123, "fecha")

    def test_date_diff_alias(self):
        r1 = functions.datediff("fin", "inicio")
        r2 = functions.date_diff("fin", "inicio")
        self.assertEqual(r1.to_sql(), r2.to_sql())

    def test_day_function(self):
        col = functions.Column("fecha")
        result = functions.day(col)
        self.assertEqual(result.to_sql(), "day(fecha)")
        self.assertEqual(result._data_type, "int")

    def test_dayofmonth_alias(self):
        col = functions.Column("fecha")
        result = functions.dayofmonth(col)
        self.assertEqual(result.to_sql(), "day(fecha)")

    def test_day_invalid(self):
        with self.assertRaises(TypeError):
            functions.day([])

    def test_dayofweek_function(self):
        col = functions.Column("fecha")
        result = functions.dayofweek(col)
        self.assertEqual(result.to_sql(), "DAY_OF_WEEK(fecha)")
        self.assertEqual(result._data_type, "int")

    def test_dayofweek_invalid(self):
        with self.assertRaises(TypeError):
            functions.dayofweek(999)

    def test_weekday_alias(self):
        result1 = functions.dayofweek("fecha")
        result2 = functions.weekday("fecha")
        self.assertEqual(result1.to_sql(), result2.to_sql())
        
    def test_dayofyear_valid(self):
        col = functions.Column("fecha")
        result = functions.dayofyear(col)
        self.assertEqual(result.to_sql(), "DAY_OF_YEAR(fecha)")
        self.assertEqual(result._data_type, "int")

    def test_dayofyear_invalid(self):
        with self.assertRaises(TypeError):
            functions.dayofyear(123)

    def test_month_valid(self):
        col = functions.Column("fecha")
        result = functions.month(col)
        self.assertEqual(result.to_sql(), "month(fecha)")
        self.assertEqual(result._data_type, "int")

    def test_month_invalid(self):
        with self.assertRaises(TypeError):
            functions.month(3.14)

    def test_last_day_with_column(self):
        c = functions.col("mi_columna")
        result = functions.last_day(c)
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), f"LAST_DAY_OF_MONTH({c.to_sql()})")
        self.assertEqual(result._data_type, "date")
        self.assertEqual(result.referenced_columns, c.referenced_columns)

    def test_last_day_invalid_input(self):
        with self.assertRaises(TypeError) as context:
            functions.last_day(123)
        self.assertIn("last_day() espera un string o una instancia de Column", str(context.exception))

    def test_current_timestamp_alias(self):
        result = functions.current_timestamp()
        self.assertIsInstance(result, functions.Column)
        self.assertEqual(result.to_sql(), "CURRENT_TIMESTAMP")
        self.assertEqual(result._data_type, "timestamp")
        
    def test_now_function(self):
        result = functions.now()
        self.assertEqual(result.to_sql(), "CURRENT_TIMESTAMP")
        self.assertEqual(result._data_type, "timestamp")

    def test_to_date_with_column(self):
        col = functions.Column("texto_fecha")
        result = functions.to_date(col)
        self.assertEqual(result.to_sql(), "CAST(texto_fecha AS DATE)")
        self.assertEqual(result._data_type, "date")

    def test_to_date_with_string_as_column(self):
        result = functions.to_date("fecha")
        self.assertEqual(result.to_sql(), "CAST(fecha AS DATE)")
        self.assertEqual(result._data_type, "date")

    def test_to_date_invalid(self):
        with self.assertRaises(TypeError):
            functions.to_date(20230415)

    def test_weekofyear_valid(self):
        col = functions.Column("fecha")
        result = functions.weekofyear(col)
        self.assertEqual(result.to_sql(), "WEEK_OF_YEAR(fecha)")
        self.assertEqual(result._data_type, "int")

    def test_weekofyear_invalid(self):
        with self.assertRaises(TypeError):
            functions.weekofyear(None)

    def test_year_valid(self):
        col = functions.Column("fecha")
        result = functions.year(col)
        self.assertEqual(result.to_sql(), "year(fecha)")
        self.assertEqual(result._data_type, "int")

    def test_year_invalid(self):
        with self.assertRaises(TypeError):
            functions.year([])

    def test_addmonths_with_column_and_int(self):
        col = functions.Column("fecha")
        result = functions.addmonths(col, 3)
        self.assertEqual(result.to_sql(), "DATE_ADD('month', 3, fecha)")
        self.assertEqual(result._data_type, "date")

    def test_addmonths_with_column_name_as_string_and_int(self):
        result = functions.addmonths("fecha", 6)
        self.assertEqual(result.to_sql(), "DATE_ADD('month', 6, fecha)")
        self.assertEqual(result._data_type, "date")

    def test_addmonths_with_column_and_column(self):
        fecha_col = functions.Column("fecha")
        meses_col = functions.Column("meses")
        result = functions.addmonths(fecha_col, meses_col)
        self.assertEqual(result.to_sql(), "DATE_ADD('month', meses, fecha)")
        self.assertEqual(result._data_type, "date")

    def test_addmonths_with_column_and_column_name_as_string(self):
        result = functions.addmonths("fecha", "meses")
        self.assertEqual(result.to_sql(), "DATE_ADD('month', meses, fecha)")
        self.assertEqual(result._data_type, "date")

    def test_add_months_alias(self):
        result = functions.add_months("fecha", 1)
        self.assertEqual(result.to_sql(), "DATE_ADD('month', 1, fecha)")
        self.assertEqual(result._data_type, "date")

    def test_addmonths_invalid_start_date_type(self):
        with self.assertRaises(TypeError):
            functions.addmonths(123, 2)  # start_date no válido

    def test_addmonths_invalid_months_type(self):
        with self.assertRaises(TypeError):
            functions.addmonths("fecha", 3.5)  # months no válido (float)


    def test_monthsbetween_with_columns_and_round(self):
        col1 = functions.Column("fecha_fin")
        col2 = functions.Column("fecha_inicio")
        result = functions.monthsbetween(col1, col2)
        self.assertEqual(
            result.to_sql(),
            "ROUND(CAST(DATE_DIFF('day', fecha_inicio, fecha_fin) AS DOUBLE) / 31.0, 8)"
        )
        self.assertEqual(result._data_type, "double")

    def test_monthsbetween_with_column_names_as_string_and_round(self):
        result = functions.monthsbetween("fecha_fin", "fecha_inicio")
        self.assertEqual(
            result.to_sql(),
            "ROUND(CAST(DATE_DIFF('day', fecha_inicio, fecha_fin) AS DOUBLE) / 31.0, 8)"
        )
        self.assertEqual(result._data_type, "double")

    def test_monthsbetween_with_columns_no_round(self):
        col1 = functions.Column("fecha_fin")
        col2 = functions.Column("fecha_inicio")
        result = functions.monthsbetween(col1, col2, roundOff=False)
        self.assertEqual(
            result.to_sql(),
            "CAST(DATE_DIFF('day', fecha_inicio, fecha_fin) AS DOUBLE) / 31.0"
        )
        self.assertEqual(result._data_type, "double")

    def test_monthsbetween_alias(self):
        result = functions.months_between("fecha_fin", "fecha_inicio")
        self.assertEqual(
            result.to_sql(),
            "ROUND(CAST(DATE_DIFF('day', fecha_inicio, fecha_fin) AS DOUBLE) / 31.0, 8)"
        )
        self.assertEqual(result._data_type, "double")

    def test_monthsbetween_invalid_end_date(self):
        with self.assertRaises(TypeError):
            functions.monthsbetween(123, "fecha_inicio")

    def test_monthsbetween_invalid_start_date(self):
        with self.assertRaises(TypeError):
            functions.monthsbetween("fecha_fin", 456)

    def test_from_unixtime_with_column_default_format(self):
        ts_col = functions.Column("ts_unix")
        result = functions.from_unixtime(ts_col)
        self.assertEqual(
            result.to_sql(),
            "format_datetime(from_unixtime(ts_unix), 'yyyy-MM-dd HH:mm:ss')"
        )
        self.assertEqual(result._data_type, "string")

    def test_from_unixtime_with_string_column_and_custom_format(self):
        result = functions.from_unixtime("ts_unix", "yyyy-MM-dd")
        self.assertEqual(
            result.to_sql(),
            "format_datetime(from_unixtime(ts_unix), 'yyyy-MM-dd')"
        )
        self.assertEqual(result._data_type, "string")

    def test_from_unixtime_invalid_column_type(self):
        with self.assertRaises(TypeError):
            functions.from_unixtime(12345)

    def test_from_unixtime_invalid_format_type(self):
        with self.assertRaises(TypeError):
            functions.from_unixtime("ts_unix", 123)  # formato no string

    # -------------------------
    # unix_timestamp
    # -------------------------

    def test_unix_timestamp_no_arg_returns_now(self):
        result = functions.unix_timestamp()
        self.assertEqual(result.to_sql(), "CAST(to_unixtime(now()) AS BIGINT)")
        self.assertEqual(result._data_type, "bigint")

    def test_unix_timestamp_with_column_default_format(self):
        # Con formato por defecto 'yyyy-MM-dd HH:mm:ss' → usa parse_datetime(...)
        fecha_col = functions.Column("fecha_str")
        result = functions.unix_timestamp(fecha_col)  # usa el default del firm
        self.assertEqual(
            result.to_sql(),
            "CAST(to_unixtime(parse_datetime(fecha_str, 'yyyy-MM-dd HH:mm:ss')) AS BIGINT)"
        )
        self.assertEqual(result._data_type, "bigint")

    def test_unix_timestamp_with_string_column_and_none_format(self):
        # format_str=None → pasa directo a to_unixtime(col)
        result = functions.unix_timestamp("fecha_ts", format_str=None)
        self.assertEqual(
            result.to_sql(),
            "CAST(to_unixtime(fecha_ts) AS BIGINT)"
        )
        self.assertEqual(result._data_type, "bigint")

    def test_unix_timestamp_with_string_column_and_custom_format(self):
        result = functions.unix_timestamp("fecha_str", "yyyy-MM-dd")
        self.assertEqual(
            result.to_sql(),
            "CAST(to_unixtime(parse_datetime(fecha_str, 'yyyy-MM-dd')) AS BIGINT)"
        )
        self.assertEqual(result._data_type, "bigint")

    def test_unix_timestamp_invalid_column_type(self):
        with self.assertRaises(TypeError):
            functions.unix_timestamp(3.14)

    def test_unix_timestamp_invalid_format_type(self):
        with self.assertRaises(TypeError):
            functions.unix_timestamp("fecha_str", 2025)  # formato no string
            
    # ---------

    def test_repeat_with_column(self):
        col = functions.Column("importe")
        result = functions.repeat(col, 3)
        self.assertEqual(
            result.to_sql(),
            "array_join(repeat(CAST(importe AS VARCHAR), 3),'')"
        )
        self.assertEqual(result._data_type, "string")

    def test_repeat_with_column_name_as_string(self):
        result = functions.repeat("importe", 2)
        self.assertEqual(
            result.to_sql(),
            "array_join(repeat(CAST(importe AS VARCHAR), 2),'')"
        )
        self.assertEqual(result._data_type, "string")

    def test_repeat_invalid_column_type(self):
        with self.assertRaises(TypeError):
            functions.repeat(1234, 2)  # número como columna

    def test_repeat_invalid_n_not_int(self):
        with self.assertRaises(ValueError):
            functions.repeat("importe", "3")  # n como string

    def test_repeat_invalid_n_negative(self):
        with self.assertRaises(ValueError):
            functions.repeat("importe", -1)  # n negativo
            
    # ---------- Regfular Expression ---------

    def test_rlike_valid(self):
        col = functions.Column("texto")
        result = functions.rlike(col, r"^\d{4}$")
        self.assertEqual(result.to_sql(), "regexp_like(texto, '^\\d{4}$')")
        self.assertEqual(result._data_type, "boolean")

    def test_rlike_from_string_column(self):
        result = functions.rlike("texto", r"[a-z]+")
        self.assertEqual(result.to_sql(), "regexp_like(texto, '[a-z]+')")
        self.assertEqual(result._data_type, "boolean")

    def test_rlike_invalid_type(self):
        with self.assertRaises(TypeError):
            functions.rlike(123, r"[a-z]+")

    def test_regexp_like_alias(self):
        result = functions.regexp_like("texto", r"abc.*")
        self.assertEqual(result.to_sql(), "regexp_like(texto, 'abc.*')")
        self.assertEqual(result._data_type, "boolean")

    def test_regexp_alias(self):
        result = functions.regexp("texto", r"abc.*")
        self.assertEqual(result.to_sql(), "regexp_like(texto, 'abc.*')")
        self.assertEqual(result._data_type, "boolean")

    def test_regexp_replace_valid(self):
        col = functions.Column("nombre")
        result = functions.regexp_replace(col, r"\s+", "_")
        self.assertEqual(result.to_sql(), "regexp_replace(nombre, '\\s+', '_')")
        self.assertEqual(result._data_type, "string")

    def test_regexp_replace_from_string_column(self):
        result = functions.regexp_replace("nombre", r"[0-9]", "*")
        self.assertEqual(result.to_sql(), "regexp_replace(nombre, '[0-9]', '*')")
        self.assertEqual(result._data_type, "string")

    def test_regexp_replace_invalid_type(self):
        with self.assertRaises(TypeError):
            functions.regexp_replace(123, r".*", "")
            

    
    # ---------- Window Functions ---------
    def test_row_number(self):
        result = functions.row_number()
        self.assertEqual(result.to_sql(), "row_number()")
        self.assertEqual(result._data_type, "bigint")

    def test_rank(self):
        result = functions.rank()
        self.assertEqual(result.to_sql(), "rank()")
        self.assertEqual(result._data_type, "bigint")

    def test_dense_rank(self):
        result = functions.dense_rank()
        self.assertEqual(result.to_sql(), "dense_rank()")
        self.assertEqual(result._data_type, "bigint")

    # ----------------------------
    # lag()
    # ----------------------------

    def test_lag_basic(self):
        col = functions.Column("mi_columna")
        result = functions.lag(col)
        self.assertEqual(result.to_sql(), "LAG(mi_columna, 1)")
        self.assertIsNone(result._data_type)

    def test_lag_with_offset_and_default_int(self):
        col = functions.Column("mi_columna")
        result = functions.lag(col, offset=2, default=0)
        self.assertEqual(result.to_sql(), "LAG(mi_columna, 2, 0)")

    def test_lag_with_default_string(self):
        col = functions.Column("mi_columna")
        result = functions.lag(col, offset=1, default="vacio")
        self.assertEqual(result.to_sql(), "LAG(mi_columna, 1, 'vacio')")

    def test_lag_with_column_name_str(self):
        result = functions.lag("mi_columna")
        self.assertEqual(result.to_sql(), "LAG(mi_columna, 1)")

    # ----------------------------
    # countDistinct()
    # ----------------------------

    def test_countDistinct_single_column_str(self):
        result = functions.countDistinct("col1")
        self.assertEqual(result.to_sql(), "COUNT(DISTINCT col1)")

    def test_countDistinct_single_column_obj(self):
        col = functions.Column("col1")
        result = functions.countDistinct(col)
        self.assertEqual(result.to_sql(), "COUNT(DISTINCT col1)")

    def test_countDistinct_multiple_columns_mixed(self):
        col1 = functions.Column("col1")
        result = functions.countDistinct(col1, "col2")
        self.assertEqual(result.to_sql(), "COUNT(DISTINCT col1, col2)")

    def test_countDistinct_invalid(self):
        with self.assertRaises(TypeError):
            functions.countDistinct(123)