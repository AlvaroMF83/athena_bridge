# This code is based on code from Apache Spark under the license found in the LICENSE file located in the root folder.

class Window:
    def __init__(self, partition_by=None, order_by=None):
        self.partition_by = list(partition_by or [])
        self.order_by = list(order_by or [])

    # Métodos de instancia para encadenamiento

    def partitionBy(self, *cols):
        return Window(partition_by=cols, order_by=self.order_by)

    def orderBy(self, *cols):
        return Window(partition_by=self.partition_by, order_by=cols)

    def __str__(self):
        clauses = []
        if self.partition_by:
            parts = ', '.join(str(col) for col in self.partition_by)
            clauses.append(f"PARTITION BY {parts}")
        if self.order_by:
            orders = ', '.join(col.to_sql() if hasattr(col, "to_sql") else str(col) for col in self.order_by)
            clauses.append(f"ORDER BY {orders}")
        return f"OVER ({' '.join(clauses)})"
