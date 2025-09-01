# This code is based on code from Apache Spark under the license found in the LICENSE file located in the root folder.

import re
from athena_bridge.window import Window


def _infer_literal_type(val):
    if isinstance(val, bool):
        return "boolean"
    elif isinstance(val, int):
        return "int"
    elif isinstance(val, float):
        return "double"
    elif isinstance(val, str):
        return "string"
    elif val is None:
        return "null"
    return "string"


class Column:
    # def __init__(self, expr, referenced_columns=None,alias=None):
    #    self.expr = expr
    #    self.referenced_columns = referenced_columns if referenced_columns is
    #                            not None else self._extract_columns(expr)
    #    self._alias = alias  # <- cambiar aquí

    def __init__(self, expr, referenced_columns=None, alias=None, data_type="string"):
        self.expr = expr
        self.referenced_columns = referenced_columns if referenced_columns is not None else []
        self._alias = alias
        self._data_type = data_type

    def __str__(self):
        return self.expr

    def _extract_referenced_columns(self, expr):
        # lógica simple que extrae nombres de columnas (por ahora solo si expr es un string simple)
        return [expr] if isinstance(expr, str) else []

    def _extract_columns(self, expr: str):
        """
        Extrae posibles nombres de columnas desde una expresión SQL.
        Muy básico, puedes mejorarlo si lo necesitas.
        """
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", expr)
        keywords = {
            "AND", "OR", "NOT", "CASE", "WHEN", "THEN", "ELSE", "END",
            "NULL", "IS", "IN", "AS", "CAST", "DATE", "TRUE", "FALSE"
        }
        return [t for t in tokens if t.upper() not in keywords]

    def alias(self, name):
        self._alias = name  # <- y aquí
        return self

    @property
    def alias_name(self):
        return self._alias

    def to_sql(self):
        return f"{self.expr} AS {self.alias_name}" if self.alias_name else self.expr

    def to_sql_without_alias(self):
        return self.expr

    def asc(self):
        return Column(f"{self.expr} ASC")

    def desc(self):
        return Column(f"{self.expr} DESC")

    # Operadores aritméticos
    def __add__(self, other):
        return self._op(other, '+')

    def __sub__(self, other):
        return self._op(other, '-')

    def __mul__(self, other):
        return self._op(other, '*')

    def __truediv__(self, other):
        return self._op(other, '/')

    # Comparaciones
    def __eq__(self, other):
        return self._op(other, '=')

    def __ne__(self, other):
        return self._op(other, '!=')

    def __gt__(self, other):
        return self._op(other, '>')

    def __lt__(self, other):
        return self._op(other, '<')

    def __ge__(self, other):
        return self._op(other, '>=')

    def __le__(self, other):
        return self._op(other, '<=')

    # Operadores lógicos
    def __and__(self, other):
        return self._op(other, 'AND')

    def __or__(self, other):
        return self._op(other, 'OR')

    def __invert__(self):
        expr = f"NOT ({self.to_sql()})"
        return Column(expr, referenced_columns=self.referenced_columns, data_type="boolean")

    # Generador de nuevas expresiones
    def _op(self, other, operator):
        if isinstance(other, Column):
            expr = f"({self.to_sql()} {operator} {other.to_sql()})"
            refs = list(set(self.referenced_columns + other.referenced_columns))
        else:
            expr = f"({self.to_sql()} {operator} {repr(other)})"
            refs = self.referenced_columns
        return Column(expr, referenced_columns=refs)

    def cast(self, data_type):
        type_mapping = {
            "STRING": "VARCHAR",
            "INT": "INTEGER",
            "INTEGER": "INTEGER",
            "BIGINT": "BIGINT",
            "FLOAT": "FLOAT",
            "DOUBLE": "DOUBLE",
            "BOOLEAN": "BOOLEAN",
            "DATE": "DATE",
            "TIMESTAMP": "TIMESTAMP"
            # Puedes extender esto según lo que necesites
        }

        if hasattr(data_type, "__str__"):
            original_type = str(data_type).upper()
            athena_type = type_mapping.get(original_type, original_type)  # usa tal cual si no está en el mapping
        else:
            raise TypeError("cast() espera un string o una instancia de tipo (StringType, etc.)")

        expr = f"CAST({self.to_sql()} AS {athena_type})"
        return Column(expr, referenced_columns=self.referenced_columns.copy(), data_type=original_type.lower())

    def astype(self, data_type: str):
        return self.cast(data_type)

    def isNull(self):
        expr = f"{self.to_sql()} IS NULL"
        return Column(expr, referenced_columns=self.referenced_columns.copy(), data_type="boolean")

    def isNotNull(self):
        expr = f"{self.to_sql()} IS NOT NULL"
        return Column(expr, referenced_columns=self.referenced_columns.copy(), data_type="boolean")

    def isin(self, *values):
        # Soporta: .isin("a", "b") o .isin(["a", "b"])
        if len(values) == 1 and isinstance(values[0], (list, tuple, set)):
            values = values[0]

        if not values:
            raise ValueError("isin() requiere al menos un valor")

        formatted_values = ", ".join(repr(v) for v in values)
        expr = f"{self.to_sql()} IN ({formatted_values})"
        return Column(expr, referenced_columns=self.referenced_columns.copy(), data_type="boolean")

    def startswith(self, prefix):
        if not isinstance(prefix, str):
            raise TypeError("startswith() espera una cadena de texto")

        expr = f"{self.to_sql()} LIKE {repr(prefix + '%')}"
        return Column(expr, referenced_columns=self.referenced_columns.copy(), data_type="boolean")

    def endswith(self, suffix: str):
        if not isinstance(suffix, str):
            raise TypeError("endswith() espera una cadena de texto")

        expr = f"{self.to_sql()} LIKE {repr('%' + suffix)}"
        return Column(expr, referenced_columns=self.referenced_columns.copy(), data_type="boolean")

    def contains(self, substring: str):
        if not isinstance(substring, str):
            raise TypeError("contains() espera una cadena de texto")

        expr = f"{self.to_sql()} LIKE {repr('%' + substring + '%')}"
        return Column(expr, referenced_columns=self.referenced_columns.copy(), data_type="boolean")

    def substr(self, start: int, length: int):
        if not isinstance(start, int) or not isinstance(length, int):
            raise TypeError("substr() espera dos enteros: posición inicial y longitud")

        expr = f"SUBSTRING({self.to_sql()}, {start}, {length})"
        return Column(expr, referenced_columns=self.referenced_columns.copy(), data_type="string")

    def like(self, pattern: str):
        if not isinstance(pattern, str):
            raise TypeError("like() espera una cadena de texto")

        expr = f"{self.to_sql()} LIKE {repr(pattern)}"
        return Column(expr, referenced_columns=self.referenced_columns.copy(), data_type="boolean")

    def _sql_literal_string(s: str) -> str:
        # Escapa comillas simples para SQL: ' -> ''
        return "'" + s.replace("'", "''") + "'"

    def rlike(self, pattern: str):
        if not isinstance(pattern, str):
            raise TypeError("rlike() espera una cadena de texto")

        expr = f"regexp_like({self.to_sql()}, '{pattern}')"
        # expr = f"regexp_like({column.to_sql()}, {_sql_literal_string(pattern)})"
        return Column(expr, referenced_columns=self.referenced_columns.copy(), data_type="boolean")

    def between(self, lower, upper):
        def to_sql_literal(val):
            # Detecta si el valor es un string con pinta de fecha: 'YYYY-MM-DD'
            if isinstance(val, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", val):
                return f"DATE '{val}'"
            elif isinstance(val, str):
                return f"'{val}'"
            return str(val)

        lower_sql = to_sql_literal(lower)
        upper_sql = to_sql_literal(upper)

        sql_expr = f"{self.to_sql()} BETWEEN {lower_sql} AND {upper_sql}"
        return Column(sql_expr, referenced_columns=self.referenced_columns.copy(), data_type="boolean")

    # Funciones window
    def over(self, window_spec):
        if not isinstance(window_spec, Window):
            raise TypeError("window_spec debe ser una instancia de Window")

        # Construcción segura de cláusulas
        partition_clause = ""
        order_clause = ""

        if window_spec.partition_by:
            parts = ', '.join(str(col) for col in window_spec.partition_by)
            partition_clause = f"PARTITION BY {parts}"

        if window_spec.order_by:
            orders = ', '.join(
                col.to_sql() if hasattr(col, "to_sql") else str(col)
                for col in window_spec.order_by
            )
            order_clause = f"ORDER BY {orders}"

        over_sql = ' '.join(filter(None, [partition_clause, order_clause]))
        full_sql = f"{self.to_sql()} OVER ({over_sql})"

        return Column(
            full_sql,
            referenced_columns=self.referenced_columns.copy(),
            data_type=getattr(self, "data_type", "string")
        )


class _When:

    def __init__(self, condition, value):
        self.whens = [(condition, value)]  # lista de tuplas (condición, valor)

    def when(self, condition, value):
        self.whens.append((condition, value))
        return self

    def otherwise(self, other_value):
        referenced = []
        value_types = []

        when_clauses = []
        for cond, val in self.whens:
            # Condición
            if isinstance(cond, Column):
                cond_sql = cond.to_sql()
                referenced += cond.referenced_columns
            else:
                cond_sql = cond
                referenced += _extract_columns_from_condition(cond_sql)

            # Valor THEN
            if isinstance(val, Column):
                val_sql = val.to_sql()
                referenced += val.referenced_columns
                value_types.append(val._data_type)
            else:
                val_sql = repr(val)
                value_types.append(_infer_literal_type(val))

            when_clauses.append(f"WHEN {cond_sql} THEN {val_sql}")

        # ELSE
        if isinstance(other_value, Column):
            else_sql = other_value.to_sql()
            referenced += other_value.referenced_columns
            value_types.append(other_value._data_type)
        else:
            else_sql = repr(other_value)
            value_types.append(_infer_literal_type(other_value))

        # Inferir tipo común (el primero no string, o string por defecto)
        resolved_type = next((t for t in value_types if t != "string" and t is not None), "string")

        expression = f"CASE {' '.join(when_clauses)} ELSE {else_sql} END"
        return Column(expression, referenced_columns=referenced, data_type=resolved_type)


def broadcast(df):
    import warnings
    warnings.warn(
        "La función broadcast() no tiene efecto en Athena. "
        "Está implementada solo por compatibilidad con PySpark.",
        UserWarning
    )
    return df  # ← devuelve el mismo DataFrame, sin copiar


def when(condition, value):
    return _When(condition, value)


def col(name):
    return Column(name, referenced_columns=[name])


column = col


def lit(value):
    def infer_type(val):
        if isinstance(val, bool):
            return "boolean"
        elif isinstance(val, int):
            return "int"
        elif isinstance(val, float):
            return "double"
        elif isinstance(val, str):
            return "string"
        elif val is None:
            return "null"
        else:
            return "string"  # fallback por defecto

    data_type = infer_type(value)

    if value is None:
        return Column("NULL", data_type=data_type)
    else:
        return Column(quote(value), data_type=data_type)


def coalesce(*cols):
    # Convertir strings a Column si hace falta
    col_objs = [
        col(c) if isinstance(c, str) else c
        for c in cols
    ]

    # Generar la expresión SQL
    sql_exprs = ", ".join(c.to_sql() for c in col_objs)

    # Detectar tipo dominante (simplificado: usamos el primero no string como real, o string)
    types = [c._data_type or "string" for c in col_objs]
    dominant_type = next((t for t in types if t != "string"), "string")

    return Column(
        f"COALESCE({sql_exprs})",
        data_type=dominant_type,
        referenced_columns=[
            rc for c in col_objs for rc in c.referenced_columns
        ]
    )


def greatest(*cols):
    # Convertir strings a Column si hace falta
    col_objs = [
        col(c) if isinstance(c, str) else c
        for c in cols
    ]

    # Generar la expresión SQL
    sql_exprs = ", ".join(c.to_sql() for c in col_objs)

    # Detectar tipo dominante (simplificado: usamos el primero no string como real, o string)
    types = [c._data_type or "string" for c in col_objs]
    dominant_type = next((t for t in types if t != "string"), "string")

    return Column(
        f"GREATEST({sql_exprs})",
        data_type=dominant_type,
        referenced_columns=[
            rc for c in col_objs for rc in c.referenced_columns
        ]
    )


def least(*cols):
    # Convertir strings a Column si hace falta
    col_objs = [
        col(c) if isinstance(c, str) else c
        for c in cols
    ]

    # Generar la expresión SQL
    sql_exprs = ", ".join(c.to_sql() for c in col_objs)

    # Detectar tipo dominante (simplificado: usamos el primero no string como real, o string)
    types = [c._data_type or "string" for c in col_objs]
    dominant_type = next((t for t in types if t != "string"), "string")

    return Column(
        f"LEAST({sql_exprs})",
        data_type=dominant_type,
        referenced_columns=[
            rc for c in col_objs for rc in c.referenced_columns
        ]
    )


def quote(val):
    if isinstance(val, str):
        return f"'{val}'"
    elif isinstance(val, Column):
        return str(val)
    return str(val)


def isnull(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("isnull() espera una columna (str o Column) como argumento")

    expr = f"{column.to_sql()} IS NULL"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="boolean")


def isnotnull(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("isnotnull() espera una columna (str o Column) como argumento")

    expr = f"{column.to_sql()} IS NOT NULL"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="boolean")

# String Functions


def contains(column, substring):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("contains() espera una columna (str o Column) como primer argumento")

    if not isinstance(substring, str):
        raise TypeError("contains() espera un string como segundo argumento")

    return column.contains(substring)


def endswith(column, suffix):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("endswith() espera una columna (str o Column) como primer argumento")

    if not isinstance(suffix, str):
        raise TypeError("endswith() espera un string como segundo argumento")

    return column.endswith(suffix)


def left(column, n):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("left() espera una columna (str o Column) como primer argumento")

    if not isinstance(n, int):
        raise TypeError("left() espera un entero como segundo argumento")

    expr = f"SUBSTRING({column.to_sql()}, 1, {n})"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="string")


def length(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("length() espera una columna (str o Column) como argumento")

    expr = f"LENGTH({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="int")


def like(column, suffix):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("like() espera una columna (str o Column) como primer argumento")

    if not isinstance(suffix, str):
        raise TypeError("like() espera un string como segundo argumento")

    return column.like(suffix)


def ltrim(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("ltrim() espera un string o un objeto Column")

    expr = f"LTRIM({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="string")


def upper(column):
    return Column(f"UPPER({column})", data_type="string")


ucase = upper


def lower(column):
    return Column(f"LOWER({column})", data_type="string")


lcase = lower


def lpad(column, length, pad_string):
    return Column(f"LPAD({column}, {length}, '{pad_string}')", data_type="string")


def right(column, n):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("right() espera una columna (str o Column) como primer argumento")

    if not isinstance(n, int):
        raise TypeError("right() espera un entero como segundo argumento")

    expr = f"SUBSTRING({column.to_sql()}, LENGTH({column.to_sql()}) - {n - 1}, {n})"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="string")


def rpad(column, length, pad_string):
    return Column(f"RPAD({column}, {length}, '{pad_string}')", data_type="string")


def rtrim(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("rtrim() espera un string o un objeto Column")

    expr = f"RTRIM({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="string")


def startswith(column, suffix):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("startswith() espera una columna (str o Column) como primer argumento")

    if not isinstance(suffix, str):
        raise TypeError("startswith() espera un string como segundo argumento")

    return column.startswith(suffix)


def split(column, pattern):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("split() espera una columna (str o Column) como primer argumento")

    if not isinstance(pattern, str):
        raise TypeError("split() espera un string como segundo argumento")

    expr = f"SPLIT({column.to_sql()}, '{pattern}')"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="array<string>")


def substr(column, pos, length):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("substr() espera una columna (str o Column) como primer argumento")
    if not isinstance(pos, int) or not isinstance(length, int):
        raise TypeError("substr() espera dos enteros como segundo y tercer argumento")

    return column.substr(pos, length)


substring = substr


def to_char(column, format=None):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("to_char() espera una columna (str o Column) como argumento")

    if format is not None:
        # Solo permitimos formato si sabemos que es de tipo fecha
        raise NotImplementedError("to_char() con formato numérico no está soportado en Athena")

    expr = f"CAST({column.to_sql()} AS VARCHAR)"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="string")


to_varchar = to_char


def to_number(column, format=None):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("to_number() espera una columna (str o Column) como argumento")

    if format is not None:
        raise NotImplementedError("Athena no soporta to_number() con formato; elimina el argumento `format`")

    expr = f"CAST({column.to_sql()} AS DOUBLE)"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="double")


def trim(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("trim() espera un string o un objeto Column")

    expr = f"TRIM({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="string")


def concat(*columns):
    if not columns:
        raise ValueError("concat() requiere al menos una columna")

    sql_parts = []
    referenced_columns = []

    for c in columns:
        if isinstance(c, str):
            c = col(c)
        if not isinstance(c, Column):
            raise TypeError("concat() espera solo strings o Column")

        sql_parts.append(c.to_sql())
        referenced_columns.extend(c.referenced_columns)

    expr = f"CONCAT({', '.join(sql_parts)})"
    return Column(expr, referenced_columns=list(set(referenced_columns)), data_type="string")


def concat_ws(separator, *columns):
    if not columns:
        raise ValueError("concat_ws() requiere al menos una columna además del separador")

    if not isinstance(separator, str):
        raise TypeError("El separador debe ser un string")

    sql_parts = []
    referenced_columns = []

    for c in columns:
        if isinstance(c, str):
            c = col(c)
        if not isinstance(c, Column):
            raise TypeError("concat_ws() espera solo strings o Column como columnas")

        sql_parts.append(c.to_sql())
        referenced_columns.extend(c.referenced_columns)

    expr = f"CONCAT_WS('{separator}', {', '.join(sql_parts)})"
    return Column(expr, referenced_columns=list(set(referenced_columns)), data_type="string")

# Colection Functions


def sort_array(array_col, asc=True):
    array_obj = col(array_col) if isinstance(array_col, str) else array_col

    if not isinstance(array_obj, Column):
        raise TypeError("sort_array() espera un string o una instancia de Column")

    sort_expr = f"ARRAY_SORT({array_obj.to_sql()})"

    if asc:
        expr = sort_expr
    else:
        expr = f"REVERSE({sort_expr})"  # Simula orden descendente

    return Column(
        expr,
        referenced_columns=array_obj.referenced_columns,
        data_type="array"
    )


# Alias opcional si deseas permitir array_sort como nombre alternativo
array_sort = sort_array


def array_max(array_col):
    array_obj = col(array_col) if isinstance(array_col, str) else array_col

    if not isinstance(array_obj, Column):
        raise TypeError("array_max() espera un string o una instancia de Column")

    expr = f"ARRAY_MAX({array_obj.to_sql()})"
    return Column(
        expr,
        referenced_columns=array_obj.referenced_columns,
        data_type="unknown"  # No se puede inferir sin inspección del array
    )


def array_min(array_col):
    array_obj = col(array_col) if isinstance(array_col, str) else array_col

    if not isinstance(array_obj, Column):
        raise TypeError("array_min() espera un string o una instancia de Column")

    expr = f"ARRAY_MIN({array_obj.to_sql()})"
    return Column(
        expr,
        referenced_columns=array_obj.referenced_columns,
        data_type="unknown"
    )


def reverse(column):
    col_obj = col(column) if isinstance(column, str) else column

    if not isinstance(col_obj, Column):
        raise TypeError("reverse() espera un string o una instancia de Column")

    expr = f"REVERSE({col_obj.to_sql()})"

    return Column(
        expr,
        referenced_columns=col_obj.referenced_columns,
        data_type=col_obj._data_type or "unknown"
    )


def array_size(column):
    column_obj = col(column) if isinstance(column, str) else column

    if not isinstance(column_obj, Column):
        raise TypeError("array_size() espera un string o una instancia de Column")

    expr = f"CARDINALITY({column_obj.to_sql()})"
    return Column(
        expr,
        referenced_columns=column_obj.referenced_columns,
        data_type="int"
    )


size = array_size
cardinality = array_size


def array_position(array_col, value):
    array_obj = col(array_col) if isinstance(array_col, str) else array_col

    if not isinstance(array_obj, Column):
        raise TypeError("array_position() espera un string o una instancia de Column como primer argumento")

    # Permitir que el valor sea string, número, o Column
    if isinstance(value, Column):
        value_expr = value.to_sql()
        referenced = array_obj.referenced_columns + value.referenced_columns
    elif isinstance(value, (str, int, float)):
        value_expr = f"'{value}'" if isinstance(value, str) else str(value)
        referenced = array_obj.referenced_columns
    else:
        raise TypeError("El valor debe ser un literal o Column")

    expr = f"ARRAY_POSITION({array_obj.to_sql()}, {value_expr})"
    return Column(expr, referenced_columns=referenced, data_type="int")


def element_at(array_col, index):
    array_obj = col(array_col) if isinstance(array_col, str) else array_col
    index_expr = col(index) if isinstance(index, str) else index

    if not isinstance(array_obj, Column):
        raise TypeError("element_at() espera un string o una instancia de Column como primer argumento")

    # Permitir que el índice sea una constante o una columna
    if isinstance(index_expr, Column):
        index_sql = index_expr.to_sql()
        referenced_columns = array_obj.referenced_columns + index_expr.referenced_columns
    elif isinstance(index_expr, (int, float)):
        index_sql = str(index_expr)
        referenced_columns = array_obj.referenced_columns
    else:
        raise TypeError("El índice debe ser int, float, string (nombre de columna) o Column")

    expr = f"ELEMENT_AT({array_obj.to_sql()}, {index_sql})"
    return Column(
        expr,
        referenced_columns=referenced_columns,
        data_type="unknown"  # Tipo genérico; no podemos inferirlo sin inspección adicional
    )

# Agregate Functions


def _aggregate_sql(func_name, column, return_type=None):
    if isinstance(column, str):
        column = col(column)

    col_name_clean = column.to_sql().replace('"', '').replace('.', '_')
    alias = f"{func_name.lower()}_{col_name_clean}"

    expr = f"{func_name.upper()}({column.to_sql()})"

    # Usar tipo original si no se especifica uno nuevo
    data_type = return_type or None  # column._data_type or "string"

    return Column(expr, referenced_columns=column.referenced_columns.copy(), alias=alias, data_type=data_type)


def count(column):
    return _aggregate_sql("count", column, "int")


def sum(column):
    return _aggregate_sql("sum", column, "float")


def avg(column):
    return _aggregate_sql("avg", column, "float")


def mean(column):
    return _aggregate_sql("avg", column, "float")


def min(column):
    return _aggregate_sql("min", column)


def max(column):
    return _aggregate_sql("max", column)


def std(column):
    return _aggregate_sql("stddev_samp", column, "float")


stddev = std  # alias como en PySpark
stddev_samp = std  # alias como en PySpark


def array_agg(column):
    return _aggregate_sql("array_agg", column)


collect_list = array_agg


def collect_set(column):
    if isinstance(column, str):
        column = col(column)

    expr = f"ARRAY_AGG(DISTINCT {column.to_sql()})"
    col_name_clean = column.to_sql().replace('"', '').replace('.', '_')
    alias = f"collect_set_{col_name_clean}"
    # data_type = f"array<{column._data_type or 'string'}>"

    return Column(expr, alias=alias, data_type=None,  referenced_columns=column.referenced_columns.copy())


# Sort Functions

def desc(expr):
    column = col(expr) if isinstance(expr, str) else expr
    return Column(f"{column.to_sql()} DESC", referenced_columns=column.referenced_columns.copy())


def asc(expr):
    column = col(expr) if isinstance(expr, str) else expr
    return Column(f"{column.to_sql()} ASC", referenced_columns=column.referenced_columns.copy())

# Math Functions


def abs(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("abs() espera un string o una instancia de Column")

    expr = f"ABS({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns, data_type="double")


def sqrt(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("sqrt() espera un string o una instancia de Column")

    expr = f"SQRT({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns, data_type="double")


def floor(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("floor() espera un string o una instancia de Column")

    expr = f"FLOOR({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns, data_type="int")


def ceil(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("ceil() espera un string o una instancia de Column")

    expr = f"CEIL({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns, data_type="int")


ceiling = ceil


def round(column, scale=0):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("round() espera un string o una instancia de Column")

    if not isinstance(scale, int):
        raise TypeError("scale debe ser un entero")

    expr = f"ROUND({column.to_sql()}, {scale})"
    return Column(expr, referenced_columns=column.referenced_columns, data_type="double" if scale else "int")


def sign(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("sign() espera un string o una instancia de Column")

    expr = f"SIGN({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns, data_type="int")


signum = sign

# Datetime Functions


def current_date():
    return Column("CURRENT_DATE", data_type="date")


curdate = current_date


def date_format(column, format_str: str):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("date_format() espera una columna (str o Column) como primer argumento")

    if not isinstance(format_str, str):
        raise TypeError("El parámetro 'format_str' debe ser una cadena de texto")

    expr = f"format_datetime({column.to_sql()}, '{format_str}')"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="string")


def dateadd(start_date, days):
    if isinstance(start_date, str):
        start_date = col(start_date)

    if not isinstance(start_date, Column):
        raise TypeError("dateadd() espera una columna (str o Column) como primer argumento")

    if not isinstance(days, (int, Column, str)):
        raise TypeError("dateadd() espera un número entero o una columna como segundo argumento")

    if isinstance(days, str):
        days = col(days)

    if isinstance(days, Column):
        expr = f"DATE_ADD('day', {days.to_sql()}, {start_date.to_sql()})"
        referenced = start_date.referenced_columns + days.referenced_columns
    else:
        expr = f"DATE_ADD('day', {days}, {start_date.to_sql()})"
        referenced = start_date.referenced_columns

    return Column(expr, referenced_columns=list(set(referenced)), data_type="date")


date_add = dateadd


def addmonths(start_date, months):
    if isinstance(start_date, str):
        start_date = col(start_date)

    if not isinstance(start_date, Column):
        raise TypeError("add_months() espera una columna (str o Column) como primer argumento")

    if not isinstance(months, (int, Column, str)):
        raise TypeError("add_months() espera un número entero o una columna como segundo argumento")

    if isinstance(months, str):
        months = col(months)

    if isinstance(months, Column):
        # El segundo argumento es una columna
        expr = f"DATE_ADD('month', {months.to_sql()}, {start_date.to_sql()})"
        referenced = start_date.referenced_columns + months.referenced_columns
    else:
        # El segundo argumento es un número entero literal
        expr = f"DATE_ADD('month', {months}, {start_date.to_sql()})"
        referenced = start_date.referenced_columns

    return Column(expr, referenced_columns=list(set(referenced)), data_type="date")


add_months = addmonths


def datediff(end_date, start_date):
    if isinstance(end_date, str):
        end_date = col(end_date)
    if isinstance(start_date, str):
        start_date = col(start_date)

    if not isinstance(end_date, Column) or not isinstance(start_date, Column):
        raise TypeError("datediff() espera dos strings o Column")

    expr = f"DATE_DIFF('day', {start_date.to_sql()}, {end_date.to_sql()})"
    referenced = start_date.referenced_columns + end_date.referenced_columns
    return Column(expr, referenced_columns=list(set(referenced)), data_type="int")


date_diff = datediff


def monthsbetween(end_date, start_date, roundOff=True):
    if isinstance(end_date, str):
        end_date = col(end_date)

    if not isinstance(end_date, Column):
        raise TypeError("months_between() espera una columna (str o Column) como primer argumento")

    if isinstance(start_date, str):
        start_date = col(start_date)

    if not isinstance(start_date, Column):
        raise TypeError("months_between() espera una columna (str o Column) como segundo argumento")

    base_expr = f"CAST(DATE_DIFF('day', {start_date.to_sql()}, {end_date.to_sql()}) AS DOUBLE) / 31.0"

    if roundOff:
        expr = f"ROUND({base_expr}, 8)"
    else:
        expr = base_expr

    referenced = end_date.referenced_columns + start_date.referenced_columns

    return Column(expr, referenced_columns=list(set(referenced)), data_type="double")


months_between = monthsbetween


def day(expr):
    if isinstance(expr, str):
        expr = col(expr)

    if not isinstance(expr, Column):
        raise TypeError("day() espera un string o un objeto Column")

    sql_expr = f"day({expr.to_sql()})"
    return Column(sql_expr, referenced_columns=expr.referenced_columns.copy(), data_type="int")


dayofmonth = day


def dayofweek(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("dayofweek() espera una columna (str o Column) como argumento")

    expr = f"DAY_OF_WEEK({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns, data_type="int")


# Alias
weekday = dayofweek


def dayofyear(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("dayofyear() espera una columna (str o Column) como argumento")

    expr = f"DAY_OF_YEAR({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns, data_type="int")


def month(expr):
    if isinstance(expr, str):
        expr = col(expr)

    if not isinstance(expr, Column):
        raise TypeError("month() espera un string o un objeto Column")

    sql_expr = f"month({expr.to_sql()})"
    return Column(sql_expr, referenced_columns=expr.referenced_columns.copy(), data_type="int")


def last_day(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("last_day() espera un string o una instancia de Column")

    expr = f"LAST_DAY_OF_MONTH({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns, data_type="date")


def now():
    return Column("CURRENT_TIMESTAMP", data_type="timestamp")


current_timestamp = now


def to_date(expr):

    if isinstance(expr, str):
        # Interpretamos strings como nombres de columna (igual que PySpark)
        expr = col(expr)

    if isinstance(expr, Column):
        sql_expr = f"CAST({expr.to_sql()} AS DATE)"
        return Column(sql_expr, referenced_columns=expr.referenced_columns.copy(), data_type="date")

    raise TypeError("to_date() espera una columna (str o Column), no acepta strings literales")


def from_unixtime(col_expr, format_str='yyyy-MM-dd HH:mm:ss'):

    if isinstance(col_expr, str):
        col_expr = col(col_expr)

    if not isinstance(col_expr, Column):
        raise TypeError("from_unixtime() espera una columna (str o Column), no un valor literal")

    if not isinstance(format_str, str):
        raise TypeError("El segundo parámetro (formato) debe ser una cadena")

    sql_expr = f"format_datetime(from_unixtime({col_expr.to_sql()}), '{format_str}')"

    return Column(sql_expr, referenced_columns=col_expr.referenced_columns.copy(), data_type="string")


def unix_timestamp(col_expr=None, format_str='yyyy-MM-dd HH:mm:ss'):
    if col_expr is None:
        # now() -> timestamp; to_unixtime() -> DOUBLE; CAST -> BIGINT
        return Column("CAST(to_unixtime(now()) AS BIGINT)", data_type="bigint")

    if isinstance(col_expr, str):
        col_expr = col(col_expr)

    if not isinstance(col_expr, Column):
        raise TypeError("unix_timestamp() espera None, un string (nombre de columna) o un objeto Column")

    if format_str is None:
        sql_expr = f"CAST(to_unixtime({col_expr.to_sql()}) AS BIGINT)"
    else:
        if not isinstance(format_str, str):
            raise TypeError("El segundo parámetro (formato) debe ser una cadena")
        # parse_datetime(...) -> timestamp; to_unixtime(...) -> DOUBLE; CAST -> BIGINT
        sql_expr = f"CAST(to_unixtime(parse_datetime({col_expr.to_sql()}, '{format_str}')) AS BIGINT)"

    return Column(sql_expr, referenced_columns=col_expr.referenced_columns.copy(), data_type="bigint")


def weekofyear(column):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("weekofyear() espera una columna (str o Column) como argumento")

    expr = f"WEEK_OF_YEAR({column.to_sql()})"
    return Column(expr, referenced_columns=column.referenced_columns, data_type="int")


def year(expr):
    if isinstance(expr, str):
        expr = col(expr)

    if not isinstance(expr, Column):
        raise TypeError("year() espera un string o un objeto Column")

    sql_expr = f"year({expr.to_sql()})"
    return Column(sql_expr, referenced_columns=expr.referenced_columns.copy(), data_type="int")


def repeat(column, n: int):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("repeat() espera un string o un objeto Column")

    if not isinstance(n, int) or n < 0:
        raise ValueError("repeat() espera un entero positivo")

    expr = f"array_join(repeat(CAST({column.to_sql()} AS VARCHAR), {n}),'')"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="string")

# Regular Expression (Quiza de problemas con caracter especiales y hay que escaparlos)


def rlike(column, pattern):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("rlike() espera una columna (str o Column) como primer argumento")

    if not isinstance(pattern, str):
        raise TypeError("rlike() espera un string como segundo argumento")

    return column.rlike(pattern)


regexp_like = rlike
regexp = rlike


def regexp_replace(column, pattern: str, replacement: str):
    if isinstance(column, str):
        column = col(column)

    if not isinstance(column, Column):
        raise TypeError("regexp_replace() espera un string o un objeto Column")

    if not isinstance(pattern, str):
        raise TypeError("rlike() espera un string como segundo argumento")

    if not isinstance(replacement, str):
        raise TypeError("rlike() espera un string como tercer argumento")

    expr = f"regexp_replace({column.to_sql()}, '{pattern}', '{replacement}')"
    return Column(expr, referenced_columns=column.referenced_columns.copy(), data_type="string")


# Funciones window


def row_number():
    return Column("row_number()", data_type="bigint")


def rank():
    return Column("rank()", data_type="bigint")


def dense_rank():
    return Column("dense_rank()", data_type="bigint")


def ntile(n):
    if not isinstance(n, int):
        raise TypeError("ntile(n) espera un entero")
    if n <= 0:
        raise ValueError("ntile(n) espera un entero positivo")
    return Column(f"ntile({n})", referenced_columns=set(), data_type="bigint")


def lag(column_name, offset=1, default=None):
    column = col(column_name) if isinstance(column_name, str) else column_name

    # Construir expresión base
    expr = f"LAG({column.to_sql()}, {offset}"
    referenced = column.referenced_columns.copy()

    if default is not None:
        if isinstance(default, str):
            expr += f", '{default}'"
        else:
            expr += f", {default}"
    expr += ")"
    # TODO: Asignar bien el tipo
    return Column(expr, referenced_columns=referenced, data_type=None)


def countDistinct(*columns):
    """
    Simula pyspark.sql.functions.countDistinct para Athena SQL.

    Args:
        *columns: Uno o más nombres de columnas (str o Column)

    Returns:
        Column: Expresión SQL COUNT(DISTINCT col1, col2, ...)
    """
    col_exprs = []
    referenced = []

    for col in columns:
        if isinstance(col, str):
            col_exprs.append(col)
            referenced.append(col)
        elif isinstance(col, Column):
            col_exprs.append(col.to_sql())
            referenced.extend(col.referenced_columns)
        else:
            raise TypeError("countDistinct espera columnas tipo str o Column")

    expr = f"COUNT(DISTINCT {', '.join(col_exprs)})"
    return Column(expr, referenced_columns=referenced)


def _extract_columns_from_condition(condition: str):
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", condition)
    keywords = {"AND", "OR", "NOT", "CASE", "WHEN", "THEN", "ELSE", "END"}
    return [t for t in tokens if t.upper() not in keywords]
