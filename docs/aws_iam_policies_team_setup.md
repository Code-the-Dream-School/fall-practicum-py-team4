# AWS IAM Policies & Team Deployment Setup (`City Air Tracker`)

## Architecture Guardrails: What Protects What & Who Can Access What

To enforce least-privilege access across both the batch ETL pipeline and the Streamlit dashboard, permissions and safeguards are separated across human operators, scoped deployment roles, runtime compute (AWS Lambda and AWS ECS Fargate), container registries, and billing controls (AWS Account `037590970192`, Region `us-east-2`):

### 1. Developers (`POWERUSER` Group & `EtlDeployRole`)

* **Who:** Team IAM users in the `POWERUSER` user group using their standard AWS credentials for console access and dashboard operations, and assuming `EtlDeployRole` (`arn:aws:iam::037590970192:role/EtlDeployRole`) via short-lived STS credentials for batch ETL updates.

* **Can Access:**

  * **Baseline Human & Console Access (`POWERUSER` + `LambdaReadOnlyConsoleAccess`):** AWS Console login via the account IAM sign-in URL, self-service password management, CloudTrail event lookup, and read-only Lambda console visibility (`lambda:ListFunctions`, `lambda:GetFunction`, `lambda:GetFunctionConfiguration`, `lambda:ListTags`) for monitoring without write/deploy privileges.

  * **Direct Dashboard Operations & Observability (`DashboardTeamAccess` inline policy on `POWERUSER`):** Grants teammates direct permissions using their default AWS credentials (no `sts:AssumeRole` required) to:

    * **Inspect Logs & Troubleshoot Issues:** View CloudWatch log groups and read/filter log streams in `arn:aws:logs:us-east-2:037590970192:log-group:/ecs/py4-dashboard-task:*` (`logs:DescribeLogGroups`, `logs:DescribeLogStreams`, `logs:GetLogEvents`, `logs:FilterLogEvents`), inspect ECS service events and stopped-task exit reasons (`ecs:DescribeServices`, `ecs:DescribeTasks`), and look up task ENI public IP addresses (`ec2:DescribeNetworkInterfaces`).

    * **Start, Stop & Deploy Dashboard Updates:** Scale `py4-dashboard-task-service-k8ei2rie` between `0` and `1` tasks (`ecs:UpdateService`, `ecs:StopTask`), register new revisions of `py4-dashboard-task` (`ecs:RegisterTaskDefinition`), and pass `EcsDashboardExecutionRole` (`iam:PassRole` conditioned on `ecs-tasks.amazonaws.com`).

    * **Push Dashboard Container Images:** Authenticate to ECR (`ecr:GetAuthorizationToken`) and push/inspect images in `arn:aws:ecr:us-east-2:037590970192:repository/fall-practicum-py-team4-dashboard`.

  * **Scoped ETL Deployment Access (`EtlDeployRole` via `sts:AssumeRole`):** Short-lived session tokens (`--profile etl-deploy`) scoped strictly to:

    * Pushing container images to `arn:aws:ecr:us-east-2:037590970192:repository/fall-practicum-py-team4` (`ecr:GetAuthorizationToken`, layer upload, and `ecr:PutImage`).

    * Creating, updating, inspecting, and test-invoking `arn:aws:lambda:us-east-2:037590970192:function:etl-pipeline` (`lambda:CreateFunction`, `lambda:UpdateFunctionCode`, `lambda:UpdateFunctionConfiguration`, `lambda:GetFunction`, `lambda:InvokeFunction`).

    * Passing only the ETL runtime execution role (`iam:PassRole` on `arn:aws:iam::037590970192:role/EtlLambdaRole`).

* **Restrictions:** Long-lived IAM user CLI access keys cannot touch `etl-pipeline` without assuming `EtlDeployRole`. Developers cannot modify IAM roles or policies, read SSM Parameter Store secrets directly, or push/modify unrelated AWS resources. Secrets are never hardcoded in repositories or container images.

### 2. Runtime Execution — Batch ETL (`etl-pipeline` AWS Lambda & `EtlLambdaRole`)

* **Who / What:** The `etl-pipeline` container Lambda function (`512 MB` memory, `300s` timeout, `x86_64`) assuming `EtlLambdaRole` (`arn:aws:iam::037590970192:role/EtlLambdaRole`) at runtime.

* **Can Access:**

  * **AWS Systems Manager (SSM) Parameter Store:** Read-only (`ssm:GetParameter` / `ssm:GetParameters`) access scoped strictly to the 5 pipeline secrets (encrypted via KMS `SecureString`), including Supabase credentials, OpenWeather API key, and OpenRouter API key.

  * **Amazon CloudWatch Logs:** Write-only (`logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`) to `/aws/lambda/etl-pipeline` to emit structured pipeline run logs.

  * **External APIs & Database:** Outbound HTTPS access to Open-Meteo, OpenWeather, OpenRouter (`openrouter/free` model router), and Supabase PostgreSQL.

* **What It Protects:** Prevents the running Lambda container from modifying AWS infrastructure, reading unrelated SSM parameters, or pushing/deleting ECR images.

### 3. Runtime Execution — Streamlit Dashboard (`py4-dashboard` ECS Fargate & `EcsDashboardExecutionRole`)

* **Who / What:** Containerized Streamlit web dashboard deployed on AWS ECS Fargate (`py4-dashboard-cluster`, task definition `py4-dashboard-task`, service `py4-dashboard-task-service-k8ei2rie`, `0.5 vCPU`, `1 GB` RAM, `Linux/X86_64`, container port `8501`), using `EcsDashboardExecutionRole` (`arn:aws:iam::037590970192:role/EcsDashboardExecutionRole`) during task startup and logging.

* **Can Access:**

  * **ECS Agent Infrastructure Permissions (`AmazonECSTaskExecutionRolePolicy`):** AWS managed execution policy granting the ECS Fargate agent permission to pull container images from `fall-practicum-py-team4-dashboard` in ECR and stream `stdout`/`stderr` container logs to CloudWatch Logs (`/ecs/py4-dashboard-task`).

  * **Scoped SSM Parameter Store Secrets (`ReadSupabaseSsmParams` inline policy):** Batch read-only (`ssm:GetParameters`) access restricted strictly to `arn:aws:ssm:us-east-2:037590970192:parameter/SUPABASE_URL` and `arn:aws:ssm:us-east-2:037590970192:parameter/SUPABASE_KEY`, injected as environment variables (`ValueFrom`) before container startup.

  * **Application Task Role (`None`):** No task IAM role is attached because the Streamlit application connects to Supabase exclusively over HTTPS (`supabase-py`) and makes zero AWS SDK/API calls at runtime.

  * **Network Security Group (`py4-dashboard-sg`):** Attached to the Fargate task's Elastic Network Interface (ENI) in the default VPC with public IPv4 enabled (direct access at `http://<PUBLIC_IP>:8501` without an Application Load Balancer), allowing inbound `Custom TCP` traffic solely on port `8501`.

* **What It Protects:** Isolates the web-facing dashboard from ETL-only secrets (`OPENWEATHER_API_KEY`, `OPENROUTER_API_KEY`), denies AWS API permissions inside the container, and exposes only Streamlit port `8501`.

### 4. Container Registries & Secrets Storage (ECR & SSM Parameter Store)

* **Amazon ECR — Batch ETL (`fall-practicum-py-team4`):** Protected by a repository resource policy (`LambdaECRImageRetrievalPolicy`) granting `lambda.amazonaws.com` read-only pull permissions (`ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`) conditioned strictly on `aws:sourceArn` matching `arn:aws:lambda:us-east-2:037590970192:function:etl-pipeline`.

* **Amazon ECR — Streamlit Dashboard (`fall-practicum-py-team4-dashboard`):** Dedicated repository (`037590970192.dkr.ecr.us-east-2.amazonaws.com/fall-practicum-py-team4-dashboard`) configured with **immutable image tags** plus a **tag immutability exclusion filter for `latest`**. Because the dashboard scales to `0` tasks between demos, `py4-dashboard-task` (Revision `2+`) points directly to the `:latest` tag (`037590970192.dkr.ecr.us-east-2.amazonaws.com/fall-practicum-py-team4-dashboard:latest`) rather than pinning a `@sha256:` digest or incremental version tags—allowing every `0 -> 1` scale-up to pull the newest pushed image automatically without creating new task definition revisions. Pulled by `EcsDashboardExecutionRole` during Fargate task launch.

* **ECR Lifecycle Policies (3-Image Retention):** Both `fall-practicum-py-team4-dashboard` and `fall-practicum-py-team4` enforce a lifecycle policy (`rulePriority: 1`, `tagStatus: "any"`, `imageCountMoreThan: 3`, `action: "expire"`) that retains only the 3 most recently pushed images per repository and automatically deletes older or untagged layers left behind whenever `:latest` is overwritten (evaluated asynchronously by AWS within 24 hours).

* **SSM Parameter Store:** 5 root-level production secrets (`SUPABASE_URL`, `SUPABASE_KEY`, `OPENWEATHER_API_KEY`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`) stored as `SecureString` parameters. Accessible only by `EtlLambdaRole` (all 5), `EcsDashboardExecutionRole` (`SUPABASE_URL` and `SUPABASE_KEY` only), and authorized IAM admins. Secrets are never baked into Docker images or committed to GitHub.

### 5. Automation, Monitoring & Cost Protection

* **Amazon EventBridge:** Scheduled trigger rule granted explicit resource-based permission (`lambda:InvokeFunction`) solely to invoke `etl-pipeline` on its batch schedule (kept `Disabled` during migration until the Prefect-free handler image is pushed).

* **Amazon CloudWatch Alarms & Logging:**

  * Monitors the `etl-pipeline` Lambda `Errors` metric (`Sum >= 1` over 5 minutes) and triggers an SNS email notification if an execution fails, protecting against silent pipeline outages.

  * Container Insights monitoring on `py4-dashboard-cluster` is disabled to avoid extra CloudWatch custom metric and performance log ingestion charges while retaining standard service metrics and `/ecs/py4-dashboard-task` container logs.

* **ECS Scale-to-Zero Cost Control (`py4-dashboard`):** Because ECS charges no idle cluster orchestration fee, `py4-dashboard-task-service-k8ei2rie` is scaled to `Desired tasks = 0` (`--desired-count 0`) between active demos and reviews—reducing Fargate vCPU, memory, and public IPv4 charges to **\$0.00** while preserving the cluster, task definition, SSM secret mappings, and security group.

* **ECR Storage Hygiene:** The 3-image lifecycle retention rule prevents unbounded ECR storage buildup from superseded `:latest` image digests.

* **AWS Budgets:** Configured with a **\$10.00 monthly cost threshold alarm** to alert the team early against unexpected Lambda, Fargate, ECR, or CloudWatch spend.

---

## Local Developer CLI & Docker Build Setup

*(All CLI commands below use standard **Bash** syntax, compatible with macOS, Linux, WSL, and Windows Git Bash.)*

### 1. Configure `~/.aws/config` for Role Assumption

Dashboard commands use `[default]` directly via the `POWERUSER` group's `DashboardTeamAccess` policy, while ETL Lambda deployments assume `EtlDeployRole` via `[profile etl-deploy]`:

```ini
[default]
region = us-east-2
output = json

[profile etl-deploy]
role_arn = arn:aws:iam::037590970192:role/EtlDeployRole
source_profile = default
region = us-east-2
output = json
```

### 2. Configure `amazon-ecr-credential-helper` (`ecr-login`)

Map the account ECR registry under `credHelpers` in `~/.docker/config.json` so `docker push` fetches short-lived ECR tokens automatically via active AWS CLI credentials (do **not** run `docker login`, as `ecr-login` intentionally leaves credential storage unimplemented):

```json
{
  "credsStore": "desktop",
  "credHelpers": {
    "037590970192.dkr.ecr.us-east-2.amazonaws.com": "ecr-login"
  }
}
```

### 3. Build & Push Batch ETL Lambda Images (`fall-practicum-py-team4`)

1. **Build a Lambda-Compatible Image & Push to ECR:**
   Sets the active shell session to the short-lived `etl-deploy` STS profile (used automatically by `ecr-login`), builds a single-architecture `linux/amd64` image without multi-manifest OCI provenance/SBOM attestations (which Lambda rejects with `InvalidParameterValueException`), and pushes it to ECR:
   ```bash
   export AWS_PROFILE=etl-deploy
   docker buildx build \
     --platform linux/amd64 \
     --provenance=false \
     --sbom=false \
     -t 037590970192.dkr.ecr.us-east-2.amazonaws.com/fall-practicum-py-team4:latest \
     --push .
   ```

2. **Deploy the New Image Digest to `etl-pipeline`:**
   Because AWS Lambda stays locked to its previous `@sha256:` digest even after `:latest` is overwritten in ECR, run `update-function-code` to swap the function onto the newly pushed build:
   ```bash
   aws lambda update-function-code \
     --function-name etl-pipeline \
     --image-uri 037590970192.dkr.ecr.us-east-2.amazonaws.com/fall-practicum-py-team4:latest \
     --profile etl-deploy \
     --region us-east-2
   ```

3. **Verify the Function Update Completed:**
   Lambda swaps container images asynchronously. Poll `get-function` until `State` reads `"Active"` and `LastUpdateStatus` reads `"Successful"` (confirming `300`s timeout and `512` MB memory) before triggering a test run:
   ```bash
   aws lambda get-function \
     --function-name etl-pipeline \
     --query "Configuration.{State:State,LastUpdateStatus:LastUpdateStatus,Timeout:Timeout,MemorySize:MemorySize}" \
     --profile etl-deploy \
     --region us-east-2
   ```

### 4. Build, Test & Push Streamlit Dashboard Images (`fall-practicum-py-team4-dashboard`)

*(Note: Keep `SUPABASE_URL` and `SUPABASE_KEY` unquoted in the root `.env` file so `docker run --env-file` passes clean strings without literal quote characters. Ensure `AWS_PROFILE` is unset or set to `default` so `ecr-login` uses your `POWERUSER` credentials.)*

1. **Build & Sanity-Check Locally** (from `services/pipeline/dashboard`):
   ```bash
   docker build -f Docker.dashboard -t city-air-dashboard .
   docker run --rm -p 8501:8501 --env-file ../../../.env city-air-dashboard
   ```

2. **Tag & Push as `:latest` to ECR:**
   ```bash
   docker tag city-air-dashboard:latest 037590970192.dkr.ecr.us-east-2.amazonaws.com/fall-practicum-py-team4-dashboard:latest
   docker push 037590970192.dkr.ecr.us-east-2.amazonaws.com/fall-practicum-py-team4-dashboard:latest
   ```

   * **How updates take effect:** Because `py4-dashboard-task-service-k8ei2rie` stays scaled to `0` between sessions, scaling it back to `1` (`--desired-count 1`) automatically launches a fresh Fargate task using the newly pushed `:latest` image—no new task definition revision is required. *(If you ever push `:latest` while a task is already running at `desired-count 1`, append `--force-new-deployment` to `aws ecs update-service` to cycle the container.)*

   * **AWS Console caveat:** If editing `py4-dashboard-task` in the ECS Console, enter the `:latest` tag URI manually rather than accepting the ECR image picker's `@sha256:...` digest, which would permanently lock the task definition to a single build.

### 5. Start, Inspect, View Logs & Stop the ECS Fargate Dashboard (`py4-dashboard-cluster`)

```bash
# 1. Start the dashboard service (1 Fargate task, automatically pulling :latest)
aws ecs update-service --cluster py4-dashboard-cluster --service py4-dashboard-task-service-k8ei2rie --desired-count 1 --region us-east-2

# 2. Fetch the newly assigned ephemeral Public IP once the task reaches RUNNING (open http://<PUBLIC_IP>:8501)
TASK=$(aws ecs list-tasks --cluster py4-dashboard-cluster --region us-east-2 --query "taskArns[0]" --output text)
ENI=$(aws ecs describe-tasks --cluster py4-dashboard-cluster --tasks "$TASK" --region us-east-2 --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text)
aws ec2 describe-network-interfaces --network-interface-ids "$ENI" --region us-east-2 --query "NetworkInterfaces[0].Association.PublicIp" --output text

# 3. Inspect recent Streamlit container logs if troubleshooting issues
aws logs tail /ecs/py4-dashboard-task --since 30m --region us-east-2

# 4. Stop the dashboard service after demos/testing to pause Fargate billing ($0.00/hr)
aws ecs update-service --cluster py4-dashboard-cluster --service py4-dashboard-task-service-k8ei2rie --desired-count 0 --region us-east-2
```

### 6. ECR Image Lifecycle Policy Reference (`Keep Last 3 Images`)

Both ECR repositories (`fall-practicum-py-team4-dashboard` and `fall-practicum-py-team4`) enforce the following lifecycle rule to purge untagged/older images beyond the 3 most recent pushes:

```bash
cat << 'EOF' > lifecycle.json
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Keep only the 3 most recently pushed images",
      "selection": {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": 3
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}
EOF

aws ecr put-lifecycle-policy --repository-name fall-practicum-py-team4-dashboard --lifecycle-policy-text file://lifecycle.json --region us-east-2
aws ecr put-lifecycle-policy --repository-name fall-practicum-py-team4 --lifecycle-policy-text file://lifecycle.json --region us-east-2
rm -f lifecycle.json
```