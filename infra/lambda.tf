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
      ALLOWED_ORIGIN = var.allowed_origin
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_logs,
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
