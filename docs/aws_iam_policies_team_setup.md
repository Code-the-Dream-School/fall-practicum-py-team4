# AWS IAM Policies & Team Deployment Setup (`City Air Tracker`)

## Architecture Guardrails: What Protects What & Who Can Access What

To enforce least-privilege access before production deployment, permissions and safeguards are separated across human operators, scoped deployment roles, runtime compute, registry policies, and billing controls (AWS Account `037590970192`, Region `us-east-2`):

### 1. Developers (`POWERUSER` Group & `EtlDeployRole`)
* **Who:** Team IAM users in the `POWERUSER` group assuming the dedicated `EtlDeployRole` (`arn:aws:iam::037590970192:role/EtlDeployRole`) via short-lived STS credentials.
* **Can Access:**
  * **Baseline Human Access (`POWERUSER` + `LambdaReadOnlyConsoleAccess`):** AWS Console login via the account IAM sign-in URL, self-service password management, CloudTrail event lookup, and read-only Lambda console visibility (`lambda:ListFunctions`, `lambda:GetFunction`, `lambda:GetFunctionConfiguration`, `lambda:ListTags`) for monitoring without write/deploy privileges.
  * **Scoped Deployment Access (`EtlDeployRole` via `sts:AssumeRole`):** Short-lived session tokens scoped strictly to:
    * Pushing container images to `arn:aws:ecr:us-east-2:037590970192:repository/fall-practicum-py-team4` (`ecr:GetAuthorizationToken`, layer upload, and `ecr:PutImage`).
    * Creating, updating, inspecting, and test-invoking `arn:aws:lambda:us-east-2:037590970192:function:etl-pipeline` (`lambda:CreateFunction`, `lambda:UpdateFunctionCode`, `lambda:UpdateFunctionConfiguration`, `lambda:GetFunction`, `lambda:InvokeFunction`).
    * Passing only the runtime execution role (`iam:PassRole` on `arn:aws:iam::037590970192:role/EtlLambdaRole`).
* **Restrictions:** Long-lived IAM user CLI access keys are replaced by short-lived STS role sessions (`--profile etl-deploy`). Developers cannot modify IAM roles/policies, read SSM secrets directly, or push/modify unrelated AWS resources. Credentials are never hardcoded in repositories or container images.

### 2. Runtime Execution (`etl-pipeline` AWS Lambda & `EtlLambdaRole`)
* **Who / What:** The `etl-pipeline` container Lambda function (`512 MB` memory, `300s` timeout, `x86_64`) assuming `EtlLambdaRole` (`arn:aws:iam::037590970192:role/EtlLambdaRole`) at runtime.
* **Can Access:**
  * **AWS Systems Manager (SSM) Parameter Store:** Read-only (`ssm:GetParameter` / `ssm:GetParameters`) access scoped strictly to the 5 pipeline secrets (encrypted via KMS `SecureString`), including Supabase credentials, OpenWeather API key, and OpenRouter API key.
  * **Amazon CloudWatch Logs:** Write-only (`logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`) to `/aws/lambda/etl-pipeline` to emit structured pipeline run logs.
  * **External APIs & Database:** Outbound HTTPS access to Open-Meteo, OpenWeather, OpenRouter (`openrouter/free` model router), and Supabase PostgreSQL.
* **What It Protects:** Prevents the running container from modifying AWS infrastructure, reading unrelated SSM parameters, or pushing/deleting ECR images.

### 3. Container Registry & Secrets Storage (ECR & SSM Parameter Store)
* **Amazon ECR (`fall-practicum-py-team4`):** Protected by a repository resource policy (`LambdaECRImageRetrievalPolicy`) granting `lambda.amazonaws.com` read-only pull permissions (`ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`) conditioned strictly on `aws:sourceArn` matching `arn:aws:lambda:us-east-2:037590970192:function:etl-pipeline`.
* **SSM Parameter Store:** 5 production secrets stored as `SecureString` parameters. Accessible only by `EtlLambdaRole` at runtime and authorized IAM admins. Secrets are never baked into the Docker image or committed to GitHub.

### 4. Automation, Monitoring & Cost Protection
* **Amazon EventBridge:** Scheduled trigger rule granted explicit resource-based permission (`lambda:InvokeFunction`) solely to invoke `etl-pipeline` on its batch schedule (kept `Disabled` during migration until the Prefect-free handler image is pushed).
* **Amazon CloudWatch Alarms:** Monitors the `etl-pipeline` Lambda `Errors` metric (`Sum >= 1` over 5 minutes) and triggers an SNS email notification if an execution fails, protecting against silent pipeline outages.
* **AWS Budgets:** Configured with a **$10.00 monthly cost threshold alarm** to alert the team early against unexpected Lambda, ECR, or CloudWatch spend.

---

## Local Developer CLI & Docker Build Setup

To deploy updates safely using short-lived `EtlDeployRole` credentials:

1. **Configure `~/.aws/config` for Role Assumption:**
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

2. **Build & Push Lambda-Compatible Images (Disable OCI Provenance/SBOM Attestations):**
   Docker Desktop Buildx defaults to multi-platform OCI image index manifests that AWS Lambda rejects (`InvalidParameterValueException`). Always build with `--provenance=false --sbom=false` targeting `linux/amd64`:
   ```powershell
   $env:AWS_PROFILE="etl-deploy"
   docker buildx build `
     --platform linux/amd64 `
     --provenance=false `
     --sbom=false `
     -t 037590970192.dkr.ecr.us-east-2.amazonaws.com/fall-practicum-py-team4:latest `
     --push .
   ```

3. **Point `etl-pipeline` to the Newly Pushed Image Digest:**
   ```powershell
   aws lambda update-function-code `
     --function-name etl-pipeline `
     --image-uri 037590970192.dkr.ecr.us-east-2.amazonaws.com/fall-practicum-py-team4:latest `
     --profile etl-deploy `
     --region us-east-2
   ```

4. **Verify Function State & Update Status:**
   ```powershell
   aws lambda get-function `
     --function-name etl-pipeline `
     --query "Configuration.{State:State,LastUpdateStatus:LastUpdateStatus,Timeout:Timeout,MemorySize:MemorySize}" `
     --profile etl-deploy `
     --region us-east-2
   ```