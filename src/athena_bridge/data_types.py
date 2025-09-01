# This code is based on code from Apache Spark under the license found in the LICENSE file located in the root folder.

class StringType:
    def __str__(self):
        return "VARCHAR"  # Athena


class IntegerType:
    def __str__(self):
        return "INTEGER"


class LongType:
    def __str__(self):
        return "BIGINT"


class ShortType:
    def __str__(self):
        return "SMALLINT"


class FloatType:
    def __str__(self):
        return "FLOAT"


class DoubleType:
    def __str__(self):
        return "DOUBLE"


class BooleanType:
    def __str__(self):
        return "BOOLEAN"


class DateType:
    def __str__(self):
        return "DATE"


class TimestampType:
    def __str__(self):
        return "TIMESTAMP"


class DecimalType:
    def __init__(self, precision=10, scale=2):
        self.precision = precision
        self.scale = scale

    def __str__(self):
        return f"DECIMAL({self.precision}, {self.scale})"

# Y así sucesivamente
