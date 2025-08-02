# Container approach for heavy dependencies like pandas
FROM public.ecr.aws/lambda/python:3.9

# Copy requirements and install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r requirements.txt

# Copy function code and scripts
COPY handler.py ${LAMBDA_TASK_ROOT}
COPY scripts/ ${LAMBDA_TASK_ROOT}/scripts/

# Set the CMD to your handler
CMD ["handler.lambda_handler"]