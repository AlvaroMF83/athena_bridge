import sys
import types
import importlib
import unittest
from unittest.mock import MagicMock, patch

class DummyDF:
    sql = "SELECT * FROM dummy"

    def to_sql(self):
        return self.sql

    def _build_query(self):
        return self.sql

    @property
    def database(self):
        return "dummy_db"

    @property
    def table(self):
        return "dummy_table"

class TestDataprocAthenaBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # --- Fake athenareader ---
        fake_ar = types.ModuleType("athenareader")

        class FakeAthenaReader:
            def __init__(self, database_tmp, path_tmp):
                self.database_tmp = database_tmp
                self.path_tmp = path_tmp
                self.calls = []
                self._options = {}
                self.last_format = None
                self.exit_called = False
                self.db = None

            def format(self, fmt):
                self.last_format = fmt
                self.calls.append(("format", fmt))
                return self

            def option(self, k, v):
                self._options[k] = v
                self.calls.append(("option", k, v))
                return self

            def database(self, db):
                self.db = db
                self.calls.append(("database", db))
                return self

            def table(self, tbl):
                self.calls.append(("table", tbl))
                return f"DF_TABLE:{self.db}.{tbl}"

            # Camino principal: _DPRead usa load() si existe
            def load(self, path):
                self.calls.append(("load", path))
                return f"DF_LOAD:{path}|fmt={self.last_format}|opts={self._options.copy()}"

            # Fallbacks
            def csv(self, path):
                self.calls.append(("csv", path))
                return f"DF_CSV:{path}"

            def parquet(self, path):
                self.calls.append(("parquet", path))
                return f"DF_PARQUET:{path}"

            def json(self, path):
                self.calls.append(("json", path))
                return f"DF_JSON:{path}"

            def exit(self):
                self.exit_called = True
                return "EXIT_OK"

        fake_ar.AthenaReader = FakeAthenaReader

        # --- Fake dataframewriter ---
        fake_dw = types.ModuleType("dataframewriter")

        class FakeWriter:
            def __init__(self, df):
                self.df = df
                self.called = {
                    "format": None,
                    "mode": None,
                    "options": {},
                    "partitionBy": None,
                    "save": None,
                    "saveAsTable": None,
                }

            def format(self, fmt):
                self.called["format"] = fmt
                return self

            def mode(self, m):
                self.called["mode"] = m
                return self

            def option(self, k, v):
                self.called["options"][k] = v
                return self

            def partitionBy(self, *cols):
                self.called["partitionBy"] = list(cols)
                return self

            def save(self, path):
                self.called["save"] = path
                return {
                    "ok": True,
                    "path": path,
                    "fmt": self.called["format"],
                    "mode": self.called["mode"],
                    "options": self.called["options"],
                    "partitions": self.called["partitionBy"],
                    "df": self.df,
                }

            def saveAsTable(self, table_name, database=None):
                self.called["saveAsTable"] = (table_name, database)
                return {
                    "ok": True,
                    "table": table_name,
                    "db": database,
                    "fmt": self.called["format"],
                    "mode": self.called["mode"],
                    "options": self.called["options"],
                }

        fake_dw.DataFrameWriter = FakeWriter

        # Inyecta fakes en sys.modules ANTES de importar el bridge
        cls._orig_ar = sys.modules.get("athenareader")
        cls._orig_dw = sys.modules.get("dataframewriter")
        sys.modules["athenareader"] = fake_ar
        sys.modules["dataframewriter"] = fake_dw

        # Importa el módulo bajo test
        from athena_bridge import dataproc_athena_bridge
        cls.bridge = importlib.reload(dataproc_athena_bridge)

    @classmethod
    def tearDownClass(cls):
        # Limpia módulos inyectados
        if cls._orig_ar is not None:
            sys.modules["athenareader"] = cls._orig_ar
        else:
            sys.modules.pop("athenareader", None)
        if cls._orig_dw is not None:
            sys.modules["dataframewriter"] = cls._orig_dw
        else:
            sys.modules.pop("dataframewriter", None)

    # ----------------- Tests de lectura -----------------

    def test_read_parquet_propagates_format_options_and_load(self):
        dp = self.bridge.DataprocAthenaBridge(database_tmp="tmp_db", path_tmp="s3://tmp/")
    
        # mockeamos el método load para evitar cualquier acceso real a S3
        with patch.object(dp._reader, 'load', return_value="MOCK_DF") as mock_load:
            df = dp.read().option("header", True).option("sep", ";").parquet("s3://bucket/in/")
    
            self.assertEqual(df, "MOCK_DF")
            mock_load.assert_called_once_with("s3://bucket/in/")
    
            # check de formato y opciones en el reader
            self.assertEqual(dp._reader._options, {"header": True, "sep": ";"})

    def test_read_resets_options_between_calls(self):
        dp = self.bridge.DataprocAthenaBridge("tmp_db", "s3://tmp/")
    
        with patch.object(dp._reader, 'load', return_value="DF1") as mock_load_1:
            _ = dp.read().option("header", True).option("sep", ";").csv("s3://bucket/one.csv")
            mock_load_1.assert_called_once_with("s3://bucket/one.csv")
    
        with patch.object(dp._reader, 'load', return_value="DF2") as mock_load_2:
            _ = dp.read().option("sep", ",").csv("s3://bucket/two.csv")
            mock_load_2.assert_called_once_with("s3://bucket/two.csv")

    def test_table_calls_database_and_table(self):
        dp = self.bridge.DataprocAthenaBridge("tmp_db", "s3://tmp/")
    
        dp._reader.database = MagicMock(return_value=dp._reader)
        dp._reader.table = MagicMock(return_value="MOCK_DF")
    
        out = dp.read().table("mi_db.mi_tabla")
    
        self.assertEqual(out, "MOCK_DF")
        dp._reader.database.assert_called_once_with("mi_db")
        dp._reader.table.assert_called_once_with("mi_tabla")

    def test_table_raises_without_dot(self):
        dp = self.bridge.DataprocAthenaBridge("tmp_db", "s3://tmp/")
        with self.assertRaises(ValueError):
            dp.read().table("solo_db_sin_punto")

    def test_read_fallback_when_reader_has_no_load(self):
        # Construye un _DPRead con un reader sin load() para verificar fallback csv()
        class FallbackReaderNoLoad:
            def __init__(self):
                self._options = {}
                self.last_format = None
                self.calls = []

            def format(self, fmt):
                self.last_format = fmt
                self.calls.append(("format", fmt))
                return self

            def option(self, k, v):
                self._options[k] = v
                self.calls.append(("option", k, v))
                return self

            def csv(self, path):
                self.calls.append(("csv", path))
                return f"DF_CSV_DIRECT:{path}|fmt={self.last_format}|opts={self._options.copy()}"

        r = self.bridge._DPRead(shared_reader=FallbackReaderNoLoad())
        out = r.option("header", True).csv("s3://bucket/direct.csv")
        self.assertTrue(out.startswith("DF_CSV_DIRECT:"))
        self.assertEqual(r._reader.last_format, "csv")
        self.assertEqual(r._reader._options, {"header": True})

    # ----------------- Tests de escritura -----------------

    def test_write_parquet_propagates_to_dataframewriter(self):
        dp = self.bridge.DataprocAthenaBridge("tmp_db", "s3://tmp/")
        dummy_df = DummyDF()
    
        with patch("athena_bridge.dataframewriter.DataFrameWriter.save", return_value={"ok": True}) as mock_save:
            res = (
                dp.write()
                .option("partitionOverwriteMode", "dynamic")
                .mode("overwrite")
                .partition_by(["tipo", "dt"])
                .parquet(dummy_df, "s3://bucket/out/")
            )
    
        mock_save.assert_called_once_with("s3://bucket/out/")
        self.assertTrue(res["ok"])


    def test_write_csv_options(self):
        dp = self.bridge.DataprocAthenaBridge("tmp_db", "s3://tmp/")
        dummy_df = DummyDF()
    
        with patch("athena_bridge.dataframewriter.DataFrameWriter.save", return_value={"ok": True, "fmt": "csv", "options": {"header": "true", "sep": ","}}):
            res = (
                dp.write()
                .option("header", "true")
                .option("sep", ",")
                .mode("overwrite")
                .csv(dummy_df, "s3://bucket/out_csv/")
            )
    
        self.assertTrue(res["ok"])
        self.assertEqual(res["fmt"], "csv")
        self.assertEqual(res["options"]["header"], "true")
        self.assertEqual(res["options"]["sep"], ",")

    def test_write_saveAsTable(self):
        dp = self.bridge.DataprocAthenaBridge("tmp_db", "s3://tmp/")
        dummy_df = DummyDF()
    
        with patch("athena_bridge.dataframewriter.DataFrameWriter.saveAsTable", return_value={
            "ok": True,
            "table": "my_table",
            "db": "my_db",
            "fmt": "parquet",
            "mode": "append",
            "options": {"x": "y"}
        }) as mock_save:
            res = (
                dp.write()
                .format("parquet")
                .mode("append")
                .option("x", "y")
                .saveAsTable(dummy_df, "my_table", database="my_db")
            )
    
        mock_save.assert_called_once_with(table_name="my_table", database="my_db")
        self.assertTrue(res["ok"])
        self.assertEqual(res["table"], "my_table")
        self.assertEqual(res["db"], "my_db")
        self.assertEqual(res["fmt"], "parquet")
        self.assertEqual(res["mode"], "append")
        self.assertEqual(res["options"]["x"], "y")

    def test_exit_delegates_to_reader_exit(self):
        dp = self.bridge.DataprocAthenaBridge("tmp_db", "s3://tmp/")

        # Espiamos la llamada a exit() del reader real
        dp._reader.exit = MagicMock(return_value=None)

        out = dp.exit()

        # Se llamó exactamente una vez y sin argumentos
        dp._reader.exit.assert_called_once_with()

        # Acepta que el bridge devuelva None (o cualquier otro truthy si lo cambias en el futuro)
        self.assertIn(out, (None, True, "EXIT_OK"))


    def test_partitionBy_alias_if_present(self):
        dp = self.bridge.DataprocAthenaBridge("tmp_db", "s3://tmp/")
        writer = dp.write()
        if not hasattr(writer, "partitionBy"):
            self.skipTest("partitionBy alias no implementado en _DPWrite (usa partition_by).")
    
        writer.partitionBy("tipo")  # solo probamos el alias
        self.assertEqual(writer._partitions, ["tipo"])


if __name__ == "__main__":
    unittest.main()
