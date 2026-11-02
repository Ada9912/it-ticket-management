import json

import pandas as pd
import os
import sys
from app.pipeline.runner import PipelineConfig, run_pipeline
from app.pipeline.sources import read_file, read_sql_table
import pytest

from app.pipeline.transform import (
    add_priority_rank,
    aggregate_cases,
    deduplicate_cases,
    filter_cases,
)

def write_inputs(input_dir):
    pd.DataFrame([
        {"case_id": 1, "employee_id": 10, "title": "VPN", "category": "network", "priority": "high", "status": "open", "created_at": "2026-09-19T10:00:00Z"},
        {"case_id": 2, "employee_id": 99, "title": "Unknown", "category": "network", "priority": "low", "status": "open", "created_at": "2026-09-19T10:00:00Z"},
    ]).to_csv(input_dir / "cases.csv", index=False)
    (input_dir / "employees.json").write_text(json.dumps([
        {"employee_id": 10, "employee_name": "A User", "department": "IT"},
    ]), encoding="utf-8")
    pd.DataFrame([
        {"priority": "HIGH", "sla_hours": 4, "policy_version": "v1"},
        {"priority": "LOW", "sla_hours": 24, "policy_version": "v1"},
    ]).to_csv(input_dir / "policies.csv", index=False)


def test_pipeline_quarantines_invalid_references_and_reconciles(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    write_inputs(input_dir)

    result = run_pipeline(PipelineConfig(input_dir, output_dir))

    assert result.curated_rows == 1
    assert result.rejected_rows == 1
    assert result.reconciliation_passed is True
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["reconciliation"]["passed"] is True
    rejected = pd.read_csv(output_dir / result.batch_id / "rejected" / "records.csv")
    assert rejected.iloc[0]["rejection_reason"] == "referential integrity failure"


def test_json_and_parquet_sources_are_supported(tmp_path):
    json_path = tmp_path / "records.json"
    json_path.write_text(json.dumps({"data": [{"id": 1}]}), encoding="utf-8")
    parquet_path = tmp_path / "records.parquet"
    pd.DataFrame([{"id": 2}]).to_parquet(parquet_path)

    assert read_file(json_path).to_dict(orient="records") == [{"id": 1}]
    assert read_file(parquet_path).to_dict(orient="records") == [{"id": 2}]

def test_sql_table_source_is_supported():
    database_url = os.getenv("PIPELINE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set PIPELINE_TEST_DATABASE_URL for PostgreSQL integration testing")

    frame = read_sql_table(database_url, "tickets")

    assert "case_id" in frame.columns
    assert "employee_id" in frame.columns
    assert "title" in frame.columns
    assert len(frame) > 0

def test_pandas_transformations():
    cases = pd.DataFrame([
        {"case_id": 1, "employee_id": 10, "priority": "HIGH", "status": "OPEN"},
        {"case_id": 2, "employee_id": 10, "priority": "LOW", "status": "CLOSED"},
        {"case_id": 2, "employee_id": 10, "priority": "LOW", "status": "CLOSED"},
    ])

    filtered = filter_cases(cases, "OPEN")
    assert len(filtered) == 1

    aggregated = aggregate_cases(cases)
    assert aggregated["case_count"].sum() == 3

    ranked = add_priority_rank(cases.drop_duplicates("case_id"))
    assert "priority_rank" in ranked.columns

    deduplicated = deduplicate_cases(cases)
    assert len(deduplicated) == 2

def test_pyspark_transformations():
    pytest.importorskip("pyspark")
    from pyspark.sql.types import LongType, StringType, StructField, StructType

    from app.pipeline.spark_transform import (
        add_employee_case_rank,
        aggregate_cases_by_priority,
        deduplicate_cases as spark_deduplicate_cases,
        filter_open_cases,
        handle_nulls,
        join_cases_with_employees,
    )
    from pyspark.sql import SparkSession

    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
    spark = (
        SparkSession.builder
        .master("local[1]")
        .appName("pipeline-test")
        .getOrCreate()
    )

    cases = spark.createDataFrame(
        [
            (1, 10, "HIGH", "OPEN", "Network"),
            (2, 10, "LOW", "CLOSED", "Access"),
            (2, 10, "LOW", "CLOSED", "Access"),
        ],
        ["case_id", "employee_id", "priority", "status", "category"],
    )

    employees = spark.createDataFrame(
        [
            (10, "A User", "IT"),
        ],
        ["employee_id", "employee_name", "department"],
    )

    filtered = filter_open_cases(cases)
    assert filtered.count() == 1

    joined = join_cases_with_employees(cases, employees)
    assert "employee_name" in joined.columns

    aggregated = aggregate_cases_by_priority(cases)
    assert aggregated.agg({"case_count": "sum"}).collect()[0][0] == 3

    ranked = add_employee_case_rank(cases.dropDuplicates(["case_id"]))
    assert "priority_rank" in ranked.columns

    deduplicated = spark_deduplicate_cases(cases)
    assert deduplicated.count() == 2

    null_schema = StructType(
        [
            StructField("case_id", LongType(), True),
            StructField("employee_id", LongType(), True),
            StructField("priority", StringType(), True),
            StructField("status", StringType(), True),
            StructField("category", StringType(), True),
        ]
    )

    null_cases = spark.createDataFrame(
        [(3, 10, None, None, None)],
        schema=null_schema,
    )

    handled = handle_nulls(null_cases)
    row = handled.collect()[0]

    assert row["priority"] == "UNKNOWN"
    assert row["status"] == "UNKNOWN"
    assert row["category"] == "UNKNOWN"

    spark.stop()