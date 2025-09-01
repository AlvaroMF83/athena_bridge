import unittest
from athena_bridge import data_types

class TestDataTypes(unittest.TestCase):

    def test_string_type(self):
        t = data_types.StringType()
        self.assertEqual(str(t), "VARCHAR")

    def test_integer_type(self):
        t = data_types.IntegerType()
        self.assertEqual(str(t), "INTEGER")

    def test_long_type(self):
        t = data_types.LongType()
        self.assertEqual(str(t), "BIGINT")

    def test_short_type(self):
        t = data_types.ShortType()
        self.assertEqual(str(t), "SMALLINT")

    def test_float_type(self):
        t = data_types.FloatType()
        self.assertEqual(str(t), "FLOAT")

    def test_double_type(self):
        t = data_types.DoubleType()
        self.assertEqual(str(t), "DOUBLE")

    def test_boolean_type(self):
        t = data_types.BooleanType()
        self.assertEqual(str(t), "BOOLEAN")

    def test_date_type(self):
        t = data_types.DateType()
        self.assertEqual(str(t), "DATE")

    def test_timestamp_type(self):
        t = data_types.TimestampType()
        self.assertEqual(str(t), "TIMESTAMP")

    def test_decimal_type_default(self):
        t = data_types.DecimalType()
        self.assertEqual(str(t), "DECIMAL(10, 2)")

    def test_decimal_type_custom(self):
        t = data_types.DecimalType(precision=8, scale=3)
        self.assertEqual(str(t), "DECIMAL(8, 3)")


