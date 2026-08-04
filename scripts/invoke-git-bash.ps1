[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$ScriptPath,

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArguments = @()
)

$ErrorActionPreference = 'Stop'

function Test-BlockedBashPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $blockedRoots = @(
        [Environment]::GetFolderPath('Windows'),
        $env:LOCALAPPDATA
    ) | Where-Object { $_ }
    foreach ($root in $blockedRoots) {
        $blocked = Join-Path $root 'System32\bash.exe'
        if ($fullPath.Equals($blocked, [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
        $windowsApps = Join-Path $root 'Microsoft\WindowsApps\bash.exe'
        if ($fullPath.Equals($windowsApps, [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Add-Candidate {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[string]]$Candidates,
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }
    if ((Test-Path -LiteralPath $Path -PathType Leaf) -and -not (Test-BlockedBashPath -Path $Path)) {
        if (-not $Candidates.Contains($Path)) {
            $Candidates.Add($Path)
        }
    }
}

function Resolve-GitBash {
    $candidates = [System.Collections.Generic.List[string]]::new()

    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($git) {
        $gitPath = if ($git.Source) { $git.Source } else { $git.Path }
        $gitRoot = Split-Path -Parent (Split-Path -Parent $gitPath)
        Add-Candidate -Candidates $candidates -Path (Join-Path $gitRoot 'bin\bash.exe')
        Add-Candidate -Candidates $candidates -Path (Join-Path $gitRoot 'usr\bin\bash.exe')
    }

    foreach ($programFiles in @($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ }) {
        $gitRoot = Join-Path $programFiles 'Git'
        Add-Candidate -Candidates $candidates -Path (Join-Path $gitRoot 'bin\bash.exe')
        Add-Candidate -Candidates $candidates -Path (Join-Path $gitRoot 'usr\bin\bash.exe')
    }

    foreach ($command in @(Get-Command bash.exe -All -ErrorAction SilentlyContinue)) {
        $commandPath = if ($command.Source) { $command.Source } else { $command.Path }
        Add-Candidate -Candidates $candidates -Path $commandPath
    }

    if ($candidates.Count -eq 0) {
        throw "Git for Windows Bash was not found. Install Git for Windows or invoke this script from a Git Bash installation; the WSL/System32 bash launcher is intentionally ignored."
    }
    return $candidates[0]
}

if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
    Write-Error "Bash script was not found: $ScriptPath"
    exit 2
}

try {
    $bash = Resolve-GitBash
} catch {
    Write-Error ("Git Bash resolution failed: " + $_.Exception.Message)
    exit 2
}

& $bash $ScriptPath @ScriptArguments
$exitCode = $LASTEXITCODE
if ($null -eq $exitCode) {
    $exitCode = 0
}
exit $exitCode
