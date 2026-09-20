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

echo "==> Checking you are signed in"
aws sts get-caller-identity --query Arn --output text
gh auth status >/dev/null

echo "==> Building the function package"
"$root/scripts/package_lambda.sh"

echo "==> Applying Terraform"
cd "$root/infra"
terraform init -input=false
terraform apply -input=false "$@"

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
