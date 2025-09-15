#!/bin/bash

# تنظیمات
REPO_OWNER="mohammad-heidary"
REPO_NAME="team-datax"
GITHUB_TOKEN="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"

# بررسی نصب jq و openssl
command -v jq >/dev/null 2>&1 || { echo "jq is required. Install it with 'sudo apt-get install jq'"; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo "openssl is required. Install it with 'sudo apt-get install openssl'"; exit 1; }

# گرفتن کلید عمومی ریپو برای رمزنگاری
public_key_info=($(curl -s -H "Authorization: token $GITHUB_TOKEN" -H "Accept: application/vnd.github.v3+json" \
"https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/actions/secrets/public-key" | jq -r '.key,.key_id'))
public_key="${public_key_info[0]}"
key_id="${public_key_info[1]}"

if [[ -z "$public_key" || -z "$key_id" ]]; then
  echo "Failed to retrieve public key or key_id. Check your token or repo access."
  exit 1
fi

# خواندن و آپلود secrets
while IFS='=' read -r secret_name secret_value; do
  # نادیده گرفتن خطوط خالی یا کامنت‌ها
  [[ -z "$secret_name" || "$secret_name" =~ ^# ]] && continue

  # رمزنگاری مقدار secret
  encrypted_value=$(echo -n "$secret_value" | base64 | openssl pkeyutl -encrypt -pubin -inkey <(echo "$public_key" | base64 -d) | base64 -w 0)
  if [[ $? -ne 0 ]]; then
    echo "Failed to encrypt $secret_name"
    continue
  fi

  # آپلود secret به GitHub
  response=$(curl -s -X PUT -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/actions/secrets/$secret_name" \
  -d "{\"encrypted_value\":\"$encrypted_value\",\"key_id\":\"$key_id\"}")

  if echo "$response" | grep -q "created_at"; then
    echo "Secret $secret_name uploaded successfully!"
  else
    echo "Failed to upload $secret_name: $response"
  fi
done < secrets.env

echo "Done!"