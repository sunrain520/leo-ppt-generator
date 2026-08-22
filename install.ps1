[CmdletBinding()]
param(
    [switch]$Help,
    [switch]$Agents,
    [string]$Ref = "main",
    [switch]$Upgrade,
    [string]$Source = "",
    [string]$Target = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repository = "sunrain520/leo-ppt-generator"
$DownloadBase = "https://codeload.github.com/sunrain520/leo-ppt-generator/zip"
$SkillName = "leo-ppt-generator"
$StageRoot = $null
$TargetParent = $null
$InstallMutex = $null
$InstallMutexAcquired = $false

function Show-Usage {
    @"
安装 Leo PPT Generator Skill。

用法：
  pwsh -File install.ps1 [选项]

选项：
  -Agents                 安装到 ~/.agents/skills，而不是 Codex 用户目录
  -Ref <commit-or-tag>    下载指定 commit 或 tag，默认 main
  -Upgrade                验证新版本后替换现有 Skill，并保留旧版本备份
  -Source <目录>          从本地 Skill 目录安装（开发与离线验收用）
  -Target <目录>          指定完整安装目录（高级用法）
  -Help                   显示帮助

默认目标：`${CODEX_HOME}\skills\leo-ppt-generator；未设置时为 `${HOME}\.codex\skills\leo-ppt-generator
"@
}

function Copy-FilteredTree {
    param(
        [Parameter(Mandatory = $true)][string]$From,
        [Parameter(Mandatory = $true)][string]$To
    )

    New-Item -ItemType Directory -Path $To -Force | Out-Null
    foreach ($Item in Get-ChildItem -LiteralPath $From -Force) {
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "安装包包含不允许的符号链接：$($Item.FullName)"
        }
        if ($Item.PSIsContainer) {
            if ($Item.Name -in @(".venv", "__pycache__", "build", "dist") -or
                $Item.Name.EndsWith(".egg-info", [StringComparison]::OrdinalIgnoreCase)) {
                continue
            }
            Copy-FilteredTree -From $Item.FullName -To (Join-Path $To $Item.Name)
            continue
        }
        if ($Item.Extension -in @(".pyc", ".pyo")) {
            continue
        }
        Copy-Item -LiteralPath $Item.FullName -Destination (Join-Path $To $Item.Name)
    }
}

function Invoke-BootstrapLogged {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$LogPath
    )

    & $script:BootstrapPowerShell @Arguments > $LogPath
    if (-not $?) {
        return 1
    }
    $ExitCode = Get-Variable -Name LASTEXITCODE -ValueOnly -ErrorAction SilentlyContinue
    return $(if ($null -eq $ExitCode) { 0 } else { [int]$ExitCode })
}

function Test-RuntimeReceipt {
    param(
        [Parameter(Mandatory = $true)][string]$LogPath,
        [Parameter(Mandatory = $true)][ValidateSet("bootstrap", "doctor")][string]$Kind
    )

    try {
        $Payload = Get-Content -LiteralPath $LogPath -Raw | ConvertFrom-Json
        if ($Kind -eq "bootstrap") {
            return ($Payload.protocol -eq "leo-ppt-bootstrap/v1") -and
                ($Payload.status -eq "ready") -and
                ($Payload.runtime_identity -is [string]) -and $Payload.runtime_identity -and
                ($Payload.cli_reference -is [string]) -and $Payload.cli_reference
        }
        return ($Payload.status -eq "ready") -and ($Payload.reason_code -eq "ready")
    }
    catch {
        return $false
    }
}

try {
    if ($Help) {
        Show-Usage
        return
    }
    if ($Agents -and $Target) {
        throw "-Agents 与 -Target 不能同时使用"
    }
    if ($Ref -notmatch '^[A-Za-z0-9][A-Za-z0-9._/-]*$' -or $Ref.Contains("..")) {
        throw "-Ref 只能是安全的 Git commit 或 tag 名称"
    }
    if ($env:OS -ne "Windows_NT") {
        throw "install.ps1 仅用于 Windows；macOS 请使用 install.sh"
    }
    $NativeArchitecture = if ($env:PROCESSOR_ARCHITEW6432) {
        $env:PROCESSOR_ARCHITEW6432
    }
    else {
        $env:PROCESSOR_ARCHITECTURE
    }
    if ($NativeArchitecture -notin @("AMD64", "x86_64")) {
        throw "当前版本仅支持 Windows x64；检测到 $NativeArchitecture"
    }
    Write-Host "install[platform_check]: Windows x64 已确认"

    if (-not $Target) {
        $UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath("UserProfile") }
        if ($Agents) {
            $Target = Join-Path $UserHome ".agents\skills\$SkillName"
        }
        else {
            $CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $UserHome ".codex" }
            $Target = Join-Path $CodexHome "skills\$SkillName"
        }
    }
    $Target = [IO.Path]::GetFullPath($Target)
    if ([IO.Path]::GetFileName($Target.TrimEnd('\', '/')) -ne $SkillName) {
        throw "安装目录末级名称必须是 $SkillName"
    }
    $TargetParent = Split-Path -Parent $Target
    New-Item -ItemType Directory -Path $TargetParent -Force | Out-Null

    $UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath("UserProfile") }
    $CodexRoot = Join-Path $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $UserHome ".codex" }) "skills"
    $AgentsRoot = Join-Path $UserHome ".agents\skills"
    foreach ($DiscoveryRoot in @($CodexRoot, $AgentsRoot)) {
        $Discovered = [IO.Path]::GetFullPath((Join-Path $DiscoveryRoot $SkillName))
        if (-not $Discovered.Equals($Target, [StringComparison]::OrdinalIgnoreCase) -and
            (Test-Path -LiteralPath (Join-Path $Discovered "SKILL.md") -PathType Leaf)) {
            throw "检测到另一个活动 Skill：$Discovered；请只保留目标 $Target 后重试"
        }
        if (Test-Path -LiteralPath $DiscoveryRoot -PathType Container) {
            $DiscoveredBackup = Get-ChildItem -LiteralPath $DiscoveryRoot -Directory -Filter "$SkillName.backup-*" |
                Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SKILL.md") -PathType Leaf } |
                Select-Object -First 1
            if ($DiscoveredBackup) {
                throw "检测到可被发现的旧备份：$($DiscoveredBackup.FullName)；请移入非发现目录后重试"
            }
        }
    }

    $HashAlgorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $TargetHash = ([BitConverter]::ToString(
            $HashAlgorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Target.ToLowerInvariant()))
        )).Replace("-", "").Substring(0, 24)
    }
    finally {
        $HashAlgorithm.Dispose()
    }
    $InstallMutex = [Threading.Mutex]::new($false, "leo-ppt-installer-$TargetHash")
    try {
        $InstallMutexAcquired = $InstallMutex.WaitOne(0)
    }
    catch [Threading.AbandonedMutexException] {
        $InstallMutexAcquired = $true
    }
    if (-not $InstallMutexAcquired) {
        throw "另一个安装或升级正在操作该目标：$Target"
    }

    if ((Test-Path -LiteralPath $Target) -and -not $Upgrade) {
        throw "同名目录已存在：$Target；请先审阅，或明确使用 -Upgrade"
    }
    if ((Test-Path -LiteralPath $Target) -and -not (Test-Path -LiteralPath $Target -PathType Container)) {
        throw "目标已存在但不是目录：$Target"
    }

    $StageRoot = Join-Path $TargetParent (".leo-ppt-installer." + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $StageRoot | Out-Null

    $SourceDirectory = $null
    if ($Source) {
        if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
            throw "本地来源目录不存在：$Source"
        }
        $SourceDirectory = (Resolve-Path -LiteralPath $Source).Path
    }
    elseif ($PSScriptRoot -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot "skills\$SkillName\SKILL.md"))) {
        $SourceDirectory = Join-Path $PSScriptRoot "skills\$SkillName"
    }
    else {
        $Archive = Join-Path $StageRoot "source.zip"
        $ExtractRoot = Join-Path $StageRoot "source"
        $DownloadUrl = "$DownloadBase/$Ref"
        Write-Host "正在下载 $Repository@$Ref…"
        Invoke-WebRequest -UseBasicParsing -Uri $DownloadUrl -OutFile $Archive
        Expand-Archive -LiteralPath $Archive -DestinationPath $ExtractRoot
        $SourceDirectory = Get-ChildItem -LiteralPath $ExtractRoot -Directory -Recurse |
            Where-Object { $_.FullName.Replace('\', '/').EndsWith("/skills/$SkillName") } |
            Select-Object -First 1 -ExpandProperty FullName
        if (-not $SourceDirectory) {
            throw "发布包中缺少 skills/$SkillName"
        }
    }

    if (-not (Test-Path -LiteralPath (Join-Path $SourceDirectory "SKILL.md") -PathType Leaf)) {
        throw "来源缺少 SKILL.md：$SourceDirectory"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $SourceDirectory "scripts\runtime_manager.py") -PathType Leaf)) {
        throw "来源缺少 scripts/runtime_manager.py：$SourceDirectory"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $SourceDirectory "scripts\leo-bootstrap.ps1") -PathType Leaf)) {
        throw "来源缺少 scripts/leo-bootstrap.ps1：$SourceDirectory"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $SourceDirectory "runtime\bootstrap-lock.json") -PathType Leaf)) {
        throw "来源缺少 runtime/bootstrap-lock.json：$SourceDirectory"
    }

    $Candidate = Join-Path $StageRoot $SkillName
    Copy-FilteredTree -From $SourceDirectory -To $Candidate
    $UnsafePath = Get-ChildItem -LiteralPath $Candidate -Force -Recurse |
        Where-Object {
            (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) -or
            ($_.PSIsContainer -and ($_.Name -in @("third_party", "__pycache__", "build", "dist") -or $_.Name.EndsWith(".egg-info"))) -or
            (-not $_.PSIsContainer -and $_.Extension -in @(".pyc", ".pyo"))
        } |
        Select-Object -First 1
    if ($UnsafePath) {
        throw "安装包包含不允许的目录、生成物或符号链接：$($UnsafePath.FullName)"
    }

    $script:BootstrapPowerShell = Join-Path $Candidate "scripts\leo-bootstrap.ps1"
    Write-Host "install[runtime_ensure]: 正在初始化受管 runtime…"
    $EnsureLog = Join-Path $StageRoot "runtime-ensure.log"
    if ((Invoke-BootstrapLogged -Arguments @("bootstrap") -LogPath $EnsureLog) -ne 0) {
        [Console]::Error.WriteLine((Get-Content -LiteralPath $EnsureLog -Raw))
        throw "runtime 初始化失败；现有 Skill 未被替换"
    }
    if (-not (Test-RuntimeReceipt -LogPath $EnsureLog -Kind "bootstrap")) {
        [Console]::Error.WriteLine((Get-Content -LiteralPath $EnsureLog -Raw))
        throw "runtime 初始化返回无效 receipt；现有 Skill 未被替换"
    }
    Write-Host "runtime：就绪"

    foreach ($Route in @("generate", "direct-editable", "upgrade-full", "upgrade-selected")) {
        Write-Host "install[route_doctor]: 正在验证 route：$Route…"
        $DoctorLog = Join-Path $StageRoot "doctor-$Route.log"
        if ((Invoke-BootstrapLogged -Arguments @("doctor", "--route", $Route) -LogPath $DoctorLog) -ne 0) {
            [Console]::Error.WriteLine((Get-Content -LiteralPath $DoctorLog -Raw))
            throw "route 验证失败：$Route；现有 Skill 未被替换"
        }
        if (-not (Test-RuntimeReceipt -LogPath $DoctorLog -Kind "doctor")) {
            [Console]::Error.WriteLine((Get-Content -LiteralPath $DoctorLog -Raw))
            throw "route 返回无效或未就绪 receipt：$Route；现有 Skill 未被替换"
        }
        Write-Host "route ${Route}：本地机制就绪"
    }

    $Backup = $null
    if (Test-Path -LiteralPath $Target) {
        $Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
        $BackupRoot = Join-Path $TargetParent ".$SkillName-backups"
        New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
        $Backup = Join-Path $BackupRoot "$Stamp-$PID"
        if (Test-Path -LiteralPath $Backup) {
            throw "备份目录已存在：$Backup"
        }
        Move-Item -LiteralPath $Target -Destination $Backup
    }
    try {
        Move-Item -LiteralPath $Candidate -Destination $Target
    }
    catch {
        if ($Backup -and (Test-Path -LiteralPath $Backup) -and -not (Test-Path -LiteralPath $Target)) {
            Move-Item -LiteralPath $Backup -Destination $Target
        }
        throw "激活新 Skill 失败；已尝试恢复旧版本：$($_.Exception.Message)"
    }
    Write-Host "install[activate]: 已原子激活验证后的 Skill"

    Write-Host ""
    Write-Host "安装成功：$Target"
    if ($Backup) {
        Write-Host "旧版本备份：$Backup"
    }
    Write-Host "请重新启动 Codex，或开启下一轮对话后使用 leo-ppt-generator。"
}
catch {
    [Console]::Error.WriteLine("安装失败：$($_.Exception.Message)")
    exit 1
}
finally {
    if ($StageRoot -and $TargetParent -and (Test-Path -LiteralPath $StageRoot)) {
        $ExpectedPrefix = Join-Path $TargetParent ".leo-ppt-installer."
        if ($StageRoot.StartsWith($ExpectedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $StageRoot -Recurse -Force
        }
        else {
            [Console]::Error.WriteLine("警告：拒绝清理非安装器临时目录：$StageRoot")
        }
    }
    if ($InstallMutex) {
        if ($InstallMutexAcquired) {
            $InstallMutex.ReleaseMutex()
        }
        $InstallMutex.Dispose()
    }
}
