# Install Dendro and connect it to Claude Code and Codex. Run it again to update.
$ErrorActionPreference = "Stop"

$repo = "https://github.com/aircoding-inp/dendro"
$base = if ($env:DENDRO_HOME) { $env:DENDRO_HOME } else { Join-Path $HOME ".dendro" }
$app = Join-Path $base "app"

$python = $null
foreach ($name in "python", "python3", "py") {
    if (Get-Command $name -ErrorAction SilentlyContinue) {
        & $name -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>$null
        if ($LASTEXITCODE -eq 0) { $python = $name; break }
    }
}
if (-not $python) { throw "Dendro needs Python 3.10 or newer." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Dendro needs git." }

if (Test-Path (Join-Path $app ".git")) {
    git -C $app pull -q --ff-only
} else {
    git clone -q --depth 1 $repo $app
}
if ($LASTEXITCODE -ne 0) { throw "Could not fetch Dendro." }

& $python $app connect
if ($LASTEXITCODE -ne 0) { throw "Could not connect Dendro." }
Write-Host "Dendro is ready. Restart your agent. To read your projects: $python `"$app`" serve"
