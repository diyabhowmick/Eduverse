# Deploys the current code to AWS from Windows.
#   powershell -ExecutionPolicy Bypass -File deploy\aws\deploy.ps1 -Env staging
#   powershell -ExecutionPolicy Bypass -File deploy\aws\deploy.ps1 -Env production
# Needs: Docker Desktop running, AWS CLI v2 signed in (aws configure, or aws sso login), Terraform outputs for that env.
param(
  [Parameter(Mandatory = $true)][ValidateSet("staging", "production")][string]$Env,
  [string]$Region = "ap-south-1"
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."
Push-Location "$PSScriptRoot\terraform"
terraform workspace select $Env | Out-Null
$repo = terraform output -raw ecr_repository
$instance = terraform output -raw instance_id
$url = terraform output -raw url
Pop-Location

if ($Env -eq "production") {
  $ok = Read-Host "Deploy to PRODUCTION ($url)? Type the word production to continue"
  if ($ok -ne "production") { Write-Host "Stopped."; exit 1 }
}

$sha = (git -C $root rev-parse --short HEAD 2>$null)
if (-not $sha) { $sha = "manual" }
$tag = "$(Get-Date -Format 'yyyyMMdd-HHmm')-$sha"
$registry = $repo.Split("/")[0]

Write-Host "Signing in to ECR..."
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry
Write-Host "Building $repo`:$tag ..."
docker build --platform linux/amd64 -t "$repo`:$tag" -t "$repo`:latest" $root
docker push "$repo`:$tag"
docker push "$repo`:latest"

Write-Host "Starting $tag on the server..."
$cmd = aws ssm send-command --region $Region --instance-ids $instance --document-name "AWS-RunShellScript" `
  --comment "eduverse deploy $tag" --parameters "commands=['sudo /opt/eduverse/deploy.sh $tag']" --query "Command.CommandId" --output text
do {
  Start-Sleep -Seconds 8
  $status = aws ssm get-command-invocation --region $Region --command-id $cmd --instance-id $instance --query "Status" --output text 2>$null
  Write-Host "  $status"
} while ($status -in @("Pending", "InProgress", "Delayed", $null, ""))
aws ssm get-command-invocation --region $Region --command-id $cmd --instance-id $instance --query "StandardOutputContent" --output text
if ($status -ne "Success") { Write-Host "Deploy FAILED. The server rolled back to the previous version. See the output above." -ForegroundColor Red; exit 1 }
Write-Host "Live: $url  (version $tag)" -ForegroundColor Green
