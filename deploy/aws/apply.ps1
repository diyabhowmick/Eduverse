# Creates or updates one environment's AWS resources.
#   powershell -ExecutionPolicy Bypass -File deploy\aws\apply.ps1 -Env staging
param([Parameter(Mandatory = $true)][ValidateSet("staging", "production")][string]$Env)
$ErrorActionPreference = "Stop"
Push-Location "$PSScriptRoot\terraform"
terraform workspace select $Env
terraform plan -var-file="envs\$Env.tfvars" -out="$Env.plan"
$ok = Read-Host "Apply this plan to $Env? (yes/no)"
if ($ok -eq "yes") { terraform apply "$Env.plan"; terraform output }
Remove-Item "$Env.plan" -ErrorAction SilentlyContinue
Pop-Location
