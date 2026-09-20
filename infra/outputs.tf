output "api_url" {
  description = "The Function URL the front end posts to."
  value       = aws_lambda_function_url.solver.function_url
}

output "site_url" {
  description = "Where the app is served."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "site_bucket" {
  description = "Bucket the deploy workflow syncs the built site into."
  value       = aws_s3_bucket.site.id
}

output "distribution_id" {
  description = "Distribution the deploy workflow invalidates."
  value       = aws_cloudfront_distribution.site.id
}

output "lambda_function_name" {
  value = aws_lambda_function.solver.function_name
}

output "github_deploy_role_arn" {
  description = <<-TEXT
    Set this as the repository variable AWS_DEPLOY_ROLE. It is an ARN, not a
    secret -- it identifies a role that only this repository's main branch can
    assume, and it is useless to anyone else.
  TEXT
  value       = aws_iam_role.github_deploy.arn
}

output "region" {
  description = "Where the function and its logs live."
  value       = var.region
}
