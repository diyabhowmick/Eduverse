# A manual database snapshot, for example before a risky change. Automatic daily backups run anyway.
#   powershell -ExecutionPolicy Bypass -File deploy\aws\backup-now.ps1 -Env production
param([Parameter(Mandatory = $true)][ValidateSet("staging", "production")][string]$Env, [string]$Region = "ap-south-1")
$id = "eduverse-$Env-manual-$(Get-Date -Format 'yyyyMMdd-HHmm')"
aws rds create-db-snapshot --region $Region --db-instance-identifier "eduverse-$Env" --db-snapshot-identifier $id --query "DBSnapshot.Status" --output text
Write-Host "Snapshot $id started. It shows in the RDS console under Snapshots."
