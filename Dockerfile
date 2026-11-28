FROM public.ecr.aws/lambda/python:3.11

# ${LAMBDA_TASK_ROOT} resolves to /var/task in AWS Lambda
WORKDIR ${LAMBDA_TASK_ROOT}

# Install system dependencies if needed
# RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt --prefer-binary

COPY . .

# Point AWS Lambda directly to the handler function (module.path.function_name)
CMD ["services.pipeline.handler.lambda_handler"]