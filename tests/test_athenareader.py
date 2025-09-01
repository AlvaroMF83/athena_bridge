import unittest
from unittest.mock import patch, MagicMock
from athena_bridge import athenareader
import pandas as pd


class TestAthenaReader(unittest.TestCase):

    def setUp(self):
        self.reader = athenareader.AthenaReader(database_tmp="temp_db", path_tmp="s3://tmp-bucket/tmp-path")

    def test_initial_values(self):
        self.assertEqual(self.reader._format, "parquet")
        self.assertEqual(self.reader.database_tmp, "temp_db")
        #self.assertEqual(self.reader.path_tmp, "s3://tmp-bucket/tmp-path")
        self.assertEqual(self.reader.data_scanned, 0)

    def test_format_setting(self):
        self.reader.format("CSV")
        self.assertEqual(self.reader._format, "csv")

    def test_database_setting(self):
        self.reader.database("analytics")
        self.assertEqual(self.reader._database, "analytics")

    def test_option_setting(self):
        self.reader.option("sep", "|")
        self.assertEqual(self.reader._options["sep"], "|")

    def test_register_temp_table(self):
        self.reader._register_temp_table("db_test", "tmp_table")
        self.assertIn(("db_test", "tmp_table"), self.reader._temporary_tables)

    def test_register_temp_path(self):
        self.reader._register_temp_path("s3://bucket/folder/")
        self.assertIn("s3://bucket/folder", self.reader._temporary_files)

    @patch("athena_bridge.dataframe.wr.catalog.table")  # mock_catalog_table
    @patch("athena_bridge.athenareader.wr.s3.store_parquet_metadata")  # mock_store
    def test_load_parquet_registers_table(self, mock_store, mock_catalog_table):
        mock_catalog_table.return_value = pd.DataFrame([{"Column Name": "col1", "Type": "int"}])

        self.reader._database = "analytics"
        self.reader.load("s3://data/parquet/")

        mock_store.assert_called_once()
        mock_catalog_table.assert_called_once()
        self.assertEqual(len(self.reader._temporary_tables), 1)

    @patch("athena_bridge.dataframe.wr.catalog.table")
    @patch("athena_bridge.athenareader.AthenaReader.infer_columns_types_from_pandas", return_value={"col1": "int"})
    @patch("athena_bridge.athenareader.wr.catalog.create_json_table")
    @patch("athena_bridge.athenareader.wr.s3.read_json")
    def test_load_json_registers_table(self, mock_read_json, mock_create_json, mock_infer, mock_df):
        self.reader.format("json")
        mock_read_json.return_value = iter([pd.DataFrame({"col1": [1]})])

        self.reader.load("s3://data/json/")
        self.assertEqual(len(self.reader._temporary_tables), 1)
        mock_create_json.assert_called_once()
        mock_df.assert_called_once()  # <- esto evita el fallo
        
        

    def test_load_invalid_format(self):
        self.reader.format("xlsx")
        with self.assertRaises(ValueError):
            self.reader.load("s3://invalid/format")
            
    def setUp(self):
        self.reader = athenareader.AthenaReader(database_tmp="temp_db", path_tmp="s3://tmp")

    def test_table_requires_database(self):
        with self.assertRaises(ValueError):
            self.reader.table("my_table")
    
    @patch("athena_bridge.athenareader.DataFrame")
    def test_table_with_database(self, mock_df):
        self.reader.database("analytics")
        self.reader.table("users")
        mock_df.assert_called_once_with(database="analytics", table="users", reader=self.reader)

    @patch.object(athenareader.AthenaReader, 'load')
    def test_parquet_delegates_to_load(self, mock_load):
        self.reader.parquet("s3://my-data")
        mock_load.assert_called_once_with("s3://my-data")
        self.assertEqual(self.reader._format, "parquet")

    @patch.object(athenareader.AthenaReader, 'load')
    def test_csv_delegates_with_options(self, mock_load):
        self.reader.csv("s3://csv-path", sep=";", header=False)
        mock_load.assert_called_once_with("s3://csv-path")
        self.assertEqual(self.reader._format, "csv")
        self.assertEqual(self.reader._options["sep"], ";")
        self.assertEqual(self.reader._options["header"], False)

    @patch.object(athenareader.AthenaReader, 'load')
    def test_json_delegates_to_load(self, mock_load):
        self.reader.json("s3://json-path")
        mock_load.assert_called_once_with("s3://json-path")
        self.assertEqual(self.reader._format, "json")

    def test_text_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            self.reader.text("s3://txt-path")

    @patch("athena_bridge.athenareader.wr.catalog.delete_table_if_exists")
    @patch("athena_bridge.athenareader.wr.s3.delete_objects")
    def test_exit_removes_temp_resources(self, mock_delete_s3, mock_delete_table):
        self.reader._temporary_tables = {("temp_db", "temp_table")}
        self.reader._temporary_files = {"s3://tmp/somepath"}

        self.reader.exit()

        mock_delete_table.assert_called_once_with(database="temp_db", table="temp_table")
        mock_delete_s3.assert_called_once_with("s3://tmp/somepath")
        self.assertEqual(len(self.reader._temporary_tables), 0)
        self.assertEqual(len(self.reader._temporary_files), 0)

    def test_infer_columns_types_from_pandas(self):
        df = pd.DataFrame({
            "id": pd.Series([1, 2], dtype="int64"),
            "nombre": pd.Series(["a", "b"], dtype="object"),
            "activo": pd.Series([True, False], dtype="bool"),
            "fecha": pd.to_datetime(["2023-01-01", "2023-01-02"])
        })

        expected = {
            "id": "bigint",
            "nombre": "string",
            "activo": "boolean",
            "fecha": "timestamp"
        }

        result = self.reader.infer_columns_types_from_pandas(df)
        self.assertEqual(result, expected)

    def test_infer_columns_types_unsupported(self):
        df = pd.DataFrame({
            "valores": pd.Series([complex(1, 2)], dtype="complex128")
        })

        with self.assertRaises(ValueError):
            self.reader.infer_columns_types_from_pandas(df)
