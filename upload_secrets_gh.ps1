```powershell
# تنظیمات
$REPO = "mohammad-heidary/team-datax"

# بررسی نصب gh
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Output "GitHub CLI (gh) is required. Install it using 'winget install --id GitHub.cli' or download from https://cli.github.com/"
    exit 1
}

# بررسی وجود فایل secrets.env
if (-not (Test-Path "secrets.env")) {
    Write-Output "secrets.env not found in current directory."
    exit 1
}

# خواندن و آپلود secrets
Get-Content secrets.env | ForEach-Object {
    if ($_ -match '^\s*#|^$' -or $_ -eq '') { return }  # نادیده گرفتن خطوط خالی یا کامنت‌ها
    $secret = $_ -split '=', 2
    $secret_name = $secret[0].Trim()
    $secret_value = $secret[1].Trim()
    if ($secret_name -eq '' -or $secret_value -eq '') { return }
    
    $result = gh secret set $secret_name --body "$secret_value" --repo $REPO 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Output "Failed to upload $secret_name : $result"
    } else {
        Write-Output "Secret $secret_name uploaded successfully!"
    }
}

Write-Output "Done!"
```