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
    Memory, which also sets the CPU share. The solver is pure Python, single
    threaded and entirely CPU bound, so this is a speed dial rather than a
    memory setting -- the function's actual footprint is a few tens of MB.

    1769 MB is the point at which a Lambda gets one whole vCPU. Below it the
    function runs on a fraction of a core; above it AWS hands out a second
    vCPU that a single-threaded interpreter cannot use, so every extra MB is
    paid for and none of it arrives as speed. That makes 1769 the largest
    value with any benefit and the smallest value with the full benefit, which
    is the whole argument for it.

    Raised from 512 because the weekly audit took 6.2 s live and that is long
    enough to feel broken. `scripts/benchmark_solver.py` measures the four
    actions locally; run under a CPU quota on one core of a 12th-gen i5, the
    audit goes 698 ms at a whole core, 1384 ms at 58% of one and 3400 ms at
    29% -- slightly worse than inversely proportional, because throttling adds
    scheduling latency on top of the arithmetic. 512 MB is 29% of a vCPU, so
    the live 6.2 s and the local 3.4 s are the same shape on different silicon
    and the solver is confirmed to be CPU bound and nothing else. Going from
    512 to 1769 MB is 3.45x the CPU, which should put the audit near 1.8 s.

    It is close to free. Lambda bills GB-seconds, so 3.45x the memory for
    roughly a third of the duration is the same bill to within rounding
    (512 MB x 6.2 s = 3.2 GB-s; 1769 MB x 1.8 s = 3.2 GB-s), and at this
    traffic the whole thing sits inside the always-free 400,000 GB-seconds a
    month either way. It also helps with the other constraint: this account is
    capped at 10 concurrent executions, and that cap counts executions rather
    than megabytes, so a request that finishes in a third of the time holds
    its slot for a third as long.
  TEXT
  type        = number
  default     = 1769
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

variable "github_owner_id" {
  description = <<-TEXT
    Numeric id of the GitHub account, when the repository issues ID-qualified
    subject claims. GitHub can be told to put the immutable numeric ids of the
    owner and the repository into the token's `sub`, so that a deleted-and-
    recreated repository of the same name cannot inherit this trust. When that
    is on, `sub` reads `repo:owner@1234/name@5678:ref:refs/heads/main` and a
    policy pinned to the plain name never matches. Leave both ids empty if the
    repository issues plain subjects.

    Find them with:
      gh api repos/OWNER/NAME --jq '.owner.id, .id'
  TEXT
  type        = string
  default     = "142567151"
}

variable "github_repository_id" {
  description = "Numeric id of the repository. See `github_owner_id`."
  type        = string
  default     = "1378199091"
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
