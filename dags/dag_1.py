from airflow.operators.empty import EmptyOperator
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.models import DAG
import pendulum

with DAG(
dag_id="hello_world",
start_date = pendulum.today('UTC').add(days=-14),
description='This DAG will print "Hello“ & "World".',
schedule="@daily",
) as dag:

    def _print_exec_date(**context):
        print(f"This script was executed at {context['execution_date']}")

    procure_rocket_material = EmptyOperator(task_id="procure_rocket_material", dag=dag)
    build_stage_1 = BashOperator(task_id="build_stage_1", bash_command="echo '{{ task }} is running in the {{ dag }} pipeline'", dag=dag)
    build_stage_2 = PythonOperator(task_id="build_stage_2", python_callable=_print_exec_date, provide_context=True, dag=dag)
    build_stage_3 = EmptyOperator(task_id="build_stage_3", dag=dag)
    procure_fuel = EmptyOperator(task_id="procure_fuel", dag=dag)
    launch = EmptyOperator(task_id="launch", dag=dag)

    procure_rocket_material >> [build_stage_1, build_stage_2, build_stage_3]
    procure_fuel >> build_stage_3
    [build_stage_1, build_stage_2, build_stage_3] >> launch


