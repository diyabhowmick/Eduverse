# EduVerse on AWS

Mumbai (ap-south-1), one AWS account, staging and production as separate Terraform workspaces.
Same pattern as AnAi: one EC2 box running Docker Compose, RDS PostgreSQL single-AZ with backups.

```
Internet -> Caddy (HTTPS, Let's Encrypt) -> API container -> RDS PostgreSQL (private subnets)
                                         -> Redis (rate limits, shared)
                                         -> S3 (books, figures, voice notes; signed links)
            Worker container (M1, writing explanations, papers, transcripts) -> same RDS, S3
            Secrets Manager (JWT_SECRET, SETTINGS_KEY, DB_PASSWORD, SUPERADMIN_PASSWORD, OPENAI_API_KEY)
            ECR (images) · CloudWatch Logs · alarms by email · SSM instead of SSH
```

All commands are PowerShell on Windows, from the project folder.

| Step | Command |
|---|---|
| Once: tools | Install AWS CLI v2, Terraform 1.6+, Docker Desktop; `aws configure` (region ap-south-1) |
| Once: state bucket and workspaces | `powershell -ExecutionPolicy Bypass -File deploy\aws\bootstrap.ps1` |
| Fill settings | `deploy\aws\terraform\envs\staging.tfvars` (domain, emails, zone id) |
| Create the environment | `powershell -ExecutionPolicy Bypass -File deploy\aws\apply.ps1 -Env staging` |
| DNS | If no zone id was given: add the A record that `dns_to_add` prints |
| Deploy the app | `powershell -ExecutionPolicy Bypass -File deploy\aws\deploy.ps1 -Env staging` |
| First sign in | Super Admin email from tfvars; password in Secrets Manager `eduverse-staging/app`, key SUPERADMIN_PASSWORD. Change it after signing in. |
| Snapshot before a risky change | `powershell -ExecutionPolicy Bypass -File deploy\aws\backup-now.ps1 -Env production` |
| Open a shell on the server | `aws ssm start-session --target <instance_id>` then `cd /opt/eduverse; sudo docker compose ps` |

Deploys roll back on their own when `/api/ready` (database and S3) does not answer within 200 seconds.
Logs: CloudWatch log group `/eduverse/<env>`. The full operations guide, security rules and the pending plan
are in the "EduVerse AWS Deployment and Operations Guide" doc.
