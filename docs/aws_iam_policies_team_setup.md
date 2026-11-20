# Team IAM Setup and Policies

For each user on the team, an IAM profile was created. All profiles are part of a `POWERUSER` group with the following attached policies:

### 1. OAuth2 Authorization & Token Creation (`signin:*`)
* **Description:** Allows users or applications to authorize OAuth2 access and generate OAuth2 tokens specifically for public IAM OIDC/OAuth2 clients (`arn:aws:signin:*:*:oauth2/public-client/*`), which is typically used for authentication flows and federation.

### 2. IAM Password Management (`iam:*`)
* **Description:** Allows individual IAM users to change their own account passwords using dynamic variable substitution (`${aws:username}`), ensuring users can only modify credentials tied to their own user path. It also permits viewing the account's overall password policy (`iam:GetAccountPasswordPolicy`).

### 3. ECR Repository Push Access (`ecr:*`)
* **Description:** Allows a user or CI/CD pipeline to authenticate with Amazon ECR (`ecr:GetAuthorizationToken`) and push container images to a specific ECR repository (`fall-practicum-py-team4` in account `037590970192` for the `us-east-2` region). This includes uploading layers, initiating layer uploads, and completing image pushes.

### 4. Full ECR Administration & CloudTrail Lookup (`ecr:*`, `cloudtrail:*`)
* **Description:** Provides administrative-level permissions across all Amazon ECR resources (`ecr:*`), allowing full creation, deletion, and management of repositories and images globally. It also allows looking up events in CloudTrail (`cloudtrail:LookupEvents`) and permits the creation of a specific service-linked role (`replication.ecr.amazonaws.com`) to support cross-region or cross-account ECR image replication.

---

**Additional Configuration:** Additionally, all users were issued CLI access keys.