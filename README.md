[![PyPI version](https://img.shields.io/pypi/v/athena_bridge.svg)](https://pypi.org/project/athena_bridge/)
[![Python versions](https://img.shields.io/pypi/pyversions/athena_bridge.svg)](https://pypi.org/project/athena_bridge/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Downloads](https://pepy.tech/badge/athena_bridge)](https://pepy.tech/project/athena_bridge)
[![GitHub stars](https://img.shields.io/github/stars/<tuusuario>/athena_bridge.svg?style=social&label=Star)](https://github.com/AlvaroMF83/athena_bridge)

# 🪶 athena_bridge

[🇪🇸 Leer en español](./README_ES.md)

**athena_bridge** is an open-source Python library that replicates the most common **PySpark** functions, allowing you to execute PySpark-like code directly on **AWS Athena** via automatically generated SQL.

With this library, you can **reuse your existing PySpark code without needing an EMR Cluster or Glue Interactive Session**, leveraging Athena’s SQL backend with identical syntax to PySpark.

---

## ✨ Key Features
- Mirrors the most used `pyspark.sql.functions`, `DataFrame`, `Column`, and `Window` APIs.
- Enables migration of PySpark code to environments without Spark.
- Translates PySpark-style operations into executable **Athena SQL** through `awswrangler`.
- Fully compatible with **Python ≥ 3.8** and **AWS Athena / Glue Catalog**.

---

## 📦 Installation
Available on [PyPI](https://pypi.org/project/athena-bridge/):

```bash
pip install athena_bridge
```

### Dependencies
- `awswrangler`
- `boto3`
- `pandas`

---

## ⚙️ AWS Configuration

To run athena_bridge queries from Amazon SageMaker, the execution role (AmazonSageMaker-ExecutionRole-xxxxxxxxxxxxx) must have the proper permissions for Glue, Athena, and S3.

Edit the role and attach a policy like the following (replace account IDs and bucket names with your own).

Example (anonymized) of a **IAM Role Policy**:

```json
{
	"Version": "2012-10-17",
	"Statement": [
		{
			"Sid": "GlueAllDatabasesAllTables",
			"Effect": "Allow",
			"Action": [
				"glue:GetCatalogImportStatus",
				"glue:GetDatabase",
				"glue:GetDatabases",
				"glue:CreateDatabase",
				"glue:UpdateDatabase",
				"glue:DeleteDatabase",
				"glue:GetTable",
				"glue:GetTables",
				"glue:CreateTable",
				"glue:UpdateTable",
				"glue:DeleteTable",
				"glue:GetPartition",
				"glue:GetPartitions",
				"glue:CreatePartition",
				"glue:BatchCreatePartition",
				"glue:UpdatePartition",
				"glue:DeletePartition",
				"glue:BatchDeletePartition"
			],
			"Resource": [
				"arn:aws:glue:eu-central-1:__ACCOUNT_ID_HERE__:catalog",
				"arn:aws:glue:eu-central-1:__ACCOUNT_ID_HERE__:database/*",
				"arn:aws:glue:eu-central-1:__ACCOUNT_ID_HERE__:table/*/*"
			]
		},
        {
			"Sid": "AthenaWorkgroupAccess",
			"Effect": "Allow",
			"Action": [
				"athena:GetWorkGroup",
				"athena:StartQueryExecution",
				"athena:GetQueryExecution",
				"athena:GetQueryResults",
				"athena:StopQueryExecution"
			],
			"Resource": "arn:aws:athena:eu-central-1:__ACCOUNT_ID_HERE__:workgroup/__YOUR_WORKGROUP_HERE_"
		},
		{
			"Sid": "AthenaS3AccessNOTE",
			"Effect": "Allow",
			"Action": [
				"s3:ListBucket",
				"s3:GetBucketLocation",
				"s3:GetObject",
				"s3:PutObject"
			],
			"Resource": [
				"arn:aws:s3:::sagemaker-studio-__ACCOUNT_ID_HERE__-xxxxxxxxxxx",
				"arn:aws:s3:::sagemaker-studio-__ACCOUNT_ID_HERE__-xxxxxxxxxxx/*",
				"arn:aws:s3:::sagemaker-eu-central-1-__ACCOUNT_ID_HERE__",
				"arn:aws:s3:::sagemaker-eu-central-1-__ACCOUNT_ID_HERE__/*"
			]
		}
	]
}
```

> ⚠️ **Note:** It is recommended to restrict the `Resource` field to specific buckets, databases, and workgroups.


To ensure that all Athena queries (including UNLOAD and CTAS operations) store their results only in the designated S3 bucket, you must enable the “Enforce workgroup configuration / Override client-side settings” option in the Athena Workgroup configuration.
This setting prevents clients (such as boto3 or awswrangler) from overriding the result location and guarantees that all query outputs are written to the S3 path defined in the workgroup.
Without this enforcement, UNLOAD commands may write temporary files (e.g., .csv, .metadata, .manifest) into unintended locations, potentially corrupting Parquet datasets.

---

## 🚀 Quick Start

```python
from athena_bridge import functions as F
from athena_bridge.spark_athena_bridge import get_spark

# --- Initialize Spark-like session ---
spark = get_spark(
    database_tmp="__YOUR_ATHENA_DATABASE__",
    path_tmp="s3://__YOUR_S3_TEMP_PATH_FOR_ATHENA_BRIDGE__/",
    workgroup="__YOUR_ATHENA_WORKGROUP__"
)

# --- Read data from S3 (CSV, Parquet, etc.) ---
df_csv = (
    spark.read
         .format("csv")
         .option("header", True)      # usa True si tus CSV tienen cabecera
         .option("sep", ";")          # cambia a "," o elimina esta línea si no aplica
         .load("s3://__YOUR_S3_DIRECTORY_THAT_CONTAINS_CSV__/")
)

# --- Write dataset as Parquet ---
df_csv.write.format("parquet").mode("overwrite").save(
    "s3://__YOUR_S3_PARQUET_OUTPUT_PATH__/"
)

# --- Read back the Parquet dataset ---
df = spark.read.format("parquet").load(
    "s3://__YOUR_S3_PARQUET_OUTPUT_PATH__/"
)

# --- Simple DataFrame operations ---
df = df.withColumn("total_amount", F.lit(1000))
df.filter(F.col("total_amount") > 500).show()

# --- Stop session ---
spark.stop()
```

💡 **Note**:
Make sure the **“Enforce workgroup configuration / Override client-side settings”** option is enabled in your Athena Workgroup, so that all queries and UNLOAD operations always write their outputs to the S3 location defined in the workgroup, preventing auxiliary files from being written outside that path.

🧠 **Result**:
The code initializes a Spark-like session connected to Athena, reads data from S3 (for example, in CSV format), writes it back as Parquet, and allows you to perform operations using PySpark-style syntax (such as withColumn, filter, show).
The computations are executed on Athena, and the results are displayed directly in the execution environment (e.g., SageMaker or a local notebook).

---

## 📘 More detailed examples

You can find more detailed notebooks in the [`examples/`](./examples/) directory:

- [example_athena_bridge_using_dataproc_module.ipynb](./examples/example_athena_bridge_using_dataproc_module.ipynb) — Read & write example using the **Dataproc** module.  
- [example_athena_bridge_using_spark_module.ipynb](./examples/example_athena_bridge_using_spark_module.ipynb) — Read & write example using the **Spark** module.  
- [quickstart.ipynb](./examples/quickstart.ipynb) — Minimal quickstart example.

---

## 🧰 PySpark Compatibility

`athena_bridge` implements a large subset of PySpark’s native functions.  
You can check the complete list of implemented functions and links to the official documentation:

| Module | Available Functions | Link |
|--------|----------------------|------|
| `functions` | 100+ PySpark functions: math, string, date, and collection operations | [functions.html](./documentation/Functions.html) |
| `dataframe` | DataFrame methods (`select`, `filter`, `join`, `show`, etc.) | [dataframe.html](./documentation/DataFrame.html) |
| `column` | Column expressions and operators | [column.html](./documentation/Column.html) |
| `window` | Basic window operations (`partitionBy`, `orderBy`) | [window.html](./documentation/Window.html) |

Each link includes direct references to the official PySpark documentation for easier migration.

---

## ⚠️ Differences from PySpark

- Operations are executed on Athena, not on a distributed Spark cluster.
- Some advanced methods (e.g., `collect_set`, `rdd`, `pivot`) are not implemented yet.
- Streaming and RDD-based features are not supported.
- Performance depends on Athena query limits and execution times.

---

## 🧪 Full Example (Jupyter / SageMaker)

Check out the notebook [`Ejemplo_finn_athena_bridge_usando_dataproc.ipynb`](./Ejemplo_finn_athena_bridge_usando_dataproc.ipynb) for a complete example, including:
- how to connect using `boto3` and `awswrangler`,
- how to create DataFrames from Athena results,
- and how to combine `athena_bridge` with `pandas` seamlessly.

---

## 🔐 License

This project is licensed under the **Apache License 2.0**.

It includes parts of the public API interface from **Apache Spark (PySpark)** under the same license.

See:
- [`LICENSE`](./LICENSE)
- [`NOTICE`](./NOTICE)

---

## 📜 Credits

Developed by [Alvaro Del Monte](https://github.com/AlvaroMF83)  
Based on the API of [Apache Spark (PySpark)](https://spark.apache.org/docs/latest/api/python/)  
Published on PyPI as `athena_bridge`.
