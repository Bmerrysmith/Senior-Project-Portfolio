FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY auth/ ${LAMBDA_TASK_ROOT}/auth/
COPY graph/ ${LAMBDA_TASK_ROOT}/graph/
COPY ingest/ ${LAMBDA_TASK_ROOT}/ingest/
COPY triage/ ${LAMBDA_TASK_ROOT}/triage/
COPY digest/ ${LAMBDA_TASK_ROOT}/digest/
COPY config.py lambda_handler.py ${LAMBDA_TASK_ROOT}/

CMD ["lambda_handler.handler"]
