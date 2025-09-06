# spark_compat.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Any, Dict, Optional

from athena_bridge.dataproc_athena_bridge import DataprocAthenaBridge, _DPRead  # tu módulo pegado arriba
from athena_bridge.athenareader import AthenaReader


class _SparkSessionBuilder:
    """
    Replica mínima de SparkSession.builder:
      SparkSession.builder \
        .config("athena.database_tmp", "...") \
        .config("athena.path_tmp", "...") \
        .config("athena.workgroup", "...") \
        .getOrCreate()
    También permite atajos:
      .appName() (ignorado)
      .master() (ignorado)
    """
    def __init__(self):
        self._conf: Dict[str, Any] = {}

    def config(self, key: str, value: Any) -> "_SparkSessionBuilder":
        self._conf[key] = value
        return self

    # No-op para compatibilidad
    def appName(self, _: str) -> "_SparkSessionBuilder":
        return self

    def master(self, _: str) -> "_SparkSessionBuilder":
        return self

    def getOrCreate(self) -> "SparkSession":
        # Admite nombres comunes de conf estilo spark.* y atajos
        db_tmp = (
            self._conf.get("athena.database_tmp")
            or self._conf.get("spark.athena.database_tmp")
            or self._conf.get("spark.sql.athena.database_tmp")
        )
        path_tmp = (
            self._conf.get("athena.path_tmp")
            or self._conf.get("spark.athena.path_tmp")
            or self._conf.get("spark.sql.athena.path_tmp")
        )
        workgroup = (
            self._conf.get("athena.workgroup")
            or self._conf.get("spark.athena.workgroup")
            or self._conf.get("spark.sql.athena.workgroup")
        )

        if not db_tmp or not path_tmp or not workgroup:
            raise ValueError(
                "Faltan configs obligatorias: athena.database_tmp, athena.path_tmp, athena.workgroup"
            )

        bridge = DataprocAthenaBridge(
            database_tmp=str(db_tmp),
            path_tmp=str(path_tmp),
            workgroup=str(workgroup),
        )
        return SparkSession(_bridge=bridge)


class SparkSession:
    """
    Shim mínimo de SparkSession para *lecturas* con sintaxis PySpark:
      spark.read.format(...).option(...).load(...)
      spark.read.parquet/csv/json(...)
      spark.read.table("db.tbl")
      spark.table("db.tbl")
      spark.sql("select ...")
      spark.stop()
    """
    builder = _SparkSessionBuilder()

    def __init__(self, _bridge: DataprocAthenaBridge):
        self._bridge = _bridge
        self._reader: AthenaReader = _bridge._reader   # mismo reader compartido del bridge
        self.read: _DPRead = _DPRead(self._reader)     # façade con API estilo PySpark

    # --------- Compat helpers estilo PySpark ----------
    def table(self, db_table: str):
        """Equivalente a spark.read.table('db.tbl')."""
        return self.read.table(db_table)

    def sql(self, query: str):
        """
        Ejecuta SQL directamente sobre Athena usando el reader compartido.
        Debe devolver tu DataFrame athena-compat.
        """
        if not hasattr(self._reader, "sql"):
            raise NotImplementedError("AthenaReader no expone sql(query). Añade .sql() en tu reader.")
        return self._reader.sql(query)

    def stop(self):
        """Compat con SparkSession.stop(); limpia temporales (delegando en bridge.exit())."""
        try:
            self._bridge.exit()
        except Exception:
            # No reventar el flujo si no hay temporales
            pass

    # --------- Acceso a conf opcional (lectura simple) ----------
    @property
    def conf(self) -> Dict[str, Any]:
        return {
            "athena.database_tmp": getattr(self._reader, "database_tmp", None),
            "athena.path_tmp": getattr(self._reader, "path_tmp", None),
            "athena.workgroup": getattr(self._reader, "workgroup", None),
        }


# --------- Atajo estilo pyspark.sql import SparkSession ----------
def get_spark(database_tmp: str, path_tmp: str, workgroup: str) -> SparkSession:
    """
    Atajo cómodo si no quieres usar .builder:
        spark = get_spark(db_tmp, path_tmp, workgroup)
    """
    bridge = DataprocAthenaBridge(database_tmp=database_tmp, path_tmp=path_tmp, workgroup=workgroup)
    return SparkSession(_bridge=bridge)
