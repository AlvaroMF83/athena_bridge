# This code is based on code from Apache Spark under the license found in the LICENSE file located in the root folder.

import awswrangler as wr
from athena_bridge.dataframe import DataFrame
import uuid
import pandas as pd


class AthenaReader:

    # _TEMPORARY_TABLES = set()

    def __init__(self, database_tmp: str, path_tmp: str, workgroup: str):
        self._format = "parquet"
        self._database = None
        self._options = {}
        self._database_tmp = database_tmp
        self._path_tmp = path_tmp
        self._workgroup = workgroup
        self._temporary_tables = set()
        self._temporary_files = set()
        self._data_scanned = 0

    def format(self, fmt: str):
        self._format = fmt.lower()
        return self

    def database(self, db: str):
        self._database = db
        return self

    def option(self, key: str, value):
        self._options[key] = value
        return self

    @property
    def database_tmp(self):
        return self._database_tmp

    @property
    def path_tmp(self):
        return self._path_tmp

    @property
    def workgroup(self):
        return self._workgroup

    @property
    def data_scanned(self):
        return self._data_scanned

    def _register_temp_table(self, database: str, table: str):
        self._temporary_tables.add((database, table))

    def _register_temp_path(self, path: str):
        self._temporary_files.add(path.rstrip("/"))

    def load(self, path: str):
        table_name = f"temp_{uuid.uuid4().hex[:8]}"

        if self._format == "parquet":
            wr.s3.store_parquet_metadata(
                path=path,
                database=self._database_tmp,
                table=table_name,
                dataset=True,
                mode="overwrite"
            )

        elif self._format == "csv":
            sep = self._options.get("sep", ",")
            header = self._options.get("header", True)
            encoding = self._options.get("encoding", "utf-8")
            user_schema = self._options.get("schema", None)

            if not header and not user_schema:
                raise ValueError("Debe proporcionarse un schema explícito si header=False.")

            if user_schema:
                columns_types = user_schema  # ✅ Usa lo que el usuario ha dado
            else:
                # Solo inferir si no se pasó un schema
                df_sample = wr.s3.read_csv(
                    path,
                    chunksize=1000,
                    sep=sep,
                    header=0 if header else None,
                    encoding=encoding
                ).__next__()
                columns_types = self.infer_columns_types_from_pandas(df_sample)

            wr.catalog.create_csv_table(
                database=self._database_tmp,
                table=table_name,
                path=path,
                columns_types=columns_types,
                sep=sep,
                mode="overwrite",
                table_type="EXTERNAL_TABLE",
                skip_header_line_count=1 if header else 0
            )

        elif self._format == "json":
            df_sample = wr.s3.read_json(path, chunksize=50).__next__()
            columns_types = self.infer_columns_types_from_pandas(df_sample)

            wr.catalog.create_json_table(
                database=self._database_tmp,
                table=table_name,
                path=path,
                columns_types=columns_types,
                mode="overwrite",
                table_type="EXTERNAL_TABLE"
            )
        else:
            raise ValueError(f"Formato '{self._format}' no soportado.")

        self._temporary_tables.add((self._database_tmp, table_name))
        return DataFrame(database=self._database_tmp, table=table_name, reader=self)

    def table(self, table_name: str):
        if not self._database:
            raise ValueError("Debes especificar una base de datos con .database(...) antes de usar .table()")
        return DataFrame(database=self._database, table=table_name, reader=self)

    # Métodos directos como en PySpark:
    def parquet(self, path: str):
        return self.format("parquet").load(path)

    def csv(self, path: str, sep: str = ",", header: bool = True, encoding: str = "utf-8", schema: dict = None):
        reader = (
            self.format("csv")
            .option("sep", sep)
            .option("header", header)
            .option("encoding", encoding)
        )

        if schema:
            reader = reader.option("schema", schema)

        return reader.load(path)

    def json(self, path: str):
        return self.format("json").load(path)

    def text(self, path: str):
        raise NotImplementedError("Athena no soporta archivos .txt sin SerDe personalizado")

    def exit(self):
        import awswrangler as wr

        for db, table in self._temporary_tables:
            try:
                wr.catalog.delete_table_if_exists(database=db, table=table)
                print(f"✔️ Eliminada tabla temporal: {db}.{table}")
            except Exception as e:
                print(f"⚠️ No se pudo eliminar {db}.{table}: {e}")

        for path in self._temporary_files:
            try:
                wr.s3.delete_objects(path)
                print(f"🧹 Borrado S3 temporal: {path}")
            except Exception as e:
                print(f"⚠️ No se pudo borrar {path}: {e}")

        self._temporary_tables.clear()
        self._temporary_files.clear()
        print("✅ Sesión finalizada y temporales eliminados.")

    def infer_columns_types_from_pandas(self, df: pd.DataFrame) -> dict:
        type_mapping = {
            "int64": "bigint",
            "Int64": "bigint",
            "float64": "double",
            "bool": "boolean",
            "boolean": "boolean",
            "datetime64[ns]": "timestamp",
            "object": "string",
            "category": "string"
        }

        columns_types = {}

        for col, dtype in df.dtypes.items():
            dtype_str = str(dtype)
            glue_type = type_mapping.get(dtype_str)
            if glue_type is None:
                raise ValueError(f"Tipo de dato no soportado para la columna '{col}': {dtype_str}")
            columns_types[col] = glue_type

        return columns_types
