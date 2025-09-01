import unittest
from athena_bridge import window

class DummyColumn:
    def __init__(self, name):
        self.name = name

    def to_sql(self):
        return self.name

    def __str__(self):
        return self.name

class TestWindowClass(unittest.TestCase):

    def test_window_empty(self):
        w = window.Window()
        self.assertEqual(str(w), "OVER ()")

    def test_partition_by(self):
        w = window.Window(partition_by=["col1", "col2"])
        self.assertIn("PARTITION BY col1, col2", str(w))

    def test_order_by(self):
        col1 = DummyColumn("fecha")
        col2 = DummyColumn("hora")
        w = window.Window(order_by=[col1, col2])
        self.assertIn("ORDER BY fecha, hora", str(w))

    def test_partition_and_order_by(self):
        col1 = DummyColumn("fecha")
        w = window.Window(partition_by=["user_id"], order_by=[col1])
        s = str(w)
        self.assertIn("PARTITION BY user_id", s)
        self.assertIn("ORDER BY fecha", s)

    def test_partitionBy_method_chain(self):
        w = window.Window().partitionBy("cliente_id", "pais")
        self.assertIn("PARTITION BY cliente_id, pais", str(w))

    def test_orderBy_method_chain(self):
        col = DummyColumn("fecha")
        w = window.Window().orderBy(col)
        self.assertIn("ORDER BY fecha", str(w))

    def test_chain_partition_then_order(self):
        col = DummyColumn("fecha")
        w = window.Window().partitionBy("pais").orderBy(col)
        s = str(w)
        self.assertIn("PARTITION BY pais", s)
        self.assertIn("ORDER BY fecha", s)