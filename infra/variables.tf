variable "region" {
  description = "Region for the Lambda function, its logs and the site bucket."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Prefix for every resource name."
  type        = string
  default     = "plategap"
}

variable "log_retention_days" {
  description = <<-TEXT
    How long to keep function logs. Short on purpose: CloudWatch Logs bills
    for storage after the first 5 GB and this project has no reason to keep a
    month of debug output.
  TEXT
  type        = number
  default     = 7
}

variable "lambda_memory_mb" {
  description = <<-TEXT
    Memory, which also sets the CPU share. The solver is pure Python and
    entirely CPU bound, so this is really a speed dial. 512 MB solves a day in
    roughly 30 ms; less than that and the weekly audit starts to feel slow.
  TEXT
  type        = number
  default     = 512
}

variable "lambda_timeout_seconds" {
  description = "Hard stop for one request. The slowest action is the weekly audit."
  type        = number
  default     = 20
}

variable "allowed_origin" {
  description = <<-TEXT
    Origin allowed to call the Function URL. Defaults to "*" because the site
    is served from a CloudFront domain that Terraform only learns after the
    distribution exists, and a tool anyone can try has no secrets to protect
    with CORS anyway.
  TEXT
  type        = string
  default     = "*"
}

variable "github_repository" {
  description = "owner/name of the repository allowed to deploy via OIDC."
  type        = string
  default     = "Sarcastic-Soul/PlateGap"
}

variable "create_github_oidc_provider" {
  description = <<-TEXT
    Whether to create the GitHub OIDC provider. An AWS account can only have
    one, so set this to false if the account already has it and pass the ARN
    in `github_oidc_provider_arn` instead.
  TEXT
  type        = bool
  default     = true
}

variable "github_oidc_provider_arn" {
  description = "Existing provider ARN, used when create_github_oidc_provider is false."
  type        = string
  default     = ""
}
