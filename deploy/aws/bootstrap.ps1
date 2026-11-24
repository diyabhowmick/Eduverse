# One time per AWS account: the S3 bucket that keeps Terraform's state, then staging and production workspaces.
#   powershell -ExecutionPolicy Bypass -File deploy\aws\bootstrap.ps1
param([string]$Region = "ap-south-1")
$ErrorActionPreference = "Stop"
$account = aws sts get-caller-identity --query Account --output text
$bucket = "eduverse-tfstate-$account"
aws s3api create-bucket --bucket $bucket --region $Region --create-bucket-configuration LocationConstraint=$Region 2>$null
aws s3api put-bucket-versioning --bucket $bucket --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket $bucket --server-side-encryption-configuration '{\"Rules\":[{\"ApplyServerSideEncryptionByDefault\":{\"SSEAlgorithm\":\"AES256\"}}]}'
aws s3api put-public-access-block --bucket $bucket --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
Push-Location "$PSScriptRoot\terraform"
terraform init -backend-config="bucket=$bucket" -backend-config="key=eduverse/terraform.tfstate" -backend-config="region=$Region"
terraform workspace new staging 2>$null; terraform workspace new production 2>$null
Pop-Location
Write-Host "State bucket: $bucket. Next: fill deploy\aws\terraform\envs\staging.tfvars, then run apply.ps1 -Env staging" -ForegroundColor Green
