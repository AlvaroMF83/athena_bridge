# dataproc_athena_bridge.py
# -*- coding: utf-8 -*-
from typing import Any, Dict, List

from athena_bridge.athenareader import AthenaReader           # requiere database_tmp y path_tmp
from athena_bridge.dataframewriter import DataFrameWriter     # tu writer existente


class _DPRead:
    """
    Facade de lectura que reutiliza SIEMPRE el mismo AthenaReader compartido.
    Para evitar “sangrado” de opciones entre lecturas, limpiamos _options
    antes de aplicar las nuevas.
    """
    def __init__(self, shared_reader: AthenaReader):
        self._reader = shared_reader
        self._opts: Dict[str, Any] = {}
        self._fmt: str | None = None

    def _reset_reader_opts(self):
        # Limpiamos opciones previas para que cada read() sea independiente
        if hasattr(self._reader, "_options"):
            self._reader._options = {}

    def option(self, key: str, value: Any):
        self._opts[key] = value
        # aplicamos al reader también (se hará un reset al ejecutar el load)
        return self

    def options(self, **kwargs):
        for k, v in kwargs.items():
            self.option(k, v)
        return self

    def format(self, fmt: str):
        self._fmt = fmt.lower()
        return self

    # ----- atajos estilo dataproc -----
    def parquet(self, path: str):
        return self.format("parquet")._load(path)

    def csv(self, path: str):
        return self.format("csv")._load(path)

    def json(self, path: str):
        return self.format("json")._load(path)

    def table(self, db_table: str):
        self._reset_reader_opts()
        if "." not in db_table:
            raise ValueError("Debe indicarse 'database.table'")
        db, tbl = db_table.split(".", 1)
        self._reader.database(db)
        return self._reader.table(tbl)

    def _load(self, path: str):
        self._reset_reader_opts()
        if self._fmt:
            self._reader.format(self._fmt)
        # aplicar options acumuladas a reader
        for k, v in self._opts.items():
            self._reader.option(k, v)
        # delegar en tu reader real
        if hasattr(self._reader, "load"):
            return self._reader.load(path)
        # (fallbacks si tu reader expone csv/parquet/json directos)
        if self._fmt == "csv" and hasattr(self._reader, "csv"):
            return self._reader.csv(path)
        if self._fmt == "parquet" and hasattr(self._reader, "parquet"):
            return self._reader.parquet(path)
        if self._fmt == "json" and hasattr(self._reader, "json"):
            return self._reader.json(path)
        raise NotImplementedError("AthenaReader no expone load()/csv()/parquet()/json() compatibles.")


class _DPWrite:
    def __init__(self):
        self._opts: Dict[str, Any] = {}
        self._mode: str | None = None
        self._partitions: List[str] = []
        self._fmt: str | None = None

    def option(self, key: str, value: Any):
        self._opts[key] = value
        return self

    def options(self, **kwargs):
        for k, v in kwargs.items():
            self.option(k, v)
        return self

    def mode(self, m: str):
        self._mode = m

        return self

    def _normalize_partitions(self, *cols):
        parts = []
        for col in cols:
            if isinstance(col, (list, tuple, set)):
                parts.extend(str(x) for x in col)
            else:
                parts.append(str(col))
        return parts

    def partition_by(self, *cols):
        self._partitions = self._normalize_partitions(*cols)
        return self

    partitionBy = partition_by

    def format(self, fmt: str):
        self._fmt = fmt.lower()
        return self

    # ----- atajos estilo dataproc -----
    def parquet(self, df, path: str):
        return self._save(df, path, fmt="parquet")

    def csv(self, df, path: str):
        return self._save(df, path, fmt="csv")

    def saveAsTable(self, df, table_name: str, database=None):
        w = DataFrameWriter(df)
        if self._fmt:
            w.format(self._fmt)
        if self._mode:
            w.mode(self._mode)
        for k, v in self._opts.items():
            w.option(k, v)
        return w.saveAsTable(table_name=table_name, database=database)

    def _save(self, df, path: str, fmt: str):
        # Delegamos TODA la semántica en tu writer existente
        w = DataFrameWriter(df)
        w.format(fmt)
        if self._mode:
            w.mode(self._mode)
        for k, v in self._opts.items():
            w.option(k, v)
        if self._partitions:
            w.partitionBy(*self._partitions)
        return w.save(path)


class DataprocAthenaBridge:
    """
    Bridge compatible con 'dataproc' que mantiene un AthenaReader único
    (construido con database_tmp y path_tmp) y expone .exit() para limpiar
    temporales reutilizando el exit() del reader.
    """
    def __init__(self, database_tmp: str, path_tmp: str):
        # Instanciamos UNA sola vez tu AthenaReader con la config obligatoria
        self._reader = AthenaReader(database_tmp=database_tmp, path_tmp=path_tmp)

    def read(self) -> _DPRead:
        # Devolvemos un facade que usa SIEMPRE el mismo reader compartido
        return _DPRead(self._reader)

    def write(self) -> _DPWrite:
        return _DPWrite()

    def exit(self):
        """
        Limpia tablas y ficheros temporales creados durante la sesión.
        """
        # Simplemente delega en el exit() de tu AthenaReader
        return self._reader.exit()
