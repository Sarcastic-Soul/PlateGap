# --------------------------------------------------------------------------
# The solver, as one function behind a Function URL.
#
# No API Gateway. The function takes a JSON body, returns a JSON body, and
# needs no routing, no authorizers, no usage plans and no request templates.
# API Gateway would add a second service to configure, a second place for
# CORS to go wrong, and a per-request charge, in exchange for nothing this
# project uses.
# --------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Writing logs is the only permission the function has. It reads its catalog
# from its own deployment package and stores nothing.
data "aws_iam_policy_document" "lambda_logs" {
  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda_logs" {
  name   = "logs"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_logs.json
}

# --------------------------------------------------------------------------
# The one thing besides logging the function may do: ask a model to write up
# a solve, for the `explain` action and nothing else.
#
# Named models, not `bedrock:*` on `*`. The endpoint is public and
# unauthenticated, so the blast radius of an abused function is whatever this
# statement allows -- and "two small models by name" is a bill somebody can
# read, while "any model in any region" is not. The handler keeps its own
# allow-list of the same two ids so that a request cannot even ask for a
# third; this is the second half of that, on the side an attacker cannot see.
#
# The two entries are shaped differently on purpose. Nova Lite is invoked as
# a foundation model, which is a region-scoped, account-less ARN. Claude
# Haiku 4.5 is only available through a cross-region inference profile, and
# calling one needs both the profile ARN in this account and the underlying
# foundation model in every region the profile is allowed to route to -- a
# grant for us-east-1 alone produces an AccessDenied from us-east-2 that
# mentions a region nothing in this repository ever named.
#
# Note for whoever applies this: the grant is necessary and not sufficient
# for the Anthropic model. This account answers InvokeModel on Haiku 4.5 with
# ResourceNotFoundException and "Model use case details have not been
# submitted", which is a console form, not a permission. Nova Lite answers
# today. Nothing breaks either way: `explain` falls back to the templated
# text and still returns 200.
# --------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

locals {
  # Where the `us.` inference profile is allowed to send the request.
  bedrock_inference_regions = ["us-east-1", "us-east-2", "us-west-2"]
  bedrock_haiku             = "anthropic.claude-haiku-4-5-20251001-v1:0"
}

data "aws_iam_policy_document" "lambda_bedrock" {
  statement {
    sid     = "WriteUpASolve"
    actions = ["bedrock:InvokeModel"]
    resources = concat(
      [
        "arn:aws:bedrock:${var.region}::foundation-model/amazon.nova-lite-v1:0",
        "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/us.${local.bedrock_haiku}",
      ],
      [for r in local.bedrock_inference_regions :
      "arn:aws:bedrock:${r}::foundation-model/${local.bedrock_haiku}"],
    )
  }
}

resource "aws_iam_role_policy" "lambda_bedrock" {
  name   = "bedrock"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_bedrock.json
}

# --------------------------------------------------------------------------
# The daily ceiling on what `scan` may spend.
#
# This is the only durable shared state in the project, and it exists for the
# only action that costs money per call on a public, unauthenticated
# endpoint. `solver/scanbudget.py` argues the case; the short version is that
# the account's concurrency limit of 10 bounds the rate to about a scan a second, which is
# roughly $34 a day of Bedrock, and a counter is both cheaper and a better
# fit than the WAF it would otherwise take to stop that.
#
# On-demand rather than provisioned. The always-free tier covers 25 write
# units, and one unit is one write a second -- exactly the peak rate this is
# meant to survive -- so the free option is the one that throttles under the
# load it exists for. On-demand at the daily cap is about two cents a month.
#
# One tiny row per day, swept up by TTL a week later, which leaves "how much
# did this actually get used" answerable without keeping anything for ever.
# --------------------------------------------------------------------------

resource "aws_dynamodb_table" "scan_budget" {
  name         = "${var.name}-scan-budget"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "day"

  attribute {
    name = "day"
    type = "S"
  }

  ttl {
    attribute_name = "expires"
    enabled        = true
  }
}

data "aws_iam_policy_document" "lambda_budget" {
  statement {
    sid = "CountWhatWasSpent"
    # UpdateItem only. The function adds to the tally and reads back what it
    # wrote in the same call; it has no reason to scan the table, and no
    # reason to be able to delete a day it has already spent.
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.scan_budget.arn]
  }
}

resource "aws_iam_role_policy" "lambda_budget" {
  name   = "scan-budget"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_budget.json
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "solver" {
  function_name = var.name
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]

  filename         = "${path.module}/../build/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/../build/lambda.zip")

  memory_size = var.lambda_memory_mb
  timeout     = var.lambda_timeout_seconds

  environment {
    variables = {
      ALLOWED_ORIGIN          = var.allowed_origin
      PLATEGAP_SCAN_MODEL     = var.scan_model
      PLATEGAP_SCAN_TABLE     = aws_dynamodb_table.scan_budget.name
      PLATEGAP_SCAN_DAILY_CAP = tostring(var.scan_daily_cap)
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_logs,
    aws_iam_role_policy.lambda_budget,
    aws_cloudwatch_log_group.lambda,
  ]
}

resource "aws_lambda_function_url" "solver" {
  function_name      = aws_lambda_function.solver.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = [var.allowed_origin]
    allow_methods = ["POST"]
    allow_headers = ["content-type"]
    max_age       = 86400
  }
}

# --------------------------------------------------------------------------
# Making the Function URL actually reachable.
#
# Setting the URL's auth type to NONE is not enough on its own. The provider
# adds a resource policy statement granting `lambda:InvokeFunctionUrl` to
# everyone, and on an older AWS account that is the end of it -- but accounts
# created from around 2024 onward block public function URLs by default, and
# on those the request is refused with a bare 403 AccessDeniedException even
# though the policy plainly allows it. Granting `lambda:InvokeFunction` as
# well is what actually opens it.
#
# This statement cannot be narrowed. AWS rejects the FunctionUrlAuthType
# condition on `lambda:InvokeFunction`, so the grant is unconditional, which
# means any AWS principal can invoke the function directly as well as
# anonymously through its URL. That is a real widening and worth being clear
# about. It is acceptable here because the function is deliberately public,
# holds no credentials, reads a catalog baked into its own package and writes
# nothing; the only cost of abuse is invocations, and account concurrency caps
# how fast those can arrive.
# --------------------------------------------------------------------------

resource "aws_lambda_permission" "public_invoke" {
  statement_id  = "AllowPublicInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.solver.function_name
  principal     = "*"
}
