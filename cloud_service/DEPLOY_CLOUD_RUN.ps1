param(
    [string]$ProjectId = "",
    [string]$Region = "australia-southeast1",
    [string]$ServiceName = "ai-lawyer-opposition-cloud",
    [string]$StorageBucket = "",
    [string]$FirebaseWebApiKey = "",
    [string]$FirebaseAuthDomain = "",
    [string]$FirebaseAppId = ""
)

$ErrorActionPreference = "Stop"

$gcloud = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
if (-not (Test-Path -LiteralPath $gcloud)) {
    throw "Google Cloud CLI is not installed. Install Google Cloud SDK before deployment."
}

$authJson = & $gcloud auth list --format=json 2>$null
$authRows = @()
if ($authJson) {
    $authRows = $authJson | ConvertFrom-Json
}
$activeAccount = ($authRows |
    Where-Object { $_.status -eq "ACTIVE" } |
    Select-Object -First 1).account
$activeAccount = "$activeAccount".Trim()
if (-not $activeAccount) {
    Write-Host ""
    Write-Host "Google Cloud sign-in is required." -ForegroundColor Yellow
    & $gcloud auth login
    if ($LASTEXITCODE -ne 0) {
        throw "Google Cloud sign-in was not completed."
    }
}

if (-not $ProjectId) {
    $ProjectId = (& $gcloud config get-value project 2>$null).Trim()
}
if (-not $ProjectId -or $ProjectId -eq "(unset)") {
    Write-Host ""
    & $gcloud projects list --format="table(projectId,name,lifecycleState)"
    Write-Host ""
    $ProjectId = Read-Host "Enter the billing-enabled Google Cloud project ID"
}
if (-not $ProjectId) {
    throw "A Google Cloud project ID is required."
}
if (-not $StorageBucket) {
    $StorageBucket = "$ProjectId-ai-lawyer-reports"
}
if (-not $FirebaseWebApiKey -or -not $FirebaseAuthDomain -or -not $FirebaseAppId) {
    $adminConfigPath = Join-Path (Split-Path $PSScriptRoot -Parent) "admin_cloud_config.local.json"
    if (Test-Path -LiteralPath $adminConfigPath) {
        try {
            $adminConfig = Get-Content -LiteralPath $adminConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if (-not $FirebaseWebApiKey) { $FirebaseWebApiKey = "$($adminConfig.web_api_key)".Trim() }
            if (-not $FirebaseAuthDomain) { $FirebaseAuthDomain = "$($adminConfig.auth_domain)".Trim() }
            if (-not $FirebaseAppId) { $FirebaseAppId = "$($adminConfig.app_id)".Trim() }
        }
        catch {
            Write-Warning "The Firebase admin configuration could not be read. Google sign-in configuration may be incomplete."
        }
    }
}

& $gcloud config set project $ProjectId
if ($LASTEXITCODE -ne 0) {
    throw "Could not select Google Cloud project '$ProjectId'."
}

Write-Host ""
Write-Host "Enabling Cloud Run deployment APIs..." -ForegroundColor Cyan
& $gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com storage.googleapis.com logging.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com
if ($LASTEXITCODE -ne 0) {
    throw "Could not enable the required Google Cloud APIs. Confirm billing and project permissions."
}

& $gcloud firestore databases describe --database="(default)" --project $ProjectId 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    & $gcloud firestore databases create --database="(default)" --location=$Region --type=firestore-native --project $ProjectId --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the default Firestore database."
    }
}

function New-RandomSecret {
    $bytes = New-Object byte[] 48
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes)
}

$sessionSecret = New-RandomSecret
$vaultSecret = New-RandomSecret
$sessionSecretName = "nido-session-secret"
$vaultSecretName = "nido-vault-secret"

foreach ($secretName in @($sessionSecretName, $vaultSecretName)) {
    & $gcloud secrets describe $secretName --project $ProjectId 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        & $gcloud secrets create $secretName --replication-policy=automatic --project $ProjectId
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create Secret Manager secret '$secretName'."
        }
    }
}

$sessionSecretFile = [System.IO.Path]::GetTempFileName()
$vaultSecretFile = [System.IO.Path]::GetTempFileName()
try {
    [System.IO.File]::WriteAllText($sessionSecretFile, $sessionSecret)
    [System.IO.File]::WriteAllText($vaultSecretFile, $vaultSecret)
    & $gcloud secrets versions add $sessionSecretName --data-file=$sessionSecretFile --project $ProjectId
    if ($LASTEXITCODE -ne 0) { throw "Could not add the session secret version." }
    & $gcloud secrets versions add $vaultSecretName --data-file=$vaultSecretFile --project $ProjectId
    if ($LASTEXITCODE -ne 0) { throw "Could not add the vault secret version." }
}
finally {
    Remove-Item -LiteralPath $sessionSecretFile, $vaultSecretFile -Force -ErrorAction SilentlyContinue
}

$projectNumber = (& $gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
$runtimeServiceAccount = "$projectNumber-compute@developer.gserviceaccount.com"
& $gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$runtimeServiceAccount" `
    --role="roles/secretmanager.secretAccessor" `
    --condition=None `
    --quiet 1>$null
foreach ($role in @("roles/datastore.user", "roles/logging.logWriter", "roles/aiplatform.user")) {
    & $gcloud projects add-iam-policy-binding $ProjectId `
        --member="serviceAccount:$runtimeServiceAccount" `
        --role=$role `
        --condition=None `
        --quiet 1>$null
}
if ($StorageBucket) {
    & $gcloud storage buckets describe "gs://$StorageBucket" 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        & $gcloud storage buckets create "gs://$StorageBucket" --location=$Region --uniform-bucket-level-access
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create Cloud Storage bucket '$StorageBucket'."
        }
    }
    & $gcloud storage buckets add-iam-policy-binding "gs://$StorageBucket" `
        --member="serviceAccount:$runtimeServiceAccount" `
        --role="roles/storage.objectAdmin" 1>$null
}

$envValues = @(
    "GOOGLE_CLOUD_PROJECT=$ProjectId",
    "NIDO_SERVICE_NAME=$ServiceName",
    "NIDO_DEPLOYMENT_MODE=competition",
    "NIDO_ALLOW_FULL_TEXT=false",
    "NIDO_LOG_PAYLOAD_TEXT=false",
    "NIDO_PRIVACY_FIRST_MODE=true",
    "NIDO_PUBLIC_PROMOTION_FREE=true",
    "NIDO_RECEPTION_DEMO_MODE=true",
    "NIDO_DEMO_CLIENT_NAME=Demo Client",
    "NIDO_DEMO_CLIENT_EMAIL=demo@gmail.com",
    "NIDO_DEMO_CLIENT_PASSWORD=demo",
    "NIDO_DEMO_LOGIN_ENABLED=true",
    "NIDO_DEMO_USERNAME=judge@strikeover.ai",
    "NIDO_DEMO_PASSWORD=StrikeOverDemo2026!",
    "NIDO_CLOUD_STORAGE_BUCKET=$StorageBucket",
    "NIDO_FIREBASE_WEB_API_KEY=$FirebaseWebApiKey",
    "NIDO_FIREBASE_AUTH_DOMAIN=$FirebaseAuthDomain",
    "NIDO_FIREBASE_APP_ID=$FirebaseAppId",
    "NIDO_LOG_NAME=ai-lawyer-opposition",
    "NIDO_VERTEX_LOCATION=$Region",
    "NIDO_VERTEX_MODEL=gemini-2.5-flash"
) -join ","

Write-Host ""
Write-Host "Deploying Cloud Run service..." -ForegroundColor Cyan
& $gcloud run deploy $ServiceName `
    --source . `
    --region $Region `
    --allow-unauthenticated `
    --port 8080 `
    --cpu 1 `
    --memory 512Mi `
    --min-instances 0 `
    --max-instances 1 `
    --timeout 1800 `
    --set-env-vars $envValues `
    --set-secrets "NIDO_SESSION_SECRET=$sessionSecretName`:latest,NIDO_VAULT_SECRET=$vaultSecretName`:latest" `
    --quiet
if ($LASTEXITCODE -ne 0) {
    throw "Cloud Run deployment failed."
}

$serviceUrl = (& $gcloud run services describe $ServiceName --region $Region --format="value(status.url)").Trim()
if (-not $serviceUrl) {
    throw "Deployment completed but the Cloud Run service URL could not be read."
}

$configPath = Join-Path (Split-Path $PSScriptRoot -Parent) "google_cloud_integrations.local.json"
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$config.enabled = $true
$config.project_id = $ProjectId
$config.region = $Region
$config.cloud_run.enabled = $true
$config.cloud_run.service_url = $serviceUrl
$configJson = $config | ConvertTo-Json -Depth 8
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($configPath, $configJson, $utf8NoBom)

Write-Host ""
Write-Host "Cloud Run deployment complete." -ForegroundColor Green
Write-Host "Service URL: $serviceUrl" -ForegroundColor Green
Write-Host "Health check: $serviceUrl/health"
Write-Host ""
Write-Host "The URL has been written into google_cloud_integrations.local.json."
Write-Host "Return to the launcher, open Google Cloud, and press Refresh or Test Cloud Run."
