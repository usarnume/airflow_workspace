from airflow.operators.empty import EmptyOperator
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.models import DAG
import pendulum
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.operators.python import ShortCircuitOperator
import json
from airflow.exceptions import AirflowSkipException
import pandas as pd
from airflow.providers.google.cloud.operators.bigquery import BigQueryCreateEmptyDatasetOperator
from airflow.providers.google.cloud.transfers.local_to_gcs import LocalFilesystemToGCSOperator
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.hooks.postgres_hook import PostgresHook

# Templates reference
# https://airflow.apache.org/docs/apache-airflow/stable/templates-ref.html


# we have 3 connections:
# google_cloud_conn	
# postgres
# thespacedevs_dev



with DAG(
dag_id="capstone_project",
start_date = pendulum.today('UTC').add(days=-10),
description='Capstone Project',
schedule="@daily",
) as dag:

    # Part 1
    call_http_status = HttpSensor(task_id="call_http_status_space_devs_api", http_conn_id="thespacedevs_dev", endpoint="", dag=dag)
    

    # Part 2
    # the simple http operator automtically passes output to XCom (can check return there)
    # https://lldev.thespacedevs.com/2.2.0/launch/ --> click on "filter"
    # you can check the results in the XCom (webinterface)

    # https://airflow.apache.org/docs/apache-airflow-providers-http/stable/_api/airflow/providers/http/operators/http/index.html#airflow.providers.http.operators.http.SimpleHttpOperator
    call_space_devs_api = SimpleHttpOperator(
        task_id="call_space_devs_api", 
        http_conn_id="thespacedevs_dev", 
        method="GET",
        data={"net__gt": "{{ ds }}T00:00:00Z", "net__lt": "{{ next_ds }}T00:00:00Z"},
        log_response=True,
        endpoint="")


    # Part 3
    # Two parts:
    # a) check if there is any data
    # b) pre-process the data
    def _check_if_data_in_request(task_instance, **context):

        response = task_instance.xcom_pull(task_ids="call_space_devs_api", # the output in XCom is coming from this task
                                           key="return_value")
        response_dict = json.loads(response)

        if response_dict["count"] == 0:
            raise AirflowSkipException(f"No launches for today {context['ds']}.")


    check_results = PythonOperator(task_id="check_results",
                                         python_callable=_check_if_data_in_request,
                                         provide_context=True)

    def _extract_relevant_data(x: dict):
        return {"id": x.get("id"),
                "name": x.get("name"),
                "status_abbrev": x.get("status.abbrev"),
                "country_code": x.get("pad").get("location").get("country_code"),
                "service_provider_name": x.get("launch_service_provider").get("name"),
                "service_provider_type": x.get("launch_service_provider").get("type")}


    def _preprocess_data(task_instance, **context):
        response = task_instance.xcom_pull(task_ids="call_space_devs_api", key="return_value") # the output in XCom is coming from this task
        response_dict = json.loads(response)
        response_results = response_dict["results"]
        df_results = pd.DataFrame([_extract_relevant_data(i) for i in response_results])
        df_results.to_parquet(path=f"/tmp/{context['ds']}.parquet") # note the slash at the beginning + if re-runs it overwrites

    preprocess_data = PythonOperator(
        task_id="preprocess_data",
        python_callable=_preprocess_data)


    # Step 4: create empty dataset on Google Cloud Storage
    create_empty_dataset = BigQueryCreateEmptyDatasetOperator(task_id="create_dataset", 
                                                              gcp_conn_id="google_cloud_conn",
                                                              dataset_id="maurits_dataset")

    # Step 5: writing data to the empty table
    upload_file = LocalFilesystemToGCSOperator(
        task_id="upload_file_to_gcs",
        src="/tmp/{{ ds }}.parquet",
        dst="maurits_dataset/{{ ds }}.parquet",
        bucket="aflow-training-rabo-2023-10-02",
        gcp_conn_id='google_cloud_conn', # defined remote
    )

    # Step 6: write parquet to big query
    gcs_to_big_query_operator = GCSToBigQueryOperator(
        task_id="write_parquet_to_bq",
        gcp_conn_id="google_cloud_conn",
        bucket="aflow-training-rabo-2023-10-02",
        source_objects=["maurits_dataset/{{ ds }}.parquet"],
        source_format="parquet",
        destination_project_dataset_table="aflow-training-rabo-2023-10-02.maurits_dataset.rocket_launches",
        write_disposition="WRITE_APPEND"
    )

    # Step 7: create postgres table
    # https://airflow.apache.org/docs/apache-airflow-providers-postgres/stable/operators/postgres_operator_howto_guide.html
    create_postgres_table = PostgresOperator(
        task_id="create_postgres_table",
        postgres_conn_id="postgres",
        sql="""
        CREATE TABLE IF NOT EXISTS rocket_launches (
            id VARCHAR,
            name VARCHAR,
            status VARCHAR,
            country_code VARCHAR,
            service_provider_name VARCHAR,
            service_provider_type VARCHAR
            );
        """
    )


    # Step 8: write the parquet to postgres
    def _read_parquet_and_write_to_postgres(task_instance, **context):
        # Read data from parquet
        df_launches = pd.read_parquet(f"/tmp/{context['ds']}.parquet")
        df_launches.to_csv(f"/tmp/{context['ds']}.csv", header=False, index=False)

        # https://airflow.apache.org/docs/apache-airflow/1.10.10/_api/airflow/hooks/postgres_hook/index.html
        hook = PostgresHook(postgres_conn_id="postgres")
        hook.copy_expert(f"COPY rocket_launches (id, name, status, country_code, service_provider_name, service_provider_type) FROM STDIN WITH CSV DELIMITER AS ','", f"/tmp/{context['ds']}.csv")

    write_parquet_to_postgres = PythonOperator(
        task_id="write_parquet_to_postgres",
        python_callable=_read_parquet_and_write_to_postgres
    )


    # definition of the dag
    (
    call_http_status >> 
    call_space_devs_api >> 
    check_results >> 
    preprocess_data >>
    create_empty_dataset >> 
    upload_file >> 
    gcs_to_big_query_operator >>
    create_postgres_table >>
    write_parquet_to_postgres
    )


    
