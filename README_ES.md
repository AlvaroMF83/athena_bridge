[![PyPI version](https://img.shields.io/pypi/v/athena_bridge.svg)](https://pypi.org/project/athena_bridge/)
[![Python versions](https://img.shields.io/pypi/pyversions/athena_bridge.svg)](https://pypi.org/project/athena_bridge/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Downloads](https://pepy.tech/badge/athena_bridge)](https://pepy.tech/project/athena_bridge)
[![GitHub stars](https://img.shields.io/github/stars/<tuusuario>/athena_bridge.svg?style=social&label=Star)](https://github.com/AlvaroMF83/athena_bridge)

# 🪶 athena_bridge

[🇬🇧 Read in English](./README.md)

**athena_bridge** es una librería open source en Python que replica las funciones más comunes de **PySpark**, permitiendo ejecutar código PySpark directamente sobre **AWS Athena** mediante SQL autogenerado.

Gracias a esta librería, puedes **reutilizar tu código PySpark sin necesidad de un cluster EMR o Glue Interactive Session**, aprovechando el backend de Athena con sintaxis idéntica a PySpark.

---

## ✨ Características principales
- Replica la mayoría de funciones de `pyspark.sql.functions`, `DataFrame`, `Column` y `Window`.
- Permite migrar código PySpark existente a entornos sin Spark.
- Traduce operaciones PySpark a consultas **Athena SQL** ejecutadas mediante `awswrangler`.
- Compatible con **Python ≥ 3.8** y **AWS Athena / Glue Catalog**.

---

## 📦 Instalación
Disponible en [PyPI](https://pypi.org/project/athena-bridge/):

```bash
pip install athena_bridge
```

### Dependencias
- `awswrangler`
- `boto3`
- `pandas`

---

## ⚙️ Configuración de AWS

Para ejecutar consultas con athena_bridge desde Amazon SageMaker, el rol de ejecución (AmazonSageMaker-ExecutionRole-xxxxxxxxxxxxx) debe tener los permisos necesarios sobre Glue, Athena y S3.

Asegúrate de editar el rol y añadir una política como la siguiente (recuerda reemplazar los identificadores de cuenta y los nombres de bucket por los tuyos propios).

Ejemplo (anonimizado) de **rol IAM**:

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


> ⚠️ **Nota:** se recomienda restringir los recursos (`Resource`) a los buckets, bases de datos y workgroups específicos utilizados.


Para garantizar que todas las consultas de Athena (incluidas las operaciones UNLOAD y CTAS) almacenen sus resultados únicamente en el bucket S3 definido, es necesario activar la opción “Invalidar la configuración del cliente / Enforce workgroup configuration” en la configuración del Workgroup de Athena.
Esta opción impide que los clientes (como boto3 o awswrangler) modifiquen la ubicación de salida de los resultados y asegura que todos los ficheros generados por las consultas se escriban siempre en la ruta S3 establecida en el Workgroup.
Si no se activa esta opción, los comandos UNLOAD pueden escribir ficheros temporales (por ejemplo, .csv, .metadata, .manifest) en ubicaciones no deseadas, lo que puede provocar errores o corrupción en los conjuntos de datos Parquet.

---

## 🚀 Uso rápido

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
 
💡 **Nota**:
Asegúrate de que en tu Workgroup de Athena esté activada la opción **“Invalidar la configuración del cliente / Enforce workgroup configuration”**, para que todas las consultas y operaciones UNLOAD utilicen siempre la ruta S3 configurada en el propio workgroup y no escriban archivos auxiliares fuera de esa ubicación.

🧠 **Resultado**:
El código inicializa una sesión tipo Spark conectada a Athena, lee datos desde S3 (por ejemplo en formato CSV), los escribe en formato Parquet, y permite realizar operaciones con sintaxis similar a PySpark (como withColumn, filter, show).
Los resultados se ejecutan sobre Athena y se muestran directamente en el entorno de ejecución (por ejemplo, en SageMaker o un notebook local).

---

## 🧰 Compatibilidad con PySpark

La librería implementa una gran parte de las funciones nativas de PySpark.  
Puedes consultar la lista completa de funciones implementadas con enlaces a la documentación oficial:

| Módulo | Funciones disponibles | Enlace |
|--------|----------------------|---------|
| `functions` | +100 funciones de PySpark: matemáticas, strings, fechas, colecciones... | [functions.html](./documentation/Functions.html) |
| `dataframe` | Métodos de DataFrame (`select`, `filter`, `join`, `show`, etc.) | [dataframe.html](./documentation/DataFrame.html) |
| `column` | Operaciones y expresiones sobre columnas | [column.html](./documentation/Column.html) |
| `window` | Funciones de ventana básicas (`partitionBy`, `orderBy`) | [window.html](./documentation/Window.html) |

Cada enlace incluye referencias directas a la documentación oficial de PySpark para facilitar la migración.

---

## ⚠️ Diferencias con PySpark

- Las operaciones se ejecutan en Athena, no en un cluster Spark distribuido.
- Algunas funciones avanzadas (por ejemplo, `collect_set`, `rdd`, `pivot`) no están implementadas.
- No se soportan operaciones que dependan de *stateful streaming* o *RDDs*.
- El rendimiento depende de los límites y tiempos de ejecución de Athena.

---

## 🧪 Ejemplo ampliado (desde Jupyter/SageMaker)

Consulta el notebook [`Ejemplo_finn_athena_bridge_usando_dataproc.ipynb`](./Ejemplo_finn_athena_bridge_usando_dataproc.ipynb) para ver:
- cómo conectarte con `boto3` y `awswrangler`,
- crear DataFrames a partir de resultados de Athena,
- y combinar funciones de `athena_bridge` con `pandas`.

---

## 🔐 Licencia

Este proyecto está licenciado bajo **Apache License 2.0**.

Incluye parte de la interfaz pública de **Apache Spark (PySpark)** bajo los mismos términos.

Consulta los archivos:
- [`LICENSE`](./LICENSE)
- [`NOTICE`](./NOTICE)

---

## 📜 Créditos

Desarrollado por [Alvaro Del Monte](https://github.com/AlvaroMF83)  
Basado en la API de [Apache Spark (PySpark)](https://spark.apache.org/docs/latest/api/python/)  
Publicado en PyPI como `athena_bridge`.
