FROM public.ecr.aws/lambda/python:3.11

# Install system dependencies for matplotlib and other packages
RUN yum update -y && \
    yum install -y gcc gcc-c++ make && \
    yum clean all

# Copy requirements first for better caching
COPY pnl_requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY pnl_handler.py ${LAMBDA_TASK_ROOT}/
COPY utils/ ${LAMBDA_TASK_ROOT}/utils/
COPY assets/ ${LAMBDA_TASK_ROOT}/assets/

# Ensure no credential files are included in the image
RUN find ${LAMBDA_TASK_ROOT} -name "*.json" -path "*/assets/*" -delete 2>/dev/null || true

# Set the handler
CMD ["pnl_handler.lambda_handler"]