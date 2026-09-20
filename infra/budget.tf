# --------------------------------------------------------------------------
# A bill that arrives as an email rather than as a discovery.
#
# Everything else in this repository bounds spending at the point of spending:
# reserved concurrency bounds the rate, `scan_daily_cap` bounds the model, the
# free tier covers the rest. This is the backstop for the case none of those
# anticipated -- a service nobody costed, a region left running, a mistake.
#
# AWS Budgets is free for the first two budgets per account, and this is the
# first. It is a global service, so it is created in us-east-1 whatever
# `var.region` says.
#
# Not created unless an address is given. The address is deliberately not
# checked into this repository: it is a real person's inbox, the repository is
# public, and a `.tf` file is exactly the sort of thing that gets scraped. Pass
# it at apply time instead:
#
#   terraform apply -var 'budget_alert_email=you@example.com'
#
# Nothing in CI runs Terraform, so leaving the variable unset breaks no
# automation -- it only means this one resource is skipped.
# --------------------------------------------------------------------------

resource "aws_budgets_budget" "monthly" {
  provider = aws.us_east_1
  count    = var.budget_alert_email == "" ? 0 : 1

  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_alert_limit)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Gross charges, not what is left after the credits are applied.
  #
  # This is the setting that decides whether the alert works at all here. The
  # account is carrying $50 of credits that expire next month, and with the
  # default `include_credit = true` those credits are netted off before the
  # threshold is compared -- so the budget would read $0.00 while something
  # quietly ran up $40, and the email would arrive only once the credits were
  # already gone. Excluding them makes the alert measure usage, which is the
  # thing worth being told about while there is still time to stop it.
  cost_types {
    include_credit = false
    include_refund = false
  }

  # Forecast first, because a warning after the money is spent is a receipt.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  # And then on the way past it, in case the forecast never saw it coming --
  # a burst that starts on the 28th does not get forecast, it just arrives.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
