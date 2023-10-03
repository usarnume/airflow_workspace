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

# https://airflow.apache.org/docs/apache-airflow/stable/templates-ref.html

with DAG(
dag_id="capstone_project",
start_date = pendulum.today('UTC').add(days=-10),
description='Capstone Project',
schedule="@daily",
) as dag:

    call_http_status = HttpSensor(task_id="call_http_status_space_devs_api", http_conn_id="thespacedevs_dev", endpoint="", dag=dag)
    
    # the simple http operator automtically passes output to XCom (can check return there)
    # https://lldev.thespacedevs.com/2.2.0/launch/ --> click on "filter"
    # you can check the results in the XCom (webinterface)
    call_space_devs_api = SimpleHttpOperator(
        task_id="call_space_devs_api", 
        http_conn_id="thespacedevs_dev", 
        method="GET",
        data={"net__gt": "{{ ds }}T00:00:00Z", "net__lt": "{{ next_ds }}T00:00:00Z"},
        log_response=True,
        endpoint="", 
        dag=dag)

    def _check_if_data_in_request(task_instance, **context):

        response = task_instance.xcom_pull(task_ids="call_space_devs_api",
                                           key="return_value")
        print(response, type(response))
        response_dict = json.loads(response)

        if response_dict["count"] == 0:
            raise AirflowSkipException(f"No launches for today {context['ds']}.")


    check_results = PythonOperator(task_id="check_results",
                                         python_callable=_check_if_data_in_request,
                                         provide_context=True,
                                         dag=dag)


    def _extract_relevant_data(x: dict):
        return {"id": x.get("id"),
                "name": x.get("name"),
                "status.abbrev": x.get("status.abbrev"),
                "mission.agencies.country_code": x.get("mission.agencies.country_code"),
                "launch_service_provider.name": x.get("launch_service_provider.name"),
                "launch_service_provider.type": x.get("launch_service_provider.type")}


    def _preprocess_data(task_instance, **context):
        response = task_instance.xcom_pull(task_ids="call_space_devs_api")
        response_dict = json.loads(response)
        response_results = response_dict["results"]
        df_results = pd.DataFrame([_extract_relevant_data(i) for i in response_results])
        df_results.to_parquet(path=f"/tmp/{context['ds']}.parquet")

    preprocess_data = PythonOperator(
        task_id="preprocess_data",
        python_callable=_preprocess_data,
        dag=dag
    )


    call_http_status >> call_space_devs_api >> check_results



    
