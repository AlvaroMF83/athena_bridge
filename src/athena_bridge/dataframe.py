# This code is based on code from Apache Spark under the license found in the LICENSE file located in the root folder.

from athena_bridge.functions import Column
import awswrangler as wr
import boto3
import time
import io
from collections import OrderedDict
from botocore.exceptions import ClientError
import awswrangler.exceptions

from athena_bridge.dataframewriter import DataFrameWriter

import pandas as pd

class DataFrame:
    _global_alias_counter = 0  # clase-level

    def __init__(self, database: str, table: str, reader):
        self.database = database
        self.table = table
        self.reader = reader
        self.alias_counter = 0
        self.steps = []
        self.current_alias = self._get_next_alias()

        try:
            table_info = wr.catalog.table(database=database, table=table)
            # Creamos un diccionario {col_name: type} desde el esquema de Glue
            self.schema = OrderedDict(
                (row["Column Name"], row["Type"]) for _, row in table_info.iterrows()
            )
        except (ClientError, awswrangler.exceptions.ResourceDoesNotExist) as e:            
            raise Exception(
                f"Could not retrieve schema for table '{table}' in database '{database}'."
                f"Please check if the table exists and you have permissions."
            ) from e

        base_query = f"SELECT * FROM {self.database}.{self.table}"
        self.steps.append((self.current_alias, base_query))

    def _get_next_alias(self):
        alias = f"df_{DataFrame._global_alias_counter}"
        DataFrame._global_alias_counter += 1
        return alias

    # def _build_query(self, final_query: str = None):
    #    with_clauses = [f"{alias} AS ({query})" for alias, query in self.steps]
    #   base = f"WITH {', '.join(with_clauses)}"
    #    final_alias = self.steps[-1][0]
    #    final_select = final_query or f"SELECT * FROM {final_alias}"
    #    return f"{base} {final_select}"

    def _get_sagemaker_user(self):
        try:
            # Esto funciona en notebooks de SageMaker Studio
            with open("/opt/ml/metadata/resource-metadata.json") as f:
                import json
                metadata = json.load(f)
                return metadata.get("UserProfileName", "desconocido")
        except Exception:
            return "desconocido"

    def _build_query(self, final_query: str = None):
        steps = self.steps.copy()

        # Añadir paso para alias si existe
        if hasattr(self, "_df_alias"):
            alias = self._df_alias
            last_step = steps[-1][0]
            if alias not in [a for a, _ in steps]:
                steps.append((alias, f"SELECT * FROM {last_step}"))
            final_alias = alias
        else:
            final_alias = steps[-1][0]

        with_clauses = [f"{alias} AS ({query})" for alias, query in steps]
        final_select = final_query or f"SELECT * FROM {final_alias}"

        # Añadir cabecera
        username = self._get_sagemaker_user()
        version = "AthenaBridge v1.0.6"
        comment = f"-- {version} | usuario: {username}"

        return f"{comment}\nWITH {', '.join(with_clauses)} {final_select}"

        return f"WITH {', '.join(with_clauses)} {final_select}"

    # def _execute(self, query: str) -> pd.DataFrame:
    #    df = wr.athena.read_sql_query(query, database=self.database, workgroup="sandbox", ctas_approach=False)
    #    datos_escaneados = df.query_metadata["Statistics"]["DataScannedInBytes"]
    #    self.reader._data_scanned += datos_escaneados
    #    return df

    def athena_to_pandas_type(self, athena_type: str) -> str:
        mapping = {
            "int": "Int64",          # soporte para nullables
            "integer": "Int64",
            "bigint": "Int64",
            "double": "float64",
            "float": "float64",
            "boolean": "bool",
            "string": "string",
            "varchar": "string",
            "char": "string",
            "date": "string",        # o pd.Datetime if parse_dates
            "timestamp": "string",   # mejor tratarlo como string y convertir luego si hace falta
        }
        return mapping.get(athena_type.lower(), "string")  # default a string

    def _execute(self, query: str) -> pd.DataFrame:
        athena = boto3.client("athena")
        s3 = boto3.client("s3")
        query_execution_id = None

        try:
            # Ejecutar la consulta
            response = athena.start_query_execution(
                QueryString=query,
                QueryExecutionContext={"Database": self.database},
                WorkGroup=self.reader._workgroup
            )

            query_execution_id = response["QueryExecutionId"]

            # Esperar a que termine la ejecución
            while True:
                result = athena.get_query_execution(QueryExecutionId=query_execution_id)
                state = result["QueryExecution"]["Status"]["State"]
                if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
                    break
                time.sleep(1)

            if state != "SUCCEEDED":
                reason = result["QueryExecution"]["Status"].get("StateChangeReason", "Unknown reason")
                raise Exception(f"Query failed with state '{state}': {reason} | "
                                f"Database: {self.database} | Query ID: {query_execution_id}")

            # Extraer estadísticas
            stats = result["QueryExecution"]["Statistics"]
            data_scanned = stats.get("DataScannedInBytes", 0)
            self.reader._data_scanned += data_scanned

            # Obtener la ubicación del resultado en S3
            output_location = result["QueryExecution"]["ResultConfiguration"]["OutputLocation"]
            bucket, key = output_location.replace("s3://", "").split("/", 1)

            # Descargar el archivo CSV desde S3
            response = s3.get_object(Bucket=bucket, Key=key)
            csv_bytes = response["Body"].read()

            # Mapear tipos del esquema
            dtype_map = {
                col: self.athena_to_pandas_type(tp)
                for col, tp in self.schema.items()
            }

            df = pd.read_csv(io.BytesIO(csv_bytes), dtype=dtype_map)

            return df
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            raise Exception(f"An AWS API error occurred during query execution: {error_code} - {error_message} | "
                f"Database: {self.database} | Query ID: {query_execution_id}") from e
        except Exception as e:
            # Catch-all for other unexpected errors like pd.read_csv issues
            raise Exception( f"An unexpected error occurred during query execution: {e} | "
                f"Database: {self.database} | Query ID: {query_execution_id}") from e
            

    def _check_columns_exist(self, *cols):
        for col in cols:
            if col is None or not isinstance(col, str):
                continue

            if col.endswith(".*"):
                continue  # alias.* es válido

            if "." in col:
                # No validar columnas con alias (ej: a.employee_id) directamente contra schema
                continue

            if col not in self.schema:
                raise ValueError(
                    f"La columna '{col}' no está disponible en el DataFrame actual. "
                    f"Columnas disponibles: {list(self.schema.keys())}"
                )

    ''' Version con alias y con columns, lo quito porque no funciona bien alias y ademas dejamos de usar
    columns
    def __getattr__(self, column_name: str):
        from athena_bridge.functions import col  # o el módulo donde tengas col

        columns = self.__dict__.get("_columns", [])

        if column_name in columns:
            alias = self.__dict__.get("_df_alias", None)
            full_col = f"{alias}.{column_name}" if alias else column_name
            return col(full_col)

        raise AttributeError(f"'DataFrame' object has no attribute '{column_name}'")
    '''

    def __getattr__(self, column_name):
        from athena_bridge.functions import col

        if column_name.startswith("_"):
            # Evita conflicto con atributos internos
            raise AttributeError(f"'DataFrame' object has no attribute '{column_name}'")

        if column_name in self.schema:
            return col(column_name)  # ← usa tu función col() para devolver un Column

        raise AttributeError(f"'DataFrame' object has no attribute '{column_name}'")

    def copy(self):
        new_df = DataFrame.__new__(DataFrame)
        new_df.database = self.database
        new_df.table = self.table
        new_df.reader = self.reader
        new_df.schema = self.schema.copy()
        new_df.steps = self.steps.copy()
        # new_df.alias_counter = self.alias_counter
        new_df.current_alias = self.current_alias

        # Clonar metadata de agrupación si existe
        new_df._group_by_columns = getattr(self, "_group_by_columns", None)
        new_df._group_by_select_exprs = getattr(self, "_group_by_select_exprs", None)
        new_df._group_by_schema = getattr(self, "_group_by_schema", None)
        return new_df

    # PROPIEDADES

    @property
    def dtypes(self):
        # Devuelve todos los pares (columna, tipo) del schema
        return list(self.schema.items())

    @property
    def columns(self):
        return list(self.schema.keys())

    @property
    def write(self):
        return DataFrameWriter(self)

    def printSchema(self):
        print("root")
        for col, dtype in self.schema.items():
            print(f" |-- {col}: {dtype} (nullable = true)")

    def describe(self, *cols):
        df = self.copy()

        # Si no se pasan columnas, filtrar las numéricas
        if not cols:
            numeric_types = ("int", "integer", "bigint", "float", "double", "decimal")
            cols = [
                col for col, dtype in df.schema.items()
                if any(dtype.lower().startswith(t) for t in numeric_types)
            ]

        if not cols:
            raise ValueError("No hay columnas numéricas para describir.")

        df._check_columns_exist(*cols)

        # Crear SELECT con agregaciones
        agg_exprs = []
        for col_name in cols:
            agg_exprs.append(f"CAST(COUNT({col_name}) AS DOUBLE) AS {col_name}_count")
            agg_exprs.append(f"AVG({col_name}) AS {col_name}_mean")
            agg_exprs.append(f"STDDEV_POP({col_name}) AS {col_name}_stddev")
            agg_exprs.append(f"MIN({col_name}) AS {col_name}_min")
            agg_exprs.append(f"MAX({col_name}) AS {col_name}_max")

        final_query = f"SELECT {', '.join(agg_exprs)} FROM {df.current_alias}"
        query = df._build_query(final_query)

        # Ejecutamos la query y transformamos a formato tipo PySpark
        result = df._execute(query)

        # Transponer y adaptar el resultado a estilo describe()
        stats = ["count", "mean", "stddev", "min", "max"]
        data = []

        for stat in stats:
            row = [stat]
            for col in cols:
                value = result.iloc[0][f"{col}_{stat}"]
                row.append(value)
            data.append(row)

        columns = ["summary"] + list(cols)
        import pandas as pd
        return pd.DataFrame(data, columns=columns)

    # TO DO: De momento no se ha conseguido el funcionamiento deseado, por lo que se desactiva
    # Es una funcionalidad secundaria.
    # hay que analizar bien como hacerlo con clausulas with antes de implementarlo
    # se queda por ahi codigo con _df_alias, pero en principio no molesta

    # def alias(self, alias_name: str):
    #    df = self.copy()
    #    df._df_alias = alias_name
    #    return df

    # TRANSFORMACIONES

    def select(self, *cols):
        from athena_bridge.functions import col  # Import local para convertir strings a Column

        df = self.copy()

        # Detectar si el usuario pasó una lista como único argumento
        if len(cols) == 1 and isinstance(cols[0], (list, tuple)):
            cols = cols[0]

        expressions = []
        new_schema = OrderedDict()

        for expr in cols:
            if isinstance(expr, str):
                expr = col(expr)

            if not isinstance(expr, Column):
                raise TypeError(f"Se esperaba una columna (str o Column), se recibió: {type(expr)}")

            # Validar columnas referenciadas
            for ref_col in expr.referenced_columns:
                df._check_columns_exist(ref_col)

            # Agregar expresión SQL y actualizar nuevo schema
            expressions.append(expr.to_sql())

            output_name = expr.alias_name or expr.expr
            # inferred_type = getattr(expr, "_data_type", "string")
            # if expr.data_type is not None:
            #    inferred_type = expr.data_type
            inferred_type = "string"
            if len(expr.referenced_columns) == 1:
                ref = expr.referenced_columns[0]
                inferred_type = self.schema.get(ref, "string")
            else:
                inferred_type = "string"

            new_schema[output_name] = inferred_type

        new_alias = df._get_next_alias()
        prev_alias = df.steps[-1][0]
        query = f"SELECT {', '.join(expressions)} FROM {prev_alias}"

        df.steps.append((new_alias, query))
        df.current_alias = new_alias
        df.schema = new_schema

        return df

    def drop(self, *cols):
        if not cols:
            raise ValueError("drop() requiere al menos un nombre de columna")

        # Verificar que no se haya pasado una lista como único argumento
        if len(cols) == 1 and isinstance(cols[0], (list, tuple, set)):
            raise TypeError("drop() espera uno o más nombres de columnas como argumentos separados, no una lista")

        df = self.copy()

        for col_name in cols:
            if not isinstance(col_name, str):
                raise TypeError(f"Se esperaba un string como nombre de columna, se recibió: {type(col_name)}")

            df._check_columns_exist(col_name)

        new_schema = OrderedDict((k, v) for k, v in df.schema.items() if k not in cols)
        expressions = list(new_schema.keys())

        new_alias = df._get_next_alias()
        prev_alias = df.steps[-1][0]
        query = f"SELECT {', '.join(expressions)} FROM {prev_alias}"

        df.steps.append((new_alias, query))
        df.current_alias = new_alias
        df.schema = new_schema

        return df

    def filter(self, condition):
        df = self.copy()

        if isinstance(condition, str):
            cond_str = condition
        elif isinstance(condition, Column):
            for ref_col in condition.referenced_columns:
                df._check_columns_exist(ref_col)
            cond_str = condition.to_sql()
        else:
            raise TypeError(f"Se esperaba una condición como str o Column, pero se recibió: {type(condition)}")

        prev_alias = df.steps[-1][0]
        new_alias = df._get_next_alias()
        sql = f"SELECT * FROM {prev_alias} WHERE {cond_str}"
        df.steps.append((new_alias, sql))
        df.current_alias = new_alias
        return df

    where = filter  # alias

    def distinct(self):
        df = self.copy()
        prev_alias = df.steps[-1][0]
        new_alias = df._get_next_alias()
        query = f"SELECT DISTINCT * FROM {prev_alias}"
        df.steps.append((new_alias, query))
        df.current_alias = new_alias
        return df

    def orderBy(self, *cols, ascending=True):
        df = self.copy()

        # Convertir a lista si pasan una sola lista como argumento
        if len(cols) == 1 and isinstance(cols[0], (list, tuple)):
            cols = cols[0]

        # Normalizar ascending
        if isinstance(ascending, bool):
            ascending = [ascending] * len(cols)
        elif isinstance(ascending, list) and len(ascending) != len(cols):
            raise ValueError("La longitud de 'ascending' debe coincidir con el número de columnas")

        order_exprs = []

        for i, expr in enumerate(cols):
            asc_flag = ascending[i]
            if isinstance(expr, str):
                order_exprs.append(f"{expr} {'ASC' if asc_flag else 'DESC'}")
            elif isinstance(expr, Column):
                expr_sql = expr.to_sql()
                if "ASC" in expr_sql or "DESC" in expr_sql:
                    # Ya lleva orden, lo usamos tal cual
                    order_exprs.append(expr_sql)
                else:
                    order_exprs.append(f"{expr_sql} {'ASC' if asc_flag else 'DESC'}")
            else:
                raise TypeError("orderBy/sort espera strings o objetos Column")

        prev_alias = df.steps[-1][0]
        new_alias = df._get_next_alias()
        query = f"SELECT * FROM {prev_alias} ORDER BY {', '.join(order_exprs)}"
        df.steps.append((new_alias, query))
        df.current_alias = new_alias
        return df

    def sort(self, *cols, ascending=True):
        return self.orderBy(*cols, ascending=ascending)

    def groupBy(self, *cols):
        from athena_bridge.functions import col

        df = self.copy()

        # Aplanar si se pasa una lista
        if len(cols) == 1 and isinstance(cols[0], (list, tuple)):
            cols = cols[0]

        group_by_exprs = []       # Para GROUP BY
        group_by_selects = []     # Para SELECT
        group_by_schema = OrderedDict()  # Para schema final
        for c in cols:
            if isinstance(c, str):
                df._check_columns_exist(c)
                expr = col(c)
                sql_expr = expr.to_sql()
                group_by_exprs.append(sql_expr)
                group_by_selects.append(f"{sql_expr} AS {c}")
                group_by_schema[c] = self.schema.get(c, "unknown")

            elif isinstance(c, Column):
                # Validación de columnas referenciadas
                if c.referenced_columns:
                    df._check_columns_exist(*c.referenced_columns)

                sql_expr = c.to_sql_without_alias()
                group_by_exprs.append(sql_expr)

                if c._alias:  # ✅ SOLO si hay alias definido
                    group_by_selects.append(f"{sql_expr} AS {c._alias}")
                    group_by_schema[c._alias] = c._data_type or "unknown"
                else:
                    group_by_selects.append(sql_expr)
                    group_by_schema[sql_expr] = c._data_type or "unknown"

            else:
                raise TypeError("groupBy() solo acepta strings o objetos Column")

        df._group_by_columns = group_by_exprs
        df._group_by_select_exprs = group_by_selects
        df._group_by_schema = group_by_schema

        return df

    groupby = groupBy  # alias

    def agg(self, *exprs):
        df = self.copy()

        select_exprs = []
        new_schema = OrderedDict()

        # Si hay agrupación previa
        if hasattr(df, "_group_by_columns") and df._group_by_columns:
            # Añadir columnas agrupadas (con alias) al SELECT
            for sel_expr in df._group_by_select_exprs:
                select_exprs.append(sel_expr)

            # Añadir al esquema final
            for col_name, col_type in df._group_by_schema.items():
                new_schema[col_name] = col_type

        # Procesar expresiones de agregación
        for expr in exprs:
            if not isinstance(expr, Column):
                raise TypeError(f"Se esperaba Column, se recibió {type(expr)}")

            for ref_col in expr.referenced_columns:
                df._check_columns_exist(ref_col)

            # Inferencia de tipo simplificada
            if expr._data_type is None:
                inferred_type = "string"
                if len(expr.referenced_columns) == 1:
                    ref = expr.referenced_columns[0]
                    base_type = df.schema.get(ref, "string")
                    sql_expr = expr.to_sql().lower()
                    if "count(" in sql_expr:
                        inferred_type = "int"
                    elif "array_agg(" in sql_expr:
                        inferred_type = f"array<{base_type}>"
                    else:
                        inferred_type = base_type
                expr._data_type = inferred_type

            select_exprs.append(expr.to_sql())
            output_name = expr.alias_name or expr.expr
            new_schema[output_name] = expr._data_type

        # Construir query final
        if df._group_by_columns:
            group_clause = ", ".join(df._group_by_columns)
            query = (
                f"SELECT {', '.join(select_exprs)} "
                f"FROM {df.current_alias} "
                f"GROUP BY {group_clause}"
            )
        else:
            query = f"SELECT {', '.join(select_exprs)} FROM {df.current_alias}"

        # Agregar nuevo paso
        new_alias = df._get_next_alias()
        df.steps.append((new_alias, query))
        df.current_alias = new_alias
        df.schema = new_schema

        # Limpiar agrupación para futuros pasos
        df._group_by_columns = None
        df._group_by_select_exprs = None
        df._group_by_schema = None

        return df

    def withColumnRenamed(self, existing: str, new: str):
        df = self.copy()
        df._check_columns_exist(existing)

        prev_alias = df.steps[-1][0]
        new_alias = df._get_next_alias()

        new_cols_sql = []
        new_schema = OrderedDict()

        for col_name, col_type in df.schema.items():
            if col_name == existing:
                new_cols_sql.append(f"{existing} AS {new}")
                new_schema[new] = col_type
            else:
                new_cols_sql.append(col_name)
                new_schema[col_name] = col_type

        query = f"SELECT {', '.join(new_cols_sql)} FROM {prev_alias}"
        df.steps.append((new_alias, query))
        df.current_alias = new_alias
        df.schema = new_schema

        return df

    def withColumn(self, name: str, col_expr):
        if not isinstance(col_expr, Column):
            raise TypeError("withColumn() espera una expresión tipo Column como segundo argumento")

        df = self.copy()

        # Validar que las columnas referenciadas existan
        for ref_col in col_expr.referenced_columns:
            df._check_columns_exist(ref_col)

        prev_alias = df.steps[-1][0]
        new_alias = df._get_next_alias()

        # Construimos SELECT usando todas las columnas del schema excepto la que se sobrescribirá
        base_columns = [c for c in df.schema if c != name]
        select_exprs = base_columns + [col_expr.alias(name).to_sql()]

        query = f"SELECT {', '.join(select_exprs)} FROM {prev_alias}"
        df.steps.append((new_alias, query))
        df.current_alias = new_alias

        # Actualizamos el schema con el tipo de dato del Column (si está disponible)
        inferred_type = getattr(col_expr, "_data_type", "string")

        df.schema[name] = inferred_type

        return df

    def join(self, other, on, how="inner"):
        df = self.copy()

        # Clonar base
        joined_df = DataFrame.__new__(DataFrame)
        joined_df.database = df.database
        joined_df.table = df.table
        joined_df.reader = df.reader
        joined_df.schema = OrderedDict()
        joined_df.steps = df.steps.copy()

        # Mapear steps de 'other' con alias únicos
        alias_map = {}
        for alias, query in other.steps:
            new_alias = joined_df._get_next_alias()
            for old, new in alias_map.items():
                query = query.replace(old, new)
            alias_map[alias] = new_alias
            joined_df.steps.append((new_alias, query))

        # Aliases actuales
        left_alias = getattr(df, "_df_alias", None) or df.current_alias
        right_alias = getattr(other, "_df_alias", None) or alias_map.get(other.current_alias, other.current_alias)

        # Condición ON
        if isinstance(on, Column):
            on_expr = on.to_sql()
        elif isinstance(on, str):
            on_expr = f"{left_alias}.{on} = {right_alias}.{on}"
        elif isinstance(on, list):
            on_expr = ' AND '.join([f"{left_alias}.{col} = {right_alias}.{col}" for col in on])
        else:
            raise TypeError("El parámetro 'on' debe ser str, list de str o una expresión Column")

        # Prioridad según tipo de join
        how_lower = how.lower()
        prefer_left = how_lower in ("inner", "left")
        prefer_right = how_lower == "right"
        include_both = not (prefer_left or prefer_right)

        # Construir SELECT y schema final
        select_exprs = []
        schema = OrderedDict()

        # 1. Columnas del lado izquierdo
        for col, dtype in self.schema.items():
            select_exprs.append(f"{left_alias}.{col} AS {col}")
            schema[col] = dtype

        # 2. Columnas del lado derecho según preferencia
        for col, dtype in other.schema.items():
            if col in schema:
                if prefer_right:
                    # Reemplazar columna del lado izquierdo
                    select_exprs = [e for e in select_exprs if not e.endswith(f"AS {col}")]
                    select_exprs.append(f"{right_alias}.{col} AS {col}")
                    schema[col] = dtype
                elif include_both:
                    # Añadir duplicada con sufijo
                    new_name = f"{col}_right"
                    select_exprs.append(f"{right_alias}.{col} AS {new_name}")
                    schema[new_name] = dtype
                # prefer_left → no hacer nada
            else:
                # Columna no duplicada → incluir normalmente
                select_exprs.append(f"{right_alias}.{col} AS {col}")
                schema[col] = dtype

        # Construir SQL final
        join_alias = joined_df._get_next_alias()
        join_sql = f"""
            SELECT {', '.join(select_exprs)}
            FROM {left_alias}
            {how.upper()} JOIN {right_alias}
            ON {on_expr}
        """.strip()

        joined_df.steps.append((join_alias, join_sql))
        joined_df.current_alias = join_alias
        joined_df.schema = schema

        return joined_df

    def limit(self, n: int):
        df = self.copy()
        new_alias = df._get_next_alias()
        prev_alias = df.steps[-1][0]
        query = f"SELECT * FROM {prev_alias} LIMIT {n}"
        df.steps.append((new_alias, query))
        df.current_alias = new_alias
        return df

    def fillna(self, value, subset=None):
        df = self.copy()

        # Determinar columnas sobre las que aplicar fillna
        if subset is None:
            subset = list(df.schema.keys())
        else:
            if isinstance(subset, str):
                subset = [subset]
            df._check_columns_exist(*subset)

        select_exprs = []
        new_schema = OrderedDict()

        for col_name, col_type in df.schema.items():
            if col_name in subset:
                expr = f"COALESCE({col_name}, {repr(value)}) AS {col_name}"
            else:
                expr = col_name
            select_exprs.append(expr)
            new_schema[col_name] = col_type  # el tipo no cambia por COALESCE

        new_alias = df._get_next_alias()
        prev_alias = df.steps[-1][0]
        query = f"SELECT {', '.join(select_exprs)} FROM {prev_alias}"
        df.steps.append((new_alias, query))
        df.current_alias = new_alias
        df.schema = new_schema

        return df

    fill = fillna  # alias

    def union(self, other):
        if not isinstance(other, DataFrame):
            raise TypeError("union() espera otro DataFrame como argumento")

        if list(self.schema.keys()) != list(other.schema.keys()):
            raise ValueError("Los DataFrames deben tener las mismas columnas  \
                             (y en el mismo orden) para aplicar union()")

        df = self.copy()

        # Asegurarse de copiar también los pasos de `other` si aún no están
        other_steps = other.steps
        for alias, query in other_steps:
            if alias not in [a for a, _ in df.steps]:
                df.steps.append((alias, query))

        # Crear el nuevo paso con UNION
        new_alias = df._get_next_alias()
        left_alias = self.current_alias
        right_alias = other.current_alias

        query = f"""
            SELECT * FROM {left_alias}
            UNION ALL
            SELECT * FROM {right_alias}
        """

        df.steps.append((new_alias, query))
        df.current_alias = new_alias
        df.schema = self.schema.copy()

        return df

    # ACCIONES

    def count(self):
        if not getattr(self, "_group_by_columns", None):
            # Sin groupBy → ejecuta y devuelve un número
            final_query = f"SELECT COUNT(*) as count FROM {self.current_alias}"
            query = self._build_query(final_query)
            result = self._execute(query)
            return result.iloc[0]['count']
        else:

            # Con groupBy → construye nuevo DataFrame
            df = self.copy()
            prev_alias = df.steps[-1][0]
            new_alias = df._get_next_alias()

            # Convertir columnas del group_by a str (por si hay objetos Column)
            group_cols = [str(col) for col in df._group_by_columns]
            group_clause = ', '.join(group_cols)

            query = (
                f"SELECT {group_clause}, COUNT(*) as count FROM {prev_alias} "
                f"GROUP BY {group_clause}"
            )

            df.steps.append((new_alias, query))
            df.current_alias = new_alias

            # Construir nuevo schema: columnas de agrupación + count
            new_schema = OrderedDict(
                (col, df.schema.get(col, "string"))  # mantener tipo original
                for col in group_cols
            )
            new_schema["count"] = "bigint"
            df.schema = new_schema

            # 💥 Limpia el flag para evitar confusión en futuras llamadas a count()
            df._group_by_columns = None
            df._group_by_select_exprs = None
            df._group_by_schema = None
            return df

    def isEmpty(self):
        return self.count() == 0

    def drop_duplicates(self, subset=None):
        df = self.copy()

        if subset is None:
            subset = list(df.schema.keys())
        elif isinstance(subset, (list, tuple)):
            subset = list(subset)
        else:
            raise TypeError("drop_duplicates() espera None o una lista/tupla de columnas")

        df._check_columns_exist(*subset)

        all_columns = list(df.schema.keys())
        partition_by = ", ".join(subset)
        order_by = ", ".join(subset)  # o cualquier orden determinista

        prev_alias = df.current_alias
        base_alias = df._get_next_alias()
        final_alias = df._get_next_alias()

        base_query = (
            f"SELECT *, ROW_NUMBER() OVER (PARTITION BY {partition_by} ORDER BY {order_by}) AS rn "
            f"FROM {prev_alias}"
        )

        df.steps.append((base_alias, base_query))

        final_query = f"SELECT {', '.join(all_columns)} FROM {base_alias} WHERE rn = 1"
        df.steps.append((final_alias, final_query))

        df.current_alias = final_alias

        return df

    # Alias para fidelidad con PySpark (nombre con minúscula inicial)
    dropDuplicates = drop_duplicates

    def show(self, n: int = 20, truncate: bool = True, vertical: bool = False):
        limited = self.limit(n)
        df = limited._execute(limited._build_query())

        if vertical:
            for idx, row in df.iterrows():
                print("-" * 20)
                print(f"Row {idx}")
                for col in df.columns:
                    print(f"{col}: {row[col]}")
        else:
            # Preparar truncado
            if truncate is True:
                max_width = 20
            elif truncate is False:
                max_width = None
            elif isinstance(truncate, int):
                max_width = truncate
            else:
                raise TypeError("truncate debe ser True, False o un entero")

            # Formatear el DataFrame con truncado
            def truncate_val(val):
                val_str = str(val)
                if max_width is not None and len(val_str) > max_width:
                    return val_str[:max_width - 3] + "..."
                return val_str

            # Aplicar truncado por celda
            formatted = df.copy()
            for col in formatted.columns:
                formatted[col] = formatted[col].apply(truncate_val)

            print(formatted.to_string(index=False))

    def head(self, n: int = 5):
        limited = self.limit(n)
        return limited._execute(limited._build_query())

    def tail(self, n: int = 5):
        limited = self.orderBy(*self.columns, ascending=False).limit(n)
        df = limited._execute(limited._build_query())
        return df[::-1].reset_index(drop=True)

    def take(self, n: int):
        df = self.limit(n)
        result = df._execute(df._build_query())
        return result.head(n).to_dict(orient="records")

    def toPandas(self):
        query = self._build_query()
        return self._execute(query)

    def first(self):
        df = self.limit(1)
        result = df._execute(df._build_query())
        if not result.empty:
            return result.iloc[0].to_dict()
        return None

    def cache(self):
        import uuid

        temp_table = f"cached_{uuid.uuid4().hex[:8]}"
        temp_path = self.reader._path_tmp.rstrip("/") + f"/{temp_table}/"
        temp_db = self.reader._database_tmp

        try:
            # 1. Ejecutar y guardar el resultado
            meta_data = wr.athena.unload(
                sql=self._build_query(),
                path=temp_path,
                database=self.database,
                file_format="parquet",
                workgroup=self.reader._workgroup,  # personalizable
            )

            datos_escaneados = meta_data.raw_payload['Statistics']['DataScannedInBytes']
            self.reader._data_scanned += datos_escaneados

            # 2. Crear metadata
            wr.s3.store_parquet_metadata(
                path=temp_path,
                database=temp_db,
                table=temp_table,
                mode="overwrite"
            )
        except Exception as e:
            raise Exception(
                f"An unexpected error occurred while caching DataFrame to S3: {e} | path={temp_path}"
            ) from e

        # 3. Reemplazar el estado del DataFrame
        self.steps = [(temp_table, f"SELECT * FROM {temp_db}.{temp_table}")]
        self.current_alias = temp_table
        self.database = temp_db
        self.table = temp_table

        # 4. Registrar los recursos temporales
        self.reader._register_temp_table(temp_db, temp_table)
        self.reader._register_temp_path(temp_path)

        return self

    def show_query(self):
        print(self._build_query())
