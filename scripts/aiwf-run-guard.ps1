param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RunGuardArgs
)

$ErrorActionPreference = 'Stop'

function Test-Python311 {
    param([string]$Command, [string[]]$Arguments = @())

    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        return $false
    }
    $probe = & $Command @Arguments -c `
        'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'
    if ($LASTEXITCODE -ne 0) {
        return $false
    }
    return $true
}

$pythonCommand = $null
$pythonPrefix = @()

if (Test-Python311 -Command 'py' -Arguments @('-3')) {
    $pythonCommand = 'py'
    $pythonPrefix = @('-3')
}
elseif (Test-Python311 -Command 'python') {
    $pythonCommand = 'python'
}
elseif (Test-Python311 -Command 'python3') {
    $pythonCommand = 'python3'
}

if (-not $pythonCommand) {
    Write-Error "No Python 3.11 or newer interpreter was found. Install Python 3.11+ and ensure 'py', 'python', or 'python3' is on PATH."
    exit 2
}

& $pythonCommand @pythonPrefix -B -m tools.aiwf_run_guard @RunGuardArgs
exit $LASTEXITCODE
