#!/usr/bin/env bash
# Stand the whole thing up, once.
#
# Creates the infrastructure with Terraform, then sets the repository
# variables that the deploy workflow needs. After this, pushing to main
# deploys. Run it yourself -- it needs your AWS credentials and your GitHub
# session, and neither should be handed to anything else.
#
#   ./scripts/bootstrap_aws.sh
#
# It is safe to re-run. Terraform will report no changes and the variables
# will be set to the same values.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Terraform does not go through the AWS CLI. It reads credentials itself, with
# the Go SDK, and the Go SDK cannot read the session cache that `aws login`
# writes -- so a shell where every `aws` command works can still fail Terraform
# with "No valid credential sources found". Handing it the credentials as
# environment variables is the fix.
#
# Stale values from an earlier session are unset first: an expired
# AWS_SESSION_TOKEN left over in the shell shadows the refreshed cache and
# produces "the refreshed credentials are still expired", which looks like a
# login problem and is not one. Nothing here is printed or written to disk.
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN \
      AWS_CREDENTIAL_EXPIRATION AWS_SECURITY_TOKEN
if ! credentials="$(aws configure export-credentials --format env 2>/dev/null)"; then
  echo "Not signed in to AWS. Run \`aws login\` (or \`aws sso login\`) and try again." >&2
  exit 1
fi
eval "$credentials"
unset credentials

echo "==> Checking you are signed in"
aws sts get-caller-identity --query Arn --output text
gh auth status >/dev/null

echo "==> Building the function package"
"$root/scripts/package_lambda.sh"

echo "==> Applying Terraform"
cd "$root/infra"
terraform init -input=false

# An AWS account may only have one OIDC provider per issuer URL, and plenty of
# accounts already have GitHub's from some earlier project. Creating it
# unconditionally fails with EntityAlreadyExists, so look first and reuse what
# is there. Detecting it beats asking, because the answer is knowable.
oidc_arn="$(aws iam list-open-id-connect-providers \
  --query "OpenIDConnectProviderList[?ends_with(Arn, ':oidc-provider/token.actions.githubusercontent.com')].Arn | [0]" \
  --output text 2>/dev/null || true)"

if [ -n "$oidc_arn" ] && [ "$oidc_arn" != "None" ]; then
  echo "    reusing the GitHub OIDC provider this account already has"
  oidc_args=(-var "create_github_oidc_provider=false"
             -var "github_oidc_provider_arn=$oidc_arn")
else
  oidc_args=()
fi

terraform apply -input=false "${oidc_args[@]}" "$@"

name="$(terraform output -raw lambda_function_name)"
bucket="$(terraform output -raw site_bucket)"
distribution="$(terraform output -raw distribution_id)"
role="$(terraform output -raw github_deploy_role_arn)"
api="$(terraform output -raw api_url)"
site="$(terraform output -raw site_url)"
region="$(terraform output -raw region 2>/dev/null || aws configure get region)"

echo "==> Setting repository variables"
# These are identifiers, not credentials. A role ARN is useless to anyone who
# cannot already assume it, and only this repository's main branch can.
gh variable set AWS_DEPLOY_ROLE  --body "$role"
gh variable set AWS_REGION       --body "$region"
gh variable set SITE_BUCKET      --body "$bucket"
gh variable set LAMBDA_FUNCTION  --body "$name"
gh variable set DISTRIBUTION_ID  --body "$distribution"

echo "==> Publishing the site for the first time"
printf 'window.PLATEGAP_API = "%s";\n' "$api" > "$root/web/config.js"
aws s3 sync "$root/web/" "s3://$bucket/" --delete \
  --exclude "index.html" --cache-control "public, max-age=300"
aws s3 cp "$root/web/index.html" "s3://$bucket/index.html" --cache-control "no-cache"
aws cloudfront create-invalidation --distribution-id "$distribution" \
  --paths "/*" --no-cli-pager >/dev/null

# config.js is rewritten by the deploy workflow on every push, so the copy in
# the working tree is left as it was rather than committed with a live URL in
# it.
git -C "$root" checkout -- web/config.js 2>/dev/null || true

echo
echo "Done."
echo "  Site: $site"
echo "  API:  $api"
echo
echo "CloudFront takes a few minutes to finish deploying the first time."
