import unittest
from unittest.mock import patch, MagicMock
from athena_bridge.dataframe import DataFrame
from athena_bridge.dataframewriter import DataFrameWriter
from athena_bridge.functions import Column
import re
import pandas as pd
from unittest.mock import call
from botocore.exceptions import ClientError
import awswrangler as wr


class DummyReader:
    def __init__(self):
        self._data_scanned = 0
        self._path_tmp = "s3://tmp-bucket/tmp"
        self._database_tmp = "temp_db"
        self._workgroup = "sandbox"
        self._registered_table = None
        self._registered_path = None

    def _register_temp_table(self, db, table):
        self._registered_table = (db, table)

    def _register_temp_path(self, path):
        self._registered_path = path


class TestDataFrame(unittest.TestCase):

    def setUp(self):
        self.df = DataFrame.__new__(DataFrame)
        self.df.database = "test_db"
        self.df.table = "test_table"
        self.df.reader = DummyReader()
        self.df.schema = {"id": "bigint", "name": "string", "price": "double"}
        self.df.steps = [("df_0", "SELECT * FROM test_table")]
        self.df.current_alias = "df_0"
        self.df._get_next_alias = lambda: "df_1"
        self.df.copy = lambda: self.df
        self.df._check_columns_exist = MagicMock()

        # ✅ Añade estos para evitar errores en agg()
        self.df._group_by_columns = None
        self.df._group_by_select_exprs = None
        self.df._group_by_schema = None

    @patch("athena_bridge.dataframe.wr.catalog.table")
    def test_init_schema_extraction(self, mock_table):
        mock_table.return_value = MagicMock()
        mock_table.return_value.iterrows.return_value = iter([
            (0, {"Column Name": "id", "Type": "bigint"}),
            (1, {"Column Name": "name", "Type": "string"})
        ])

        df = DataFrame(database="test_db", table="test_table", reader=DummyReader())
        self.assertEqual(df.database, "test_db")
        self.assertEqual(df.table, "test_table")
        self.assertIn("id", df.schema)
        self.assertIn("name", df.schema)
        self.assertTrue(df.steps[0][1].startswith("SELECT * FROM"))

    @patch("athena_bridge.dataframe.wr.catalog.table")
    def test_init_raises_configuration_error_on_client_error(self, mock_table):
        # Simula un ClientError como si Glue no encontrara la tabla
        mock_table.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "EntityNotFoundException",
                    "Message": "Glue table not found"
                }
            },
            operation_name="GetTable"
        )

        with self.assertRaises(Exception) as context:
            DataFrame(database="test_db", table="test_table", reader=DummyReader())

        self.assertIn("Could not retrieve schema for table", str(context.exception))
        self.assertIn("'test_table' in database 'test_db'", str(context.exception))

    @patch("athena_bridge.dataframe.wr.catalog.table")
    def test_init_raises_configuration_error_on_exception(self, mock_table):
        # Simula un error de cliente de botocore, que es más realista
        mock_table.side_effect = ClientError(
            {"Error": {"Code": "EntityNotFoundException", "Message": "Table not found"}}, "GetTable")
        with self.assertRaises(Exception) as context:
            DataFrame(database="test_db", table="test_table", reader=DummyReader())
        self.assertIn("Could not retrieve schema", str(context.exception))
        self.assertIn("'test_table' in database 'test_db'", str(context.exception))

    def test_get_next_alias_increments_global(self):
        start = DataFrame._global_alias_counter
        alias1 = DataFrame._get_next_alias(DataFrame)
        alias2 = DataFrame._get_next_alias(DataFrame)
        self.assertEqual(alias1, f"df_{start}")
        self.assertEqual(alias2, f"df_{start + 1}")

    def test_build_query_basic(self):
        df = DataFrame.__new__(DataFrame)
        df.steps = [("df_0", "SELECT * FROM tabla_base")]
        query = df._build_query()
        self.assertIn("WITH df_0 AS (SELECT * FROM tabla_base)", query)
        self.assertIn("SELECT * FROM df_0", query)

    def test_build_query_with_df_alias(self):
        df = DataFrame.__new__(DataFrame)
        df.steps = [("df_0", "SELECT * FROM tabla_base")]
        df._df_alias = "df_alias"
        query = df._build_query()
        self.assertIn("df_alias AS (SELECT * FROM df_0)", query)
        self.assertTrue(query.endswith("SELECT * FROM df_alias"))

    @patch("athena_bridge.dataframe.boto3.client")
    @patch("athena_bridge.dataframe.pd.read_csv")
    def test_execute_successful_query(self, mock_read_csv, mock_boto3):
        # Mock objetos de boto3
        athena_mock = MagicMock()
        s3_mock = MagicMock()

        mock_boto3.side_effect = [athena_mock, s3_mock]

        athena_mock.start_query_execution.return_value = {
            "QueryExecutionId": "query-123"
        }

        athena_mock.get_query_execution.side_effect = [
            {"QueryExecution": {"Status": {"State": "RUNNING"}}},
            {
                "QueryExecution": {
                    "Status": {"State": "SUCCEEDED"},
                    "Statistics": {"DataScannedInBytes": 2048},
                    "ResultConfiguration": {"OutputLocation": "s3://bucket/key.csv"}
                }
            }
        ]

        s3_mock.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"col1,col2\n1,2")
        }

        mock_read_csv.return_value = "df_fake"

        result = self.df._execute("SELECT * FROM test")

        self.assertEqual(result, "df_fake")
        self.assertEqual(self.df.reader._data_scanned, 2048)
        mock_read_csv.assert_called_once()

    @patch("athena_bridge.dataframe.boto3.client")
    def test_execute_failing_query_raises_athena_query_error(self, mock_boto3):
        athena_mock = MagicMock()
        mock_boto3.return_value = athena_mock

        athena_mock.start_query_execution.return_value = {"QueryExecutionId": "query-fail-123"}
        athena_mock.get_query_execution.return_value = {
            "QueryExecution": {
                "Status": {"State": "FAILED", "StateChangeReason": "Syntax error"},
                "QueryExecutionContext": {"Database": "test_db"},
                "QueryExecutionId": "query-fail-123"
            }
        }

        with self.assertRaises(Exception) as cm:
            self.df._execute("BAD QUERY")

        exc = cm.exception
        self.assertIn("Query failed with state 'FAILED'", str(exc))
        self.assertIn("Syntax error", str(exc))

    @patch("athena_bridge.dataframe.boto3.client")
    def test_execute_client_error_raises_athena_query_error(self, mock_boto3):
        athena_mock = MagicMock()
        mock_boto3.return_value = athena_mock
        athena_mock.start_query_execution.side_effect = ClientError(
            {"Error": {"Code": "InvalidRequestException", "Message": "Query is empty"}},
            "StartQueryExecution"
        )

        with self.assertRaises(Exception) as cm:
            self.df._execute("")

        exc = cm.exception
        self.assertIn("An AWS API error occurred", str(exc))
        self.assertIn("InvalidRequestException", str(exc))
 

    def test_check_columns_exist_valid(self):
        try:
            self.df._check_columns_exist("id", "name")
        except ValueError:
            self.fail("Unexpected ValueError raised for existing columns")

    def test_check_columns_exist_invalid_column(self):
        # Usa la implementación real, no el mock
        self.df._check_columns_exist = DataFrame._check_columns_exist.__get__(self.df, DataFrame)
        self.df.schema = {"id": "bigint", "name": "string"}  # Schema realista

        with self.assertRaises(ValueError) as cm:
            self.df._check_columns_exist("nonexistent")

        self.assertIn("no está disponible", str(cm.exception))

        def test_check_columns_exist_ignores_aliases(self):
            try:
                self.df._check_columns_exist("alias.*", "df.col1")
            except ValueError:
                self.fail("Should not raise error for alias.* or df.col1")

    @patch("athena_bridge.functions.col")
    def test_getattr_valid_column(self, mock_col):
        # Simula atributos internos
        self.df.__dict__["_columns"] = ["id", "name"]
        self.df.__dict__["_df_alias"] = None  # o elimínalo si no quieres alias

        mock_col.return_value = "mocked_column"
        result = self.df.__getattr__("id")

        self.assertEqual(result, "mocked_column")
        mock_col.assert_called_once_with("id")  # sin alias

    def test_getattr_private_attribute_raises(self):
        with self.assertRaises(AttributeError):
            _ = self.df.__getattr__("_internal")

    def test_getattr_invalid_column(self):
        self.df.__dict__["_columns"] = ["id", "name"]
        with self.assertRaises(AttributeError):
            _ = self.df.__getattr__("nonexistent")

    def test_copy_creates_independent_dataframe(self):
        # Reactivar implementación real
        self.df.copy = DataFrame.copy.__get__(self.df, DataFrame)

        # Asegurar datos iniciales
        self.df.database = "db"
        self.df.table = "table"
        self.df.reader = DummyReader()
        self.df.schema = {"id": "bigint"}
        self.df.steps = [("df_0", "SELECT * FROM db.table")]
        self.df.current_alias = "df_0"

        new_df = self.df.copy()

        self.assertIsInstance(new_df, DataFrame)
        self.assertEqual(new_df.database, self.df.database)
        self.assertEqual(new_df.table, self.df.table)
        self.assertEqual(new_df.reader, self.df.reader)
        self.assertEqual(new_df.schema, self.df.schema)
        self.assertEqual(new_df.steps, self.df.steps)
        self.assertEqual(new_df.current_alias, self.df.current_alias)
        self.assertIsNot(new_df, self.df)

    def test_dtypes_returns_schema_items(self):
        expected = [("id", "bigint"), ("name", "string"), ("price", "double")]
        self.assertEqual(self.df.dtypes, expected)

    def test_columns_returns_schema_keys(self):
        self.assertEqual(self.df.columns, ["id", "name", "price"])

    def test_write_returns_dataframewriter(self):
        writer = self.df.write
        self.assertIsInstance(writer, DataFrameWriter)
        self.assertEqual(writer.df, self.df)

    @patch("builtins.print")
    def test_print_schema_outputs_correct_format(self, mock_print):
        self.df.printSchema()
        mock_print.assert_any_call("root")
        mock_print.assert_any_call(" |-- id: bigint (nullable = true)")
        mock_print.assert_any_call(" |-- name: string (nullable = true)")

    @patch.object(DataFrame, "_execute")
    @patch.object(DataFrame, "_build_query")
    @patch.object(DataFrame, "_check_columns_exist")
    def test_describe_with_numeric_columns(self, mock_check, mock_build, mock_execute):
        mock_df = MagicMock()
        mock_df.iloc.__getitem__.return_value = {
            "id_count": 100,
            "id_mean": 50.5,
            "id_stddev": 12.3,
            "id_min": 1,
            "id_max": 100
        }
        mock_execute.return_value = mock_df
        mock_build.return_value = "SELECT ..."

        result = self.df.describe("id")
        self.assertEqual(result.columns.tolist(), ["summary", "id"])
        self.assertEqual(result.iloc[0][0], "count")
        self.assertEqual(result.iloc[0][1], 100)

    @patch.object(DataFrame, "_check_columns_exist")
    def test_describe_raises_if_no_numeric(self, mock_check):
        self.df.schema = {"name": "string"}
        with self.assertRaises(ValueError):
            self.df.describe()

    @patch("athena_bridge.functions.col")  # <-- el lugar correcto
    @patch.object(DataFrame, "_check_columns_exist")
    def test_select_with_strings_and_col_conversion(self, mock_check, mock_col):
        col_obj = Column("id", referenced_columns=["id"])
        mock_col.return_value = col_obj
        self.df.schema = {"id": "bigint"}
        self.df._check_columns_exist = MagicMock()
        self.df.copy = lambda: self.df  # simplificación para el test
        new_df = self.df.select("id")
        self.assertIsInstance(new_df, DataFrame)

    @patch.object(DataFrame, "_check_columns_exist")
    def test_select_raises_on_invalid_input(self, mock_check):
        with self.assertRaises(TypeError):
            self.df.select(123)

    # -------- DROP --------

    def test_drop_valid_columns(self):
        new_df = self.df.drop("name")
        self.assertIn("id", new_df.schema)
        self.assertIn("price", new_df.schema)
        self.assertNotIn("name", new_df.schema)
        self.assertIn(("df_1", "SELECT id, price FROM df_0"), new_df.steps)

    def test_drop_raises_on_no_args(self):
        with self.assertRaises(ValueError):
            self.df.drop()

    def test_drop_raises_on_list_argument(self):
        with self.assertRaises(TypeError):
            self.df.drop(["id", "name"])

    def test_drop_raises_on_non_string(self):
        with self.assertRaises(TypeError):
            self.df.drop(123)

    # -------- FILTER / WHERE --------

    def test_filter_with_string(self):
        self.df._get_next_alias = lambda: "df_1"
        new_df = self.df.filter("price > 100")
        self.assertIn(("df_1", "SELECT * FROM df_0 WHERE price > 100"), new_df.steps)

    def test_filter_with_column(self):
        self.df.schema = {"id": "bigint", "price": "double"}
        self.df._get_next_alias = lambda: "df_1"
        self.df._check_columns_exist = MagicMock()

        condition = Column("price > 100", referenced_columns=["price"])
        condition.to_sql = lambda: "price > 100"

        new_df = self.df.filter(condition)
        self.df._check_columns_exist.assert_called_with("price")
        self.assertIn(("df_1", "SELECT * FROM df_0 WHERE price > 100"), new_df.steps)

    def test_filter_invalid_type(self):
        with self.assertRaises(TypeError):
            self.df.filter(123)

    def test_where_is_alias_for_filter(self):
        self.assertIs(DataFrame.where, DataFrame.filter)

    # -------- DISTINCT --------

    def test_distinct_adds_query_step(self):
        self.df._get_next_alias = lambda: "df_1"
        new_df = self.df.distinct()
        self.assertIn(("df_1", "SELECT DISTINCT * FROM df_0"), new_df.steps)
        self.assertEqual(new_df.current_alias, "df_1")

    # -------- orderBy --------

    def test_order_by_single_column_default_asc(self):
        new_df = self.df.orderBy("id")
        self.assertIn(("df_1", "SELECT * FROM df_0 ORDER BY id ASC"), new_df.steps)

    def test_order_by_multiple_columns_and_flags(self):
        new_df = self.df.orderBy("id", "price", ascending=[True, False])
        self.assertIn(("df_1", "SELECT * FROM df_0 ORDER BY id ASC, price DESC"), new_df.steps)

    def test_order_by_with_column_objects(self):
        col1 = Column("id")
        col1.to_sql = lambda: "id"
        col2 = Column("price")
        col2.to_sql = lambda: "price"
        new_df = self.df.orderBy(col1, col2, ascending=[False, True])
        self.assertIn(("df_1", "SELECT * FROM df_0 ORDER BY id DESC, price ASC"), new_df.steps)

    def test_order_by_with_invalid_column_type(self):
        with self.assertRaises(TypeError):
            self.df.orderBy(123)

    def test_order_by_with_mismatched_ascending(self):
        with self.assertRaises(ValueError):
            self.df.orderBy("id", "price", ascending=[True])

    # -------- sort (alias) --------

    def test_sort_is_alias_for_order_by(self):
        self.df.orderBy = MagicMock(return_value="ok")
        result = self.df.sort("id")
        self.df.orderBy.assert_called_once_with("id", ascending=True)
        self.assertEqual(result, "ok")

    # -------- groupBy --------

    def test_group_by_list_argument(self):
        new_df = self.df.groupBy(["id", "name"])
        self.assertEqual(new_df._group_by_columns, ["id", "name"])
        self.df._check_columns_exist.assert_has_calls([call("id"), call("name")])
        self.assertEqual(self.df._check_columns_exist.call_count, 2)

    def test_group_by_strings(self):
        new_df = self.df.groupBy("id", "name")
        self.assertEqual(new_df._group_by_columns, ["id", "name"])
        self.df._check_columns_exist.assert_has_calls([call("id"), call("name")])
        self.assertEqual(self.df._check_columns_exist.call_count, 2)

    def test_group_by_empty(self):
        new_df = self.df.groupBy()
        self.assertEqual(new_df._group_by_columns, [])

    def test_groupby_alias_is_groupBy(self):
        self.assertIs(DataFrame.groupby, DataFrame.groupBy)

    # -------- agg() --------

    def test_agg_without_groupby(self):
        col = Column("AVG(price)", referenced_columns=["price"], data_type="double").alias("avg_price")
        col.to_sql = lambda: "AVG(price)"

        new_df = self.df.agg(col)

        # Verifica que se llamó a check_columns_exist por cada columna referenciada
        self.df._check_columns_exist.assert_has_calls([call("price")])
        self.assertEqual(self.df._check_columns_exist.call_count, 1)

        self.assertIn(("df_1", "SELECT AVG(price) FROM df_0"), new_df.steps)
        # self.assertEqual(new_df.schema, {"avg_price": "double"})  # opcional

    def test_agg_with_groupby(self):
        self.df._group_by_columns = ["id"]
        self.df._group_by_select_exprs = ["id AS id"]
        self.df._group_by_schema = {"id": "bigint"}

        col = Column("MAX(price)", referenced_columns=["price"], data_type="double").alias("max_price")
        col.to_sql = lambda: "MAX(price)"

        new_df = self.df.agg(col)

    def test_agg_raises_on_non_column(self):
        with self.assertRaises(TypeError):
            self.df.agg("not_a_column")

    # -------- withColumnRenamed --------

    def test_with_column_renamed(self):
        self.df.schema = {"old": "string", "id": "bigint"}
        new_df = self.df.withColumnRenamed("old", "new")

        self.df._check_columns_exist.assert_called_once_with("old")
        self.assertIn("old AS new", new_df.steps[-1][1])
        self.assertIn("new", new_df.schema)
        self.assertNotIn("old", new_df.schema)

    # -------- withColumn --------

    def test_with_column_adds_new_column(self):
        col_expr = Column("price * 2", referenced_columns=["price"], data_type="double").alias("price_doble")
        col_expr.to_sql = lambda: "price * 2"

        new_df = self.df.withColumn("price_doble", col_expr)

        self.assertIn("price * 2", new_df.steps[-1][1])  # sin "AS price_doble"
        self.assertIn("price_doble", new_df.schema)

    def test_with_column_replaces_existing_column(self):
        self.df.schema = {"id": "bigint", "price": "double"}
        col_expr = Column("price + 10", referenced_columns=["price"], data_type="double").alias("price")
        col_expr.to_sql = lambda: "price + 10"

        new_df = self.df.withColumn("price", col_expr)

        self.assertIn("price + 10", new_df.steps[-1][1])  # sin "AS price"
        self.assertIn("price", new_df.schema)
        self.assertEqual(new_df.schema["price"], "double")

    def test_with_column_raises_on_invalid_type(self):
        with self.assertRaises(TypeError):
            self.df.withColumn("new_col", "not_a_column_object")

        # ---------- limit ----------

    def test_limit_adds_limit_clause(self):
        new_df = self.df.limit(10)
        self.assertIn(("df_1", "SELECT * FROM df_0 LIMIT 10"), new_df.steps)
        self.assertEqual(new_df.current_alias, "df_1")

    # ---------- fillna / fill ----------

    def test_fillna_all_columns(self):
        new_df = self.df.fillna(0)
        expected_exprs = [
            "COALESCE(id, 0) AS id",
            "COALESCE(name, 0) AS name",
            "COALESCE(price, 0) AS price"
        ]
        for expr in expected_exprs:
            self.assertIn(expr, new_df.steps[-1][1])
        self.assertEqual(new_df.schema, self.df.schema)

    def test_fillna_subset(self):
        new_df = self.df.fillna("N/A", subset=["name"])
        self.df._check_columns_exist.assert_called_once_with("name")
        self.assertIn("COALESCE(name, 'N/A') AS name", new_df.steps[-1][1])
        self.assertIn("id", new_df.steps[-1][1])  # no transform
        self.assertEqual(new_df.schema, self.df.schema)

    def test_fill_alias_works(self):
        new_df = self.df.fill(0)
        self.assertIn("COALESCE(id, 0) AS id", new_df.steps[-1][1])

    # ---------- union ----------

    def test_union_with_matching_schema(self):
        other = DataFrame.__new__(DataFrame)
        other.database = "test_db"
        other.table = "other_table"
        other.reader = self.df.reader
        other.schema = self.df.schema.copy()
        other.steps = [("df_2", "SELECT * FROM other_table")]
        other.current_alias = "df_2"
        other._get_next_alias = lambda: "df_x"

        self.df._get_next_alias = lambda: "df_3"
        new_df = self.df.union(other)

        self.assertIn("UNION ALL", new_df.steps[-1][1])
        self.assertIn("SELECT * FROM df_0", new_df.steps[-1][1])
        self.assertIn("SELECT * FROM df_2", new_df.steps[-1][1])
        self.assertEqual(new_df.schema, self.df.schema)

    def test_union_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.df.union("not_a_dataframe")

    def test_union_raises_on_schema_mismatch(self):
        other = DataFrame.__new__(DataFrame)
        other.schema = {"different": "int"}
        with self.assertRaises(ValueError):
            self.df.union(other)

    # -------- Acciones ----------------

    @patch.object(DataFrame, "_execute")
    @patch.object(DataFrame, "_build_query")
    def test_count_without_groupby_returns_scalar(self, mock_build_query, mock_execute):
        mock_build_query.return_value = "SELECT COUNT(*) as count FROM df_0"
        mock_execute.return_value = pd.DataFrame([{"count": 42}])

        result = self.df.count()

        mock_build_query.assert_called_once()
        mock_execute.assert_called_once()
        self.assertEqual(result, 42)

    def test_count_with_groupby_returns_dataframe(self):
        self.df._group_by_columns = ["id"]
        self.df._check_columns_exist = MagicMock()

        self.df._get_next_alias = lambda: "df_1"
        self.df.copy = lambda: self.df

        result = self.df.count()

        # Validamos que es un DataFrame (no escalar)
        self.assertIsInstance(result, DataFrame)

        # Validamos que el último paso sea el GROUP BY correcto
        last_query = result.steps[-1][1]
        self.assertIn("GROUP BY id", last_query)
        self.assertIn("COUNT(*) as count", last_query)

        # Validamos que el schema tenga los group_by + count
        self.assertEqual(result.schema, {
            "id": "bigint",
            "count": "bigint"
        })

        # Validamos que el flag haya sido limpiado
        self.assertIsNone(result._group_by_columns)

    # -------- dropDuplicates --------

    def test_drop_duplicates_all_columns(self):
        # Generador de alias controlado
        alias_gen = (f"df_{i}" for i in range(100))

        # Simulamos la copia del DataFrame como nueva instancia
        df_copy = DataFrame.__new__(DataFrame)
        df_copy.database = self.df.database
        df_copy.table = self.df.table
        df_copy.reader = self.df.reader
        df_copy.schema = self.df.schema.copy()
        df_copy.steps = self.df.steps.copy()
        df_copy.current_alias = self.df.current_alias
        df_copy._check_columns_exist = MagicMock()
        df_copy._get_next_alias = lambda: next(alias_gen)

        # Reemplazamos el .copy() del DataFrame original para devolver la copia
        self.df.copy = lambda: df_copy

        # También el alias del original, por si acaso lo llama antes
        self.df._get_next_alias = lambda: next(alias_gen)

        # Ejecutamos el método
        result = self.df.drop_duplicates()

        # Validamos los pasos creados y el alias final
        self.assertEqual(result.current_alias, "df_1")
        self.assertEqual(result.steps[-2][0], "df_0")  # paso con ROW_NUMBER
        self.assertEqual(result.steps[-1][0], "df_1")  # paso con WHERE rn = 1

        # Validamos que las partes clave están en las queries
        row_number_query = result.steps[-2][1]
        final_query = result.steps[-1][1]
        self.assertIn("ROW_NUMBER() OVER", row_number_query)
        self.assertIn("PARTITION BY id, name, price", row_number_query)
        self.assertIn("WHERE rn = 1", final_query)

    def test_drop_duplicates_subset(self):
        result = self.df.drop_duplicates(subset=["name", "price"])
        self.df._check_columns_exist.assert_called_once_with("name", "price")
        query = result.steps[-2][1]
        self.assertIn("PARTITION BY name, price", query)

    def test_drop_duplicates_invalid_subset(self):
        with self.assertRaises(TypeError):
            self.df.drop_duplicates(subset="not_a_list")

    def test_drop_duplicates_alias(self):
        result1 = self.df.dropDuplicates(["id"])
        result2 = self.df.drop_duplicates(["id"])
        self.assertEqual(result1.steps, result2.steps)

    # -------- show --------

    @patch.object(DataFrame, "_execute")
    @patch.object(DataFrame, "_build_query")
    @patch.object(DataFrame, "limit")
    def test_show_default_output(self, mock_limit, mock_build_query, mock_execute):
        df_mock = pd.DataFrame([{"id": 1, "name": "Alice", "price": 10.5}])
        mock_limit.return_value = self.df
        mock_build_query.return_value = "SELECT * FROM df_0 LIMIT 20"
        mock_execute.return_value = df_mock

        with patch("builtins.print") as mock_print:
            self.df.show()

            # Captura todo lo que se imprimió en una sola string
            output = "".join(str(call.args[0]) for call in mock_print.call_args_list)
            self.assertIn("Alice", output)
            self.assertIn("10.5", output)

    @patch.object(DataFrame, "_execute")
    @patch.object(DataFrame, "_build_query")
    @patch.object(DataFrame, "limit")
    def test_show_truncate_custom(self, mock_limit, mock_build_query, mock_execute):
        long_name = "A very long name that should be truncated"
        df_mock = pd.DataFrame([{"id": 1, "name": long_name, "price": 10.5}])
        mock_limit.return_value = self.df
        mock_build_query.return_value = "SELECT * FROM df_0 LIMIT 20"
        mock_execute.return_value = df_mock

        with patch("builtins.print") as mock_print:
            self.df.show(truncate=10)
            printed = "".join(str(c[0][0]) for c in mock_print.call_args_list)
            self.assertIn("A very ...", printed)

    @patch.object(DataFrame, "_execute")
    @patch.object(DataFrame, "_build_query")
    @patch.object(DataFrame, "limit")
    def test_show_invalid_truncate_raises(self, mock_limit, mock_build_query, mock_execute):
        # Preparar mocks para evitar llamadas reales a Athena
        mock_limit.return_value = self.df
        mock_build_query.return_value = "SELECT * FROM df_0 LIMIT 20"
        mock_execute.return_value = pd.DataFrame([{"id": 1, "name": "Alice"}])

        with self.assertRaises(TypeError):
            self.df.show(truncate="invalid")

    @patch.object(DataFrame, "limit")
    @patch.object(DataFrame, "_build_query")
    @patch.object(DataFrame, "_execute")
    def test_head(self, mock_execute, mock_build_query, mock_limit):
        mock_limit.return_value = self.df
        mock_build_query.return_value = "SELECT * FROM df_0"
        mock_execute.return_value = pd.DataFrame([{"id": 1, "name": "Alice"}])

        result = self.df.head(3)

        mock_limit.assert_called_once_with(3)
        self.assertIsInstance(result, pd.DataFrame)

    @patch.object(DataFrame, "orderBy")
    @patch.object(DataFrame, "limit")
    @patch.object(DataFrame, "_build_query")
    @patch.object(DataFrame, "_execute")
    def test_tail(self, mock_execute, mock_build_query, mock_limit, mock_orderBy):
        mock_orderBy.return_value = self.df
        mock_limit.return_value = self.df
        mock_build_query.return_value = "SELECT * FROM df_0"
        df_data = pd.DataFrame([{"id": 1}, {"id": 2}, {"id": 3}])
        mock_execute.return_value = df_data

        result = self.df.tail(2)

        mock_orderBy.assert_called_once_with("id", "name", "price", ascending=False)
        mock_limit.assert_called_once_with(2)

        # El resultado debe estar invertido: últimos 2 → [2, 3] → invertido [3, 2]
        self.assertEqual(result.iloc[0]["id"], 3)
        self.assertEqual(result.iloc[1]["id"], 2)

    @patch.object(DataFrame, "limit")
    @patch.object(DataFrame, "_build_query")
    @patch.object(DataFrame, "_execute")
    def test_take_returns_dicts(self, mock_execute, mock_build_query, mock_limit):
        df_data = pd.DataFrame([{"id": 1}, {"id": 2}])
        mock_limit.return_value = self.df
        mock_build_query.return_value = "SELECT * FROM df_0"
        mock_execute.return_value = df_data

        result = self.df.take(2)

        mock_limit.assert_called_once_with(2)
        self.assertEqual(result, [{"id": 1}, {"id": 2}])

    @patch.object(DataFrame, "_build_query")
    @patch.object(DataFrame, "_execute")
    def test_to_pandas(self, mock_execute, mock_build_query):
        df_data = pd.DataFrame([{"id": 1}])
        mock_build_query.return_value = "SELECT * FROM df_0"
        mock_execute.return_value = df_data

        result = self.df.toPandas()

        mock_build_query.assert_called_once()
        mock_execute.assert_called_once()
        self.assertEqual(result.iloc[0]["id"], 1)

    @patch.object(DataFrame, "_execute")
    def test_first_returns_dict(self, mock_execute):
        mock_execute.return_value = pd.DataFrame([{"id": 1, "name": "Alice"}])
        result = self.df.first()
        self.assertEqual(result, {"id": 1, "name": "Alice"})

    @patch.object(DataFrame, "_execute")
    def test_first_returns_none_if_empty(self, mock_execute):
        mock_execute.return_value = pd.DataFrame([])
        result = self.df.first()
        self.assertIsNone(result)

    @patch("athena_bridge.dataframe.wr.athena.unload")
    @patch("athena_bridge.dataframe.wr.s3.store_parquet_metadata")
    def test_cache_changes_state(self, mock_store, mock_unload):
        # Simula que se devolvieron estadísticas
        mock_unload.return_value = MagicMock(raw_payload={"Statistics": {"DataScannedInBytes": 2048}})

        # Simula que el query ya está definido
        self.df._build_query = MagicMock(return_value="SELECT * FROM df_0")

        result = self.df.cache()

        # Validaciones
        self.assertTrue(result.table.startswith("cached_"))
        self.assertEqual(result.database, "temp_db")
        self.assertIn("SELECT * FROM temp_db", result.steps[-1][1])
        self.assertEqual(result.reader._data_scanned, 2048)
        self.assertEqual(result.reader._registered_table[0], "temp_db")
        self.assertTrue(result.reader._registered_path.startswith("s3://tmp-bucket/tmp/cached_"))

    @patch("athena_bridge.dataframe.wr.athena.unload")
    def test_cache_raises_s3_write_error_on_failure(self, mock_unload):
        self.df._build_query = MagicMock(return_value="SELECT * FROM df_0")
        mock_unload.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Permission denied"}},
            "Unload"
        )

        with self.assertRaises(Exception) as cm:
            self.df.cache()

        exc = cm.exception
        self.assertRegex(str(exc), r"(Failed to cache DataFrame to S3|unexpected error .* caching DataFrame to S3)")
        self.assertIn("AccessDenied", str(exc))

    def test_show_query_prints_query(self):
        self.df._build_query = MagicMock(return_value="SELECT * FROM test_table")
        with patch("builtins.print") as mock_print:
            self.df.show_query()
            mock_print.assert_called_once_with("SELECT * FROM test_table")

    # ----------------------------
    # DataFrame.isEmpty
    # ----------------------------
    def test_dataframe_is_empty_true(self):
        df = DataFrame.__new__(DataFrame)
        df.count = MagicMock(return_value=0)
        self.assertTrue(df.isEmpty())

    def test_dataframe_is_empty_false(self):
        df = DataFrame.__new__(DataFrame)
        df.count = MagicMock(return_value=5)
        self.assertFalse(df.isEmpty())


class TestDataFrameJoin(unittest.TestCase):

    def setUp(self):
        self.df1 = DataFrame.__new__(DataFrame)
        self.df1.database = "db"
        self.df1.table = "table1"
        self.df1.reader = DummyReader()
        self.df1.schema = {"id": "bigint", "name": "string"}
        self.df1.steps = [("df_0", "SELECT * FROM table1")]
        self.df1.current_alias = "df_0"
        self.df1.copy = lambda: self.df1
        self.df1._get_next_alias = lambda: "df_1"

        self.df2 = DataFrame.__new__(DataFrame)
        self.df2.database = "db"
        self.df2.table = "table2"
        self.df2.reader = self.df1.reader
        self.df2.schema = {"id": "bigint", "email": "string"}
        self.df2.steps = [("df_2", "SELECT * FROM table2")]
        self.df2.current_alias = "df_2"
        self.df2._get_next_alias = lambda: "df_3"

    def test_join_on_string_column_inner(self):
        alias_gen = (f"df_alias_{i}" for i in range(100))

        def next_alias(*args, **kwargs):
            return next(alias_gen)

        with patch.object(DataFrame, "_get_next_alias", new=next_alias):
            self.df2.current_alias = "df_alias_1"
            self.df2.steps = [("df_alias_1", "SELECT * FROM table2")]

            result = self.df1.join(self.df2, on="id", how="inner")
            query = result.steps[-1][1]

            self.assertIn("INNER JOIN", query)
            self.assertRegex(query, r"ON df_0.id = df_alias_\d+\.id")

    def test_join_on_column_object(self):
        cond = Column("df_0.id = df_2.id")
        cond.to_sql = lambda: "df_0.id = df_2.id"
        result = self.df1.join(self.df2, on=cond, how="inner")

        self.assertIn("ON df_0.id = df_2.id", result.steps[-1][1])

    def test_join_on_list_of_columns(self):
        self.df1.schema = {"id": "bigint", "name": "string"}
        self.df2.schema = {"id": "bigint", "name": "string"}

        # Alias generator predictably returns df_0, df_1, df_2, etc.
        alias_gen = (f"df_alias_{i}" for i in range(100))

        def next_alias(*args, **kwargs):
            return next(alias_gen)

        with patch.object(DataFrame, "_get_next_alias", new=next_alias):
            # Establecemos current_alias fijos
            self.df1.current_alias = "df_0"
            self.df1.steps = [("df_0", "SELECT * FROM table1")]

            self.df2.current_alias = "df_1"
            self.df2.steps = [("df_1", "SELECT * FROM table2")]

            result = self.df1.join(self.df2, on=["id", "name"], how="left")

            query = result.steps[-1][1]

            # Verificación más flexible (evita hardcodeo exacto de alias)
            assert "LEFT JOIN" in query
            assert re.search(r"ON df_0.id = df_alias_\d+\.id AND df_0.name = df_alias_\d+\.name", query)

        def test_join_type_right_replaces_conflicts(self):
            self.df2.schema = {"id": "bigint", "name": "string"}

            alias_gen = (f"df_alias_{i}" for i in range(100))
            with patch.object(DataFrame, "_get_next_alias", new=lambda *args: next(alias_gen)):
                self.df2.current_alias = "df_alias_1"
                self.df2.steps = [("df_alias_1", "SELECT * FROM table2")]

                result = self.df1.join(self.df2, on="id", how="right")
                query = result.steps[-1][1]

                self.assertIn("RIGHT JOIN", query)
                self.assertRegex(query, r"df_alias_\d+\.name AS name")

        def test_join_type_outer_adds_suffix_for_duplicates(self):
            self.df2.schema = {"id": "bigint", "name": "string"}

            alias_gen = (f"df_alias_{i}" for i in range(100))
            with patch.object(DataFrame, "_get_next_alias", new=lambda *args: next(alias_gen)):
                self.df2.current_alias = "df_alias_1"
                self.df2.steps = [("df_alias_1", "SELECT * FROM table2")]

                result = self.df1.join(self.df2, on="id", how="outer")
                query = result.steps[-1][1]

                self.assertIn("OUTER JOIN", query)
                self.assertIn("df_0.name AS name", query)
                self.assertRegex(query, r"df_alias_\d+\.name AS name_right")

    def test_join_invalid_on_type(self):
        with self.assertRaises(TypeError):
            self.df1.join(self.df2, on=1234)

