from airflow.operators.empty import EmptyOperator
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.models import DAG
import pendulum
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.http.operators.http import SimpleHttpOperator


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

    call_http_status >> call_space_devs_api



    
