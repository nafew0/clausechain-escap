# ClauseChain — one-command local deployment for Windows (PowerShell 5.1 or 7).
# macOS / Linux / WSL2: use ./deploy.sh instead (same steps).
#
# Needs only Docker Desktop. Every other dependency is pinned inside the images.
#
#   .\deploy.ps1
#   .\deploy.ps1 -Data full                 full data, 3.3 GB (asked interactively if omitted)
#   .\deploy.ps1 -Data partial              partial data, 1.3 GB (no embedding caches or run logs)
#   .\deploy.ps1 -EnvFile keys.env          also install the provided engine keys
#   .\deploy.ps1 -DataFile bundle.tar.gz    use a bundle you already downloaded
#   .\deploy.ps1 -Port 9090                 serve on another port (default 8080)
#
# If scripts are blocked: powershell -ExecutionPolicy Bypass -File .\deploy.ps1
# Safe to run again: finished steps are skipped.

param(
    [string]$Port = "",
    [string]$EnvFile = "",
    [string]$DataFile = "",
    [string]$DataUrl = "",
    [string]$DataSha256 = "",
    [ValidateSet("full", "partial")][string]$Data = "",
    [switch]$SkipData,
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-Location -Path $PSScriptRoot
$Root = (Get-Location).Path
$Utf8 = New-Object System.Text.UTF8Encoding($false)   # no BOM: docker compose reads .env byte for byte

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor White }
function Ok($text)   { Write-Host "  + $text" -ForegroundColor Green }
function Warn($text) { Write-Host "  ! $text" -ForegroundColor Yellow }
function Die($text)  { Write-Host ""; Write-Host "x $text" -ForegroundColor Red; exit 1 }
function Write-Lf($path, [string[]]$lines) { [System.IO.File]::WriteAllText($path, (($lines -join "`n") + "`n"), $Utf8) }
function Read-Lines($path) { return [System.IO.File]::ReadAllText($path) -split "`r?`n" | Where-Object { $_ -ne $null } }
function New-Secret {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
}
function Set-EnvValue($lines, $name, $value) {
    return $lines | ForEach-Object { if ($_ -match "^$name=") { "$name=$value" } else { $_ } }
}
# Runs a native command with all output sent to $log (or discarded) and returns its exit code.
# Windows PowerShell 5.1 turns redirected stderr into a terminating error under "Stop", so relax it here.
function Invoke-Quiet($log, [string[]]$command) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $rest = @(); if ($command.Length -gt 1) { $rest = $command[1..($command.Length - 1)] }
        if ($log) { & $command[0] @rest *> $log } else { & $command[0] @rest *> $null }
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
}
function Get-HttpCode($url) {
    $code = & curl.exe -s -o NUL -w "%{http_code}" $url 2>$null
    if (-not $code) { return "000" }
    return $code
}

# Published bundle locations (deploy\data_bundle.cfg); parameters override them.
$Bundle = @{}
if (Test-Path "deploy\data_bundle.cfg") {
    foreach ($line in Read-Lines "deploy\data_bundle.cfg") {
        if ($line -match '^(CLAUSECHAIN_DATA_[A-Z0-9_]+)=(.*)$') { $Bundle[$Matches[1]] = $Matches[2].Trim() }
    }
}

# ---------------------------------------------------------------- 1. prerequisites
Step "1/7  Checking prerequisites"
# A window opened before Docker Desktop was installed still has the old PATH:
# reload it from the registry, then try Docker's standard install folder.
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $dockerBin = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $dockerBin "docker.exe"))) {
        $env:Path = "$dockerBin;$env:Path"
    }
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Warn "docker was not on this window's PATH; found it (opening a new window also fixes this)"
    }
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Die "Docker is not installed. Install Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/"
}
if ((Invoke-Quiet $null @("docker", "compose", "version")) -ne 0) { Die "Docker Compose v2 is missing ('docker compose'). Update Docker Desktop." }
if ((Invoke-Quiet $null @("docker", "info")) -ne 0) { Die "Docker Desktop is installed but not running. Start it, wait until it says 'running', and run this again." }
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { Die "curl.exe is missing (it ships with Windows 10 1803 and later)." }
if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) { Die "tar.exe is missing (it ships with Windows 10 1803 and later)." }
Ok ("Docker " + (& docker version --format '{{.Server.Version}}'))
$drive = (Get-Item $Root).PSDrive
$freeGb = [math]::Floor($drive.Free / 1GB)
if ($freeGb -lt 30) { Warn "Only $freeGb GB free on $($drive.Name):. The data and images need about 25 GB." } else { Ok "Disk: $freeGb GB free" }

# ---------------------------------------------------------------- 2. settings
Step "2/7  Settings"
if (-not (Test-Path ".env")) {
    $lines = Read-Lines ".env.example"
    foreach ($name in "DJANGO_SECRET_KEY", "JWT_SIGNING_KEY", "POSTGRES_PASSWORD") { $lines = Set-EnvValue $lines $name (New-Secret) }
    Write-Lf ".env" $lines
    Ok "Created .env with new random secrets"
} else { Ok ".env already present (kept)" }
if ($Port) {
    $lines = Read-Lines ".env"
    $lines = Set-EnvValue $lines "CLAUSECHAIN_PORT" $Port
    $lines = Set-EnvValue $lines "APP_ORIGIN" "http://localhost:$Port"
    $lines = Set-EnvValue $lines "CSRF_TRUSTED_ORIGINS" "http://localhost:$Port,http://127.0.0.1:$Port"
    Write-Lf ".env" $lines
}
$Port = ((Read-Lines ".env") | Where-Object { $_ -match '^CLAUSECHAIN_PORT=' } | ForEach-Object { ($_ -split '=', 2)[1] }) | Select-Object -First 1
if (-not $Port) { $Port = "8080" }
$Url = "http://localhost:$Port"

if ($EnvFile) {
    if (-not (Test-Path $EnvFile)) { Die "-EnvFile not found: $EnvFile" }
    Write-Lf "engine\.env" (Read-Lines $EnvFile)
    Ok "Installed engine keys from $EnvFile into engine\.env"
} elseif (-not (Test-Path "engine\.env")) {
    Write-Lf "engine\.env" (Read-Lines "engine\.env.example")
    Warn "No engine keys yet: browsing and review work; runs need keys in engine\.env (then: docker compose restart engine-worker)"
} else { Ok "engine\.env already present (kept)" }

# ---------------------------------------------------------------- 3. data
Step "3/7  Data bundle (corpus database, run outputs, source downloads)"
if ($SkipData) {
    Warn "Skipped (-SkipData)"
} elseif ((Test-Path "engine\data\graph_v2.db") -and (Test-Path "engine\outputs") -and -not $DataFile) {
    Ok "Already in place (engine\data\graph_v2.db)"
} else {
    if (-not $DataFile -and -not $DataUrl) {
        if (-not $Data) {
            Write-Host "  Which data bundle?"
            Write-Host "    1) full     3.3 GB  corpus, source downloads, run outputs, embedding caches, run logs"
            Write-Host "                        (re-runs need no re-embedding)"
            Write-Host "    2) partial  1.3 GB  corpus, source downloads, run outputs"
            $answer = Read-Host "  Choose 1 or 2 [1]"
            if ($answer -in @("2", "p", "partial")) { $Data = "partial" } else { $Data = "full" }
        }
        $key = $Data.ToUpper()
        $DataUrl = $Bundle["CLAUSECHAIN_DATA_$($key)_URL"]
        if (-not $DataSha256) { $DataSha256 = $Bundle["CLAUSECHAIN_DATA_$($key)_SHA256"] }
        Write-Host "  Data bundle: $Data"
    }
    if (-not $DataFile) {
        if (-not $DataUrl) { Die "No data bundle location. Pass -DataUrl <link> or -DataFile <bundle.tar.gz>." }
        New-Item -ItemType Directory -Force -Path ".deploy-cache" | Out-Null
        $name = if ($Data) { $Data } else { "custom" }
        $DataFile = ".deploy-cache\clausechain-data-$name.tar.gz"
        Write-Host "  Downloading $DataUrl"
        & curl.exe -fL --retry 5 --retry-delay 5 -C - -o $DataFile $DataUrl
        if ($LASTEXITCODE -ne 0) { Die "Download failed. Check the link, then run .\deploy.ps1 again (it resumes)." }
    }
    if (-not (Test-Path $DataFile)) { Die "Data bundle not found: $DataFile" }
    if ($DataSha256) {
        Write-Host "  Verifying SHA-256 ..."
        $actual = (Get-FileHash -Algorithm SHA256 -Path $DataFile).Hash.ToLower()
        if ($actual -ne $DataSha256.ToLower()) { Die "Checksum mismatch (got $actual). Delete $DataFile and run again." }
        Ok "Checksum verified"
    } else { Warn "No checksum given; skipping verification" }
    Write-Host "  Unpacking about 15 GB (several minutes) ..."
    & tar.exe -xzf $DataFile -C $Root
    if ($LASTEXITCODE -ne 0) { Die "Could not unpack $DataFile" }
    if (-not (Test-Path "engine\data\graph_v2.db")) { Die "The bundle did not contain engine\data\graph_v2.db" }
    Ok "Data in place"
}
foreach ($dir in "engine\outputs", "engine\logs", "engine\data\cache") { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

# ---------------------------------------------------------------- 4. build + start
Step "4/7  Building and starting the containers (first time: 10-20 minutes)"
if ($NoBuild) { & docker compose up -d } else { & docker compose up -d --build }
if ($LASTEXITCODE -ne 0) { Die "docker compose up failed (see the messages above)." }
Ok "Containers started"

# ---------------------------------------------------------------- 5. wait
Step "5/7  Waiting for the app to answer on $Url"
$ready = $false
for ($i = 0; $i -lt 120; $i++) {
    if ((Get-HttpCode "$Url/api/auth/user/") -eq "401" -and (Get-HttpCode "$Url/") -eq "200") { $ready = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $ready) { & docker compose ps; Die "The app did not come up within 10 minutes. See: docker compose logs backend frontend" }
Ok "API and web app are up"

# ---------------------------------------------------------------- 6. snapshots
Step "6/7  Importing the reviewed evidence (Hybrid, then Local)"
foreach ($mode in "hybrid", "local") {
    if ((Invoke-Quiet ".deploy-import-$mode.log" @("docker", "compose", "exec", "-T", "backend", "python", "manage.py", "engine_refresh", "--mode", $mode)) -eq 0) { Ok "$mode snapshot imported" }
    else { Warn "$mode snapshot import failed - details in .deploy-import-$mode.log (the app still runs; re-run .\deploy.ps1 to retry)" }
}
# The signed decisions (engine\data\review\*.json) become the review state the queues show.
if ((Invoke-Quiet ".deploy-import-decisions.log" @("docker", "compose", "exec", "-T", "backend", "python", "manage.py", "import_decisions")) -eq 0) { Ok "signed review decisions loaded" }
else { Warn "loading the signed decisions failed - details in .deploy-import-decisions.log (re-run .\deploy.ps1 to retry)" }

# ---------------------------------------------------------------- 7. admin
Step "7/7  Admin account"
$Cred = ".deploy-credentials.txt"
if (Test-Path $Cred) {
    Ok "Admin account already created (see $Cred)"
} else {
    $AdminPassword = (New-Secret).Substring(0, 20)
    $script = @'
import os
from accounts.models import User
user, _ = User.objects.get_or_create(username='admin', defaults={'email': 'admin@clausechain.local'})
user.email = user.email or 'admin@clausechain.local'
user.first_name, user.last_name = 'Evaluator', 'Admin'
user.is_superuser = user.is_staff = True
user.email_verified = True
user.set_password(os.environ['CC_ADMIN_PASSWORD'])
user.save()
'@
    & docker compose exec -T -e "CC_ADMIN_PASSWORD=$AdminPassword" backend python manage.py shell -c $script | Out-Null
    if ($LASTEXITCODE -ne 0) { Die "Could not create the admin account." }
    Write-Lf $Cred @("ClauseChain admin login", "URL:      $Url", "Username: admin", "Password: $AdminPassword")
    Ok "Admin account created"
}

Write-Host ""
Write-Host "ClauseChain is running:  $Url" -ForegroundColor Green
Write-Host ""
Write-Host "  Sign in:   username admin, password in $Cred"
Write-Host "  Try it:    Runs > Sources > Build sources, then Queue run; switch Hybrid / Local at the top of any page."
Write-Host "  Stop:      docker compose stop          Start again: docker compose start"
Write-Host "  Logs:      docker compose logs -f backend engine-worker"
Write-Host "  Remove:    docker compose down          (keeps the data; add -v to also drop the database)"
