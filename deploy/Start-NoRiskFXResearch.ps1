# Windows boot-task launcher template. No OS task is installed by this file.
# Requires existing private Gold ZIP, local repository and Python environment.
param(
  [Parameter(Mandatory=$true)][string]$Python,
  [Parameter(Mandatory=$true)][string]$Repository,
  [Parameter(Mandatory=$true)][string]$PrivateConfig
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $Repository
& $Python -m scripts.research_unattended_service run --config $PrivateConfig
exit $LASTEXITCODE
