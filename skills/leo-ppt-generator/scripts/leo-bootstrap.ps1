[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ManagerArguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$SkillDir = Split-Path -Parent $ScriptDir
$ManifestPath = Join-Path $SkillDir "runtime\bootstrap-lock.json"
$ManagerPath = Join-Path $ScriptDir "runtime_manager.py"
$LeoHome = if ($env:LEO_PPT_HOME) { $env:LEO_PPT_HOME } else { Join-Path $env:LOCALAPPDATA "leo-ppt-generator" }
$StageRoot = $null
$BootstrapMutex = $null
$MutexAcquired = $false

function Write-Stage([string]$Stage, [string]$Message) {
    [Console]::Error.WriteLine("bootstrap[$Stage]: $Message")
}

function Stop-Bootstrap(
    [string]$Reason,
    [string]$ActionId,
    [string]$Command,
    [string]$Verification,
    [string]$Stage
) {
    [ordered]@{
        protocol = "leo-ppt-bootstrap/v1"
        schema_version = 1
        platform = "windows"
        architecture = "x64"
        python_source = "unknown"
        runtime_outcome = "not_ready"
        runtime_identity = $null
        cli_reference = $null
        stage = $Stage
        status = "blocked"
        reason_code = $Reason
        primary_action = [ordered]@{
            id = $ActionId
            command = $Command
            verification = $Verification
        }
        details = @{}
    } | ConvertTo-Json -Depth 5 -Compress | Write-Output
    exit 2
}

try {
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $ManagerPath -PathType Leaf)) {
        Stop-Bootstrap "bootstrap_bundle_incomplete" "reinstall_skill" "重新安装 leo-ppt-generator" "bundle 完整后重试。" "platform_check"
    }
    if ($env:OS -ne "Windows_NT") {
        Stop-Bootstrap "bootstrap_platform_unsupported" "use_supported_platform" "在 macOS arm64 或 Windows x64 上安装" "平台匹配后重试。" "platform_check"
    }
    $Architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    if ($Architecture -notin @("AMD64", "x86_64")) {
        Stop-Bootstrap "bootstrap_platform_unsupported" "use_supported_platform" "在 Windows x64 上安装" "平台匹配后重试。" "platform_check"
    }
    Write-Stage "platform_check" "Windows x64 已确认"

    $PythonExecutable = $null
    $PythonPrefix = @()
    $PythonSource = $null
    foreach ($Candidate in @(
        @{ Name = "py"; Prefix = @("-3.12") },
        @{ Name = "python3.12"; Prefix = @() },
        @{ Name = "python"; Prefix = @() }
    )) {
        $Command = Get-Command $Candidate.Name -ErrorAction SilentlyContinue
        if (-not $Command) { continue }
        & $Command.Source @($Candidate.Prefix) -c "import struct,sys;raise SystemExit(0 if sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PythonExecutable = $Command.Source
            $PythonPrefix = @($Candidate.Prefix)
            $PythonSource = "system"
            break
        }
    }

    if (-not $PythonExecutable) {
        Write-Stage "python_resolve" "未找到兼容系统 Python，准备私有 Python"
        New-Item -ItemType Directory -Path $LeoHome -Force | Out-Null
        $HashAlgorithm = [Security.Cryptography.SHA256]::Create()
        try {
            $Hash = $HashAlgorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes(([IO.Path]::GetFullPath($LeoHome)).ToLowerInvariant()))
        }
        finally {
            $HashAlgorithm.Dispose()
        }
        $MutexName = "leo-ppt-bootstrap-" + ([BitConverter]::ToString($Hash).Replace("-", "").Substring(0, 24))
        $BootstrapMutex = [Threading.Mutex]::new($false, $MutexName)
        try { $MutexAcquired = $BootstrapMutex.WaitOne([TimeSpan]::FromSeconds(30)) }
        catch [Threading.AbandonedMutexException] { $MutexAcquired = $true }
        if (-not $MutexAcquired) {
            Stop-Bootstrap "bootstrap_lock_timeout" "retry_bootstrap" "重新运行 leo-bootstrap.ps1" "活动 bootstrap 完成后重试。" "python_resolve"
        }

        $PrivatePython = Get-ChildItem -LiteralPath (Join-Path $LeoHome "python") -Filter "python.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
        if ($PrivatePython) {
            & $PrivatePython -c "import sys;raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonExecutable = $PrivatePython
                $PythonPrefix = @()
                $PythonSource = "private-python"
            }
        }

        if (-not $PythonExecutable) {
            $Manifest = $null
            $UvCommand = Get-Command "uv" -ErrorAction SilentlyContinue
            if ($UvCommand) {
                $UvVersionOutput = (& $UvCommand.Source --version 2>$null | Out-String).Trim()
            }
            if ($UvCommand -and $UvVersionOutput -match '^uv [0-9]+\.[0-9]+\.[0-9]+') {
                $UvExecutable = $UvCommand.Source
                $PythonSource = "uv-existing"
            }
            else {
            try { $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json }
            catch { Stop-Bootstrap "bootstrap_manifest_invalid" "reinstall_skill" "重新安装 leo-ppt-generator" "manifest 可解析后重试。" "python_resolve" }
            $Artifact = $Manifest.artifacts.'windows-x64'
            $ExpectedPrefix = "https://github.com/astral-sh/uv/releases/download/$($Manifest.uv_version)/"
            if ($Manifest.schema_version -ne 1 -or $Manifest.python_version -notmatch '^3\.12\.[0-9]+$' -or
                $Artifact.url -notlike "$ExpectedPrefix*" -or $Artifact.sha256 -notmatch '^[0-9a-f]{64}$' -or
                $Artifact.executable -ne "uv-x86_64-pc-windows-msvc/uv.exe") {
                Stop-Bootstrap "bootstrap_manifest_invalid" "reinstall_skill" "重新安装 leo-ppt-generator" "manifest 通过结构与 origin 检查后重试。" "python_resolve"
            }
            $StageRoot = Join-Path $LeoHome (".bootstrap-stage." + [Guid]::NewGuid().ToString("N"))
            New-Item -ItemType Directory -Path $StageRoot | Out-Null
            $Archive = Join-Path $StageRoot "uv.zip"
            Write-Stage "python_resolve" "下载固定 uv $($Manifest.uv_version) 工件"
            try { Invoke-WebRequest -UseBasicParsing -Uri $Artifact.url -OutFile $Archive -TimeoutSec 120 }
            catch { Stop-Bootstrap "bootstrap_download_failed" "check_network_and_retry" "检查网络或代理后重新运行 leo-bootstrap.ps1" "工件可完整下载后重试。" "python_resolve" }
            if ((Get-Item -LiteralPath $Archive).Length -le 0 -or (Get-Item -LiteralPath $Archive).Length -gt [int64]$Artifact.max_bytes) {
                Stop-Bootstrap "bootstrap_artifact_size_invalid" "reinstall_skill" "重新安装 leo-ppt-generator" "工件大小符合 manifest 后重试。" "python_resolve"
            }
            if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Artifact.sha256) {
                Stop-Bootstrap "bootstrap_artifact_hash_mismatch" "stop_and_reinstall" "停止执行并重新安装 leo-ppt-generator" "SHA-256 与 manifest 一致后重试。" "python_resolve"
            }
            try { Expand-Archive -LiteralPath $Archive -DestinationPath $StageRoot }
            catch { Stop-Bootstrap "bootstrap_extract_failed" "retry_bootstrap" "重新运行 leo-bootstrap.ps1" "解压成功后重试。" "python_resolve" }
            $UvExecutable = Join-Path $StageRoot ($Artifact.executable.Replace('/', '\'))
            if (-not (Test-Path -LiteralPath $UvExecutable -PathType Leaf)) {
                Stop-Bootstrap "bootstrap_archive_invalid" "reinstall_skill" "重新安装 leo-ppt-generator" "归档结构匹配 manifest 后重试。" "python_resolve"
            }
                $PythonSource = "uv-bootstrap"
            }

            if (-not $Manifest) { $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json }
            $PythonRoot = Join-Path $LeoHome "python"
            $CacheRoot = Join-Path $LeoHome "bootstrap-cache"
            $OldInstallDir = $env:UV_PYTHON_INSTALL_DIR
            $OldCacheDir = $env:UV_CACHE_DIR
            try {
                $env:UV_PYTHON_INSTALL_DIR = $PythonRoot
                $env:UV_CACHE_DIR = $CacheRoot
                Write-Stage "python_resolve" "安装私有 Python $($Manifest.python_version)"
                & $UvExecutable python install $Manifest.python_version --install-dir $PythonRoot --no-bin --no-registry --no-config | Out-Null
                if ($LASTEXITCODE -ne 0) { Stop-Bootstrap "bootstrap_python_install_failed" "retry_bootstrap" "重新运行 leo-bootstrap.ps1" "私有 Python 安装完成后重试。" "python_resolve" }
                $PythonExecutable = (& $UvExecutable python find $Manifest.python_version --managed-python --no-project --no-config | Out-String).Trim()
            }
            finally {
                $env:UV_PYTHON_INSTALL_DIR = $OldInstallDir
                $env:UV_CACHE_DIR = $OldCacheDir
            }
            if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
                Stop-Bootstrap "bootstrap_python_invalid" "retry_bootstrap" "重新运行 leo-bootstrap.ps1" "私有 Python 通过版本检查后重试。" "python_resolve"
            }
            Write-Stage "python_resolve" "私有 Python 已就绪"
        }
        else {
            Write-Stage "python_resolve" "复用 Leo 私有 Python 3.12"
        }
    }
    else {
        Write-Stage "python_resolve" "复用兼容系统 Python 3.12"
    }

    if (-not $ManagerArguments -or $ManagerArguments.Count -eq 0) { $ManagerArguments = @("bootstrap") }
    if ($ManagerArguments[0] -eq "bootstrap") {
        $ManagerArguments += @("--python-source", $PythonSource, "--bootstrap-platform", "windows", "--bootstrap-architecture", "x64")
    }
    Write-Stage "runtime_ensure" "调用受管 runtime manager"
    & $PythonExecutable @PythonPrefix $ManagerPath @ManagerArguments
    exit $LASTEXITCODE
}
catch {
    Stop-Bootstrap "bootstrap_unhandled_error" "retry_bootstrap" "重新运行 leo-bootstrap.ps1" "若仍失败，使用 --json 诊断详情。" "python_resolve"
}
finally {
    if ($StageRoot -and (Test-Path -LiteralPath $StageRoot)) { Remove-Item -LiteralPath $StageRoot -Recurse -Force }
    if ($BootstrapMutex) {
        if ($MutexAcquired) { $BootstrapMutex.ReleaseMutex() }
        $BootstrapMutex.Dispose()
    }
}
