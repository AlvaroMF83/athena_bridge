import unittest
from unittest.mock import patch, MagicMock
from athena_bridge.dataframewriter import DataFrameWriter
from botocore.exceptions import ClientError


# class DummyDataFrame:
#    pass  # Simula el objeto df

class DummyReader:
    def __init__(self):
        self._data_scanned = 0
        self._workgroup='sandbox'


class DummyDataFrame:
    def __init__(self, database="db_test"):
        self.database = database
        self.reader = DummyReader()

    def _build_query(self):
        return "SELECT * FROM tabla"

    def _execute(self, sql):
        return f"SQL ejecutado: {sql}"


class TestDataFrameWriter(unittest.TestCase):

    def setUp(self):
        self.df = DummyDataFrame()
        self.writer = DataFrameWriter(self.df)

    def test_default_values(self):
        self.assertEqual(self.writer._format, "parquet")
        self.assertEqual(self.writer._mode, "overwrite")
        self.assertIsNone(self.writer._database)
        self.assertEqual(self.writer._options, {})
        self.assertIsNone(self.writer._partitioned_by)

    def test_format_sets_value(self):
        result = self.writer.format("CSV")
        self.assertEqual(self.writer._format, "csv")
        self.assertIs(result, self.writer)  # método encadenable

    def test_mode_sets_value(self):
        result = self.writer.mode("APPEND")
        self.assertEqual(self.writer._mode, "append")
        self.assertIs(result, self.writer)

    def test_option_sets_value(self):
        result = self.writer.option("sep", "|")
        self.assertEqual(self.writer._options["sep"], "|")
        self.assertIs(result, self.writer)

    def test_partition_by_sets_columns(self):
        result = self.writer.partitionBy("col1", "col2")
        self.assertEqual(self.writer._partitioned_by, ["col1", "col2"])
        self.assertIs(result, self.writer)

    def test_save_invalid_path_raises_configuration_error(self):
        with self.assertRaises(Exception) as cm:
            self.writer.save("/local/path")
        self.assertIn("must be an S3 bucket", str(cm.exception))

    @patch("athena_bridge.dataframewriter.wr.s3.does_object_exist")
    def test_save_path_already_exists_raises_s3_write_error(self, mock_exists):
        self.writer._mode = None  # No mode specified
        mock_exists.return_value = True

        with self.assertRaises(Exception) as cm:
            self.writer.save("s3://bucket/output/")

        self.assertIn("already exists", str(cm.exception))
        self.assertIn("s3://bucket/output/", str(cm.exception))

    @patch("athena_bridge.dataframewriter.wr.s3.delete_objects")
    @patch("athena_bridge.dataframewriter.wr.athena.unload")
    def test_save_unload_fails_raises_s3_write_error(self, mock_unload, mock_delete):
        mock_unload.side_effect = ClientError(
            {"Error": {"Code": "InvalidRequest", "Message": "Some error"}},
            "Unload"
        )
        with self.assertRaises(Exception) as cm:
            self.writer.save("s3://bucket/output/")

        exc = cm.exception
        self.assertIn("An unexpected error occurred while saving the DataFrame", str(exc))
        self.assertIn("InvalidRequest", str(exc))


    @patch("athena_bridge.dataframewriter.wr.s3.delete_objects")
    @patch("athena_bridge.dataframewriter.wr.athena.unload")
    def test_save_parquet_unloads_correctly(self, mock_unload, mock_delete):
        mock_unload.return_value = MagicMock(raw_payload={"Statistics": {"DataScannedInBytes": 1234}})
        self.writer.format("parquet").mode("overwrite")
        result = self.writer.save("s3://bucket/output/")

        mock_delete.assert_called_once_with("s3://bucket/output/")
        mock_unload.assert_called_once()
        self.assertEqual(self.df.reader._data_scanned, 1234)
        self.assertIn("Saved to s3://bucket/output/", result)

    @patch("athena_bridge.dataframewriter.wr.athena.unload")
    def test_save_csv_sets_textfile_and_separator(self, mock_unload):
        mock_unload.return_value = MagicMock(raw_payload={"Statistics": {"DataScannedInBytes": 4321}})
        self.writer.format("csv").option("sep", "|").mode("overwrite")

        with patch("athena_bridge.dataframewriter.wr.s3.delete_objects"):
            result = self.writer.save("s3://bucket/csv/")

        args = mock_unload.call_args.kwargs
        self.assertEqual(args["file_format"], "TEXTFILE")
        self.assertEqual(args["field_delimiter"], "|")
        self.assertIn("Saved to s3://bucket/csv/", result)
        self.assertEqual(self.df.reader._data_scanned, 4321)

    def test_saveAsTable_overwrite(self):
        writer = self.writer.mode("overwrite")
        result = writer.saveAsTable("users", "analytics")
        self.assertEqual(result, "SQL ejecutado: CREATE OR REPLACE TABLE analytics.users AS SELECT * FROM tabla")

    def test_saveAsTable_append(self):
        writer = self.writer.mode("append")
        result = writer.saveAsTable("logs")
        self.assertEqual(result, "SQL ejecutado: INSERT INTO db_test.logs SELECT * FROM tabla")

    def test_saveAsTable_invalid_mode(self):
        self.writer.mode("ignore")
        with self.assertRaises(ValueError):
            self.writer.saveAsTable("invalid_table")
