# This code is based on code from Apache Spark under the license found in the LICENSE file located in the root folder.

import awswrangler as wr
import uuid
import boto3
from botocore.exceptions import ClientError

class DataFrameWriter:
    def __init__(self, df):
        self.df = df
        self._format = "parquet"
        self._mode = "overwrite"
        self._database = None
        self._options = {}  # Aquí almacenaremos las opciones como 'sep', 'header', etc.
        self._partitioned_by = None

    def format(self, fmt):
        self._format = fmt.lower()
        return self

    def mode(self, mode):
        self._mode = mode.lower()
        return self

    def option(self, key, value):
        self._options[key.lower()] = value
        return self

    def partitionBy(self, *cols):
        self._partitioned_by = list(cols)
        return self

    def save(self, path: str):
        if not path.startswith("s3://"):
            raise Exception(f"The destination path ({path}) must be an S3 bucket (s3://...)")

        query = self.df._build_query()
        path = path.rstrip("/") + "/"

        try:
            if not self._mode:
                # Si no hay modo y el path existe, lanzar error explícito (como PySpark)
                if wr.s3.does_object_exist(path):
                    raise Exception(
                        f"The path {path} already exists. Use .mode('overwrite') or .mode('append').")
                mode = "error_if_exists"
            else:
                mode = self._mode

            dynamic = self._options.get("partitionOverwriteMode", "static") == "dynamic"
            is_partitioned = bool(self._partitioned_by)

            # Pasamos las opciones a minusculas, particionOverwriteMode estaba dando problemas porque se almacena
            # como partitionoverwritemode. Asi que pasamos a minusculas y luego comprobamos con minusculas
            self._options = {k.lower(): v for k, v in self._options.items()}

            dynamic = self._options.get("partitionoverwritemode", "static").lower() == "dynamic"
            is_partitioned = bool(self._partitioned_by)

            # Determinar ruta de escritura
            if mode == "append":
                # Escribir en subcarpeta temporal única
                unload_path = f"{path}__tmp_append_{uuid.uuid4().hex[:6]}/"
            elif mode == "overwrite" and dynamic and is_partitioned:
                unload_path = f"{path}__tmp_dynamic_overwrite_{uuid.uuid4().hex[:6]}/"
            else:
                # Overwrite total: borrar antes
                wr.s3.delete_objects(path)
                unload_path = path

            # Construir argumentos para UNLOAD
            unload_args = {
                "sql": query,
                "path": unload_path,
                "database": self._database or self.df.database,
                "file_format": self._format,
                "partitioned_by": self._partitioned_by,
                "workgroup": self.df.reader._workgroup
            }

            if self._format.lower() in ("csv", "textfile"):
                if "header" in self._options:
                    print("⚠️ 'header' no es compatible con UNLOAD y será ignorado.")
                unload_args["file_format"] = "TEXTFILE"
                unload_args["field_delimiter"] = self._options.get("sep", ",")

            meta_data = wr.athena.unload(**unload_args)
            self.df.reader._data_scanned += meta_data.raw_payload['Statistics']['DataScannedInBytes']

            # Si hay que mover archivos (append o dynamic overwrite)
            if (mode == "append") or (mode == "overwrite" and dynamic and is_partitioned):
                s3 = boto3.resource("s3")
                bucket = path.replace("s3://", "").split("/")[0]
                prefix_final = "/".join(path.replace("s3://", "").split("/")[1:])
                prefix_temp = "/".join(unload_path.replace("s3://", "").split("/")[1:])

                for obj in s3.Bucket(bucket).objects.filter(Prefix=prefix_temp):
                    src = {"Bucket": bucket, "Key": obj.key}
                    dest_key = obj.key.replace(prefix_temp, prefix_final, 1)
                    s3.Object(bucket, dest_key).copy_from(CopySource=src)

                # Eliminar temporales
                wr.s3.delete_objects(unload_path)

            return f"Saved to {path} as {self._format.upper()} ({mode}) using UNLOAD"

        except Exception as e:
            raise Exception(
                f"An unexpected error occurred while saving the DataFrame: {e}"
            ) from e

    def saveAsTable(self, table_name: str, database: str = None):
        query = self.df._build_query()
        db = database or self.df.database

        if self._mode == "overwrite":
            sql = f"CREATE OR REPLACE TABLE {db}.{table_name} AS {query}"
        elif self._mode == "append":
            sql = f"INSERT INTO {db}.{table_name} {query}"
        else:
            raise ValueError("Modo no soportado: usa 'overwrite' o 'append'")

        return self.df._execute(sql)
