param(
    [string]$Target = "D:\LeadPilot_AI",
    [string]$TagName = "v1.0.0"
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
function Step([string]$title) { Write-Host "`n===== $title =====" -ForegroundColor Cyan }
function Run([string]$program, [string[]]$argv) {
    & $program @argv
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $program $($argv -join ' ')" }
}
Set-Location -LiteralPath $Target
if (!(Test-Path ".git") -or !(Test-Path "scripts\release_verify.py")) { throw "Open your current LeadPilot AI Git checkout and install the release kit first." }
$python = "C:\Anaconda3\envs\venv\python.exe"
if (!(Test-Path $python)) { throw "Python environment not found: $python" }
Step "Verify latest remote history"
Run git @("fetch", "origin", "main")
$branch = (& git branch --show-current).Trim()
if ($branch -ne 'main') { throw "Expected branch 'main'; currently '$branch'." }
& git merge-base --is-ancestor origin/main HEAD
if ($LASTEXITCODE -ne 0) { throw "Remote main is not an ancestor of local HEAD. DO NOT force push; reconcile origin/main first." }
Step "Run isolated Python suite, verify frontend production build"
Run $python @("scripts\release_verify.py", "--full")
Step "Stage source and documentation"
Run git @("add", "-A")
Run $python @("scripts\release_verify.py", "--staged-scan")
Run git @("diff", "--cached", "--check")
Run git @("diff", "--cached", "--stat")
Run git @("status", "--short")
& git diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Host "No staged changes. Current commit may already be ready for tagging."; exit 0 }
Step "REVIEW BEFORE PUBLICATION"
Write-Host "The screenshots in docs/screenshots are DEMO captures. Review them and the staged changes."
Write-Host "This command will create a commit on main, push it to GitHub, and publish tag $TagName."
$approval = Read-Host "Type PUBLISH (uppercase) to proceed or anything else to stop"
if ($approval -cne 'PUBLISH') { Write-Host "Cancelled. No commit, push, or tag created."; exit 0 }
Step "Commit and push"
Run git @("commit", "-m", "feat: release LeadPilot AI local MVP with RBAC, CRM and voice")
Run git @("push", "origin", "main")
Step "Annotated version tag"
& git show-ref --verify --quiet "refs/tags/$TagName"
if ($LASTEXITCODE -eq 0) { throw "Local tag $TagName already exists. Commit pushed; review the tag manually." }
& git ls-remote --exit-code --tags origin "refs/tags/$TagName" | Out-Null
if ($LASTEXITCODE -eq 0) { throw "Remote tag $TagName already exists. Commit pushed; review the tag manually." }
Run git @("tag", "-a", $TagName, "-m", "LeadPilot AI local portfolio MVP $TagName")
Run git @("push", "origin", $TagName)
Step "Done"
Run git @("status", "--short")
Write-Host "Release commit and $TagName pushed. Deployment is not yet performed." -ForegroundColor Green
