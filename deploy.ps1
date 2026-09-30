# ClauseChain — one-command local deployment for Windows (PowerShell 5.1 or 7).
# macOS / Linux / WSL2: use ./deploy.sh instead (same steps).
#
# Needs only Docker Desktop. Every other dependency is pinned inside the images.
#
#   .\deploy.ps1                            asks each setting (Enter keeps the default shown)
#   .\deploy.ps1 -Yes                       no questions: defaults plus any parameters given
#
#   -Data full | partial                    data bundle: full 3.3 GB (default) or partial 1.3 GB
#   -DataFile FILE                          use a bundle you already downloaded
#   -DataUrl URL [-DataSha256 SUM]          download the bundle from another link
#   -SkipData                               start with an empty workspace
#   -EnvFile FILE                           engine API keys file (default: keys.env in this folder)
#   -Port N                                 serve on port N (default 8080)
#   -NoBuild                                start the existing images without rebuilding
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
    [switch]$NoBuild,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OrigPwd = (Get-Location).Path
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
$Interactive = (-not $Yes) -and (-not [Console]::IsInputRedirected)

# Docker Desktop is the one prerequisite. The script never installs it: it checks,
# and if Docker is missing or stopped it shows where to get it and waits.
function Find-Docker {
    if (Get-Command docker -ErrorAction SilentlyContinue) { return $true }
    # A window opened before Docker Desktop was installed still has the old PATH:
    # reload it from the registry, then try Docker's standard install folder.
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $dockerBin = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $dockerBin "docker.exe"))) {
        $env:Path = "$dockerBin;$env:Path"
    }
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Warn "docker was not on this window's PATH; found it (opening a new window also fixes this)"
        return $true
    }
    return $false
}
function Show-DockerDownload {
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "amd64" }
    Write-Host "      Download page:  https://docs.docker.com/desktop/setup/install/windows-install/"
    Write-Host "      Installer:      https://desktop.docker.com/win/main/$arch/Docker%20Desktop%20Installer.exe"
}
function Wait-ForUser($message) {
    if (-not $Interactive) { Die $message }
    Read-Host "  Press Enter to check again (Ctrl+C to stop)" | Out-Null
}

while (-not (Find-Docker)) {
    Warn "Docker Desktop is required and is not installed yet. Download it, install it, and start it:"
    Show-DockerDownload
    Wait-ForUser "Docker is not installed. Install Docker Desktop (links above), then run this again."
}
while ((Invoke-Quiet $null @("docker", "compose", "version")) -ne 0) {
    Warn "Docker Compose v2 is missing (the 'docker compose' command). Update Docker Desktop:"
    Show-DockerDownload
    Wait-ForUser "Docker Compose v2 is missing. Update Docker Desktop, then run this again."
}
while ((Invoke-Quiet $null @("docker", "info")) -ne 0) {
    Warn "Docker Desktop is installed but not running. Start it and wait until it says it is running."
    Wait-ForUser "Docker Desktop is installed but not running. Start it and run this again."
}
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { Die "curl.exe is missing (it ships with Windows 10 1803 and later)." }
if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) { Die "tar.exe is missing (it ships with Windows 10 1803 and later)." }
Ok ("Docker " + (& docker version --format '{{.Server.Version}}'))
$drive = (Get-Item $Root).PSDrive
$freeGb = [math]::Floor($drive.Free / 1GB)
if ($freeGb -lt 30) { Warn "Only $freeGb GB free on $($drive.Name):. The data and images need about 25 GB." } else { Ok "Disk: $freeGb GB free" }

# ---------------------------------------------------------------- 2. settings
Step "2/7  Settings"
# Asks a question showing its default; Enter keeps the default.
function Ask($question, $default) {
    if (-not $Interactive) { return $default }
    $prompt = if ($default) { "  $question [$default]" } else { "  $question" }
    $answer = Read-Host $prompt
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer.Trim().Trim('"').Trim("'")
}
function Test-Yes($answer) { return -not ($answer -match '^(n|no)$') }
# A path relative to this folder first, then to the folder the command was run from.
function Resolve-UserPath($path) {
    if (-not $path) { return $path }
    $path = $path.Trim().Trim('"').Trim("'")
    if (-not (Test-Path $path) -and -not [System.IO.Path]::IsPathRooted($path) -and (Test-Path (Join-Path $OrigPwd $path))) {
        return (Join-Path $OrigPwd $path)
    }
    return $path
}

$CurrentPort = ""
if (Test-Path ".env") {
    $CurrentPort = ((Read-Lines ".env") | Where-Object { $_ -match '^CLAUSECHAIN_PORT=' } | ForEach-Object { ($_ -split '=', 2)[1] }) | Select-Object -First 1
}
if (-not $CurrentPort) { $CurrentPort = "8080" }
if (-not $Port) { $Port = Ask "Port for the web app" $CurrentPort }
if ($Port -notmatch '^\d+$') { Die "The port must be a number (got '$Port')." }

# Engine API keys: keys.env in this folder is the default (recommended), or any path.
if (-not $EnvFile) {
    $keysDefault = if (Test-Path "keys.env") { "keys.env" } elseif (Test-Path "engine\.env") { "keep" } else { "keys.env" }
    if ($Interactive) {
        Write-Host "  Engine API keys (keys.env):"
        Write-Host "    Recommended: download keys.env and copy it into this folder, then press Enter:"
        Write-Host "      $Root"
        Write-Host "    Or type the path to your keys file ('none' = add keys later in engine\.env)."
    }
    while ($true) {
        $EnvFile = Ask "Keys file" $keysDefault
        if ($EnvFile -in @("keep", "none", "skip", "no")) { $EnvFile = ""; break }
        $EnvFile = Resolve-UserPath $EnvFile
        if (Test-Path $EnvFile) { break }
        if ($Interactive) { Warn "Not found: $EnvFile. Copy keys.env into $Root and press Enter, type its path, or type 'none'." }
        else { Warn "No keys file ($EnvFile); continuing without keys (add them later in engine\.env)"; $EnvFile = ""; break }
    }
}
$EnvFile = Resolve-UserPath $EnvFile
if ($EnvFile -and -not (Test-Path $EnvFile)) { Die "Keys file not found: $EnvFile" }

$DataPresent = (Test-Path "engine\data\graph_v2.db") -and (Test-Path "engine\outputs")
if (-not $SkipData -and -not $DataFile -and -not $DataUrl -and -not $Data -and -not $DataPresent) {
    if ($Interactive) {
        Write-Host "  Data bundle:"
        Write-Host "    1) full     3.3 GB  corpus, source downloads, run outputs, embedding caches, run logs"
        Write-Host "                        (re-runs need no re-embedding)"
        Write-Host "    2) partial  1.3 GB  corpus, source downloads, run outputs"
        Write-Host "    3) a bundle file you already downloaded"
        Write-Host "    4) download from another link"
        Write-Host "    5) none: start with an empty workspace"
    }
    switch (Ask "Choose 1-5" "1") {
        { $_ -in @("1", "full") } { $Data = "full"; break }
        { $_ -in @("2", "partial") } { $Data = "partial"; break }
        "3" {
            $DataFile = Resolve-UserPath (Ask "Path to the bundle (.tar.gz)" "")
            if (-not $DataFile -or -not (Test-Path $DataFile)) { Die "Bundle not found: $DataFile" }
            break
        }
        "4" {
            $DataUrl = Ask "Link to the bundle" ""
            if (-not $DataUrl) { Die "No link given." }
            $DataSha256 = Ask "Its SHA-256 (Enter to skip the check)" ""
            break
        }
        { $_ -in @("5", "none") } { $SkipData = $true; break }
        default { Die "Choose a number from 1 to 5 (got '$_')." }
    }
}

if ($DataFile) { $DataFile = Resolve-UserPath $DataFile }

if (-not $NoBuild -and $Interactive) {
    if (-not (Test-Yes (Ask "Build the images (needed the first time and after an update)" "yes"))) { $NoBuild = $true }
}

if ($SkipData) { $dataSummary = "none (empty workspace)" }
elseif ($DataPresent -and -not $DataFile -and -not $DataUrl) { $dataSummary = "already in place" }
elseif ($DataFile) { $dataSummary = $DataFile }
elseif ($DataUrl) { $dataSummary = $DataUrl }
elseif ($Data -eq "partial") { $dataSummary = "partial (1.3 GB download)" }
else { $dataSummary = "full (3.3 GB download)" }
if ($EnvFile) { $keysSummary = $EnvFile }
elseif (Test-Path "engine\.env") { $keysSummary = "engine\.env (kept)" }
else { $keysSummary = "none yet (runs need them; add later in engine\.env)" }
Write-Host "  Summary"
Write-Host "    Port:   $Port"
Write-Host "    Keys:   $keysSummary"
Write-Host "    Data:   $dataSummary"
Write-Host ("    Build:  " + $(if ($NoBuild) { "no" } else { "yes" }))
if ($Interactive -and -not (Test-Yes (Ask "Continue" "yes"))) { Write-Host "  Nothing changed."; exit 0 }

if (-not (Test-Path ".env")) {
    $lines = Read-Lines ".env.example"
    foreach ($name in "DJANGO_SECRET_KEY", "JWT_SIGNING_KEY", "POSTGRES_PASSWORD") { $lines = Set-EnvValue $lines $name (New-Secret) }
    Write-Lf ".env" $lines
    Ok "Created .env with new random secrets"
} else { Ok ".env already present (kept)" }
$lines = Read-Lines ".env"
$lines = Set-EnvValue $lines "CLAUSECHAIN_PORT" $Port
$lines = Set-EnvValue $lines "APP_ORIGIN" "http://localhost:$Port"
$lines = Set-EnvValue $lines "CSRF_TRUSTED_ORIGINS" "http://localhost:$Port,http://127.0.0.1:$Port"
Write-Lf ".env" $lines
$Url = "http://localhost:$Port"

if ($EnvFile) {
    Write-Lf "engine\.env" (Read-Lines $EnvFile)
    Ok "Installed engine keys from $EnvFile into engine\.env"
} elseif (-not (Test-Path "engine\.env")) {
    Write-Lf "engine\.env" (Read-Lines "engine\.env.example")
    Warn "No engine keys yet: browsing and review work; runs need keys in engine\.env (then: docker compose restart engine-worker backend)"
} else { Ok "engine\.env already present (kept)" }

# ---------------------------------------------------------------- 3. data
Step "3/7  Data bundle (corpus database, run outputs, source downloads)"
if ($SkipData) {
    Warn "Skipped: empty workspace"
} elseif ($DataPresent -and -not $DataFile -and -not $DataUrl) {
    Ok "Already in place (engine\data\graph_v2.db)"
} else {
    if (-not $DataFile -and -not $DataUrl) {
        if (-not $Data) { $Data = "full" }
        $key = $Data.ToUpper()
        $DataUrl = $Bundle["CLAUSECHAIN_DATA_$($key)_URL"]
        if (-not $DataSha256) { $DataSha256 = $Bundle["CLAUSECHAIN_DATA_$($key)_SHA256"] }
    }
    if (-not $DataFile) {
        if (-not $DataUrl) { Die "No data bundle location. Pass -DataUrl <link> or -DataFile <bundle.tar.gz>." }
        New-Item -ItemType Directory -Force -Path ".deploy-cache" | Out-Null
        $name = if ($Data) { $Data } else { "custom" }
        $DataFile = ".deploy-cache\clausechain-data-$name.tar.gz"
        $done = $false
        if ($DataSha256 -and (Test-Path $DataFile)) {
            $done = ((Get-FileHash -Algorithm SHA256 -Path $DataFile).Hash.ToLower() -eq $DataSha256.ToLower())
        }
        if ($done) { Ok "Already downloaded ($DataFile)" }
        else {
            Write-Host "  Downloading $DataUrl"
            & curl.exe -fL --progress-bar --retry 5 --retry-delay 5 -C - -o $DataFile $DataUrl
            if ($LASTEXITCODE -ne 0) { Die "Download failed. Check the link, then run .\deploy.ps1 again (it resumes)." }
        }
    }
    if (-not (Test-Path $DataFile)) { Die "Data bundle not found: $DataFile" }
    Write-Host "  Verifying SHA-256 ..."
    $actual = (Get-FileHash -Algorithm SHA256 -Path $DataFile).Hash.ToLower()
    if ($DataSha256) {
        if ($actual -ne $DataSha256.ToLower()) { Die "Checksum mismatch (got $actual). Delete $DataFile and run again." }
        Ok "Checksum verified"
    } elseif ($actual -in @($Bundle["CLAUSECHAIN_DATA_FULL_SHA256"], $Bundle["CLAUSECHAIN_DATA_PARTIAL_SHA256"])) {
        Ok "Checksum verified (a published bundle)"
    } else { Warn "Not one of the published bundles (SHA-256 $actual); unpacking it anyway" }
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

$credLines = Read-Lines $Cred
$AdminUser = ($credLines | Where-Object { $_ -match '^Username:' } | ForEach-Object { ($_ -split ':\s*', 2)[1] }) | Select-Object -First 1
$AdminPassword = ($credLines | Where-Object { $_ -match '^Password:' } | ForEach-Object { ($_ -split ':\s*', 2)[1] }) | Select-Object -First 1
Write-Host ""
Write-Host "ClauseChain is running:  $Url" -ForegroundColor Green
Write-Host ""
Write-Host "  ==============================================================" -ForegroundColor Yellow
Write-Host "    ADMIN LOGIN - save these now" -ForegroundColor Yellow
Write-Host "      URL:       $Url"
Write-Host "      Username:  $AdminUser" -ForegroundColor White
Write-Host "      Password:  $AdminPassword" -ForegroundColor White
Write-Host "      (also kept in $Cred in this folder)"
Write-Host "  ==============================================================" -ForegroundColor Yellow
if ($Interactive) { Read-Host "  Press Enter once you have saved the password" | Out-Null }
Write-Host ""
Write-Host "  Try it:    Runs > Sources > Build sources, then Queue run; switch Hybrid / Local at the top of any page."
Write-Host "  Stop:      docker compose stop          Start again: docker compose start"
Write-Host "  Logs:      docker compose logs -f backend engine-worker"
Write-Host "  Remove:    docker compose down          (keeps the data; add -v to also drop the database)"
