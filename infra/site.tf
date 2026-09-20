# --------------------------------------------------------------------------
# The front end: a private bucket, reachable only through CloudFront.
#
# The bucket has no website hosting, no public policy and all four public
# access blocks on. CloudFront reaches it with an Origin Access Control, which
# means the only way to read an object is through the distribution.
# --------------------------------------------------------------------------

resource "aws_s3_bucket" "site" {
  bucket_prefix = "${var.name}-site-"
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.name}-site"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "${var.name} front end"
  price_class         = "PriceClass_All"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "site"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id       = "site"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # CachingOptimized, an AWS managed policy.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"

    # CSP, HSTS and the rest. Defined at the bottom of this file, where there
    # is room to explain how the policy was derived from the three files.
    response_headers_policy_id = aws_cloudfront_response_headers_policy.site.id
  }

  # A single page application: anything that is not a file is still the page.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "site" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.site.json

  depends_on = [aws_s3_bucket_public_access_block.site]
}

# --------------------------------------------------------------------------
# Response headers: a content security policy written from what the site
# actually does, and HSTS.
#
# The site is a handful of static files and no build step, so the policy can
# be written by reading them rather than by starting permissive and hoping to
# tighten it later. `index.html` carries two script tags, both same-origin,
# and no inline script and no inline event handlers. `style.css` has no
# `@import`, no `url()` and no web font. The front end is ES modules that
# import each other by relative path, and the one dependency -- Preact with
# htm, in `web/vendor/` -- is vendored rather than fetched from a CDN, so
# `script-src 'self'` covers it. The standalone htm build has no bare import
# specifiers either, so no import map is needed and nothing has to be
# unblocked for one. The frontier chart is an inline `<svg>` element with CSS
# classes, not a style attribute, and nothing anywhere touches `eval` or
# `new Function`. The only asset that is not same-origin is the emoji
# favicon, which is a `data:` SVG in the head.
#
# So every fetch directive can be locked to 'self' with two exceptions, and
# `default-src 'none'` denies everything nobody asked for -- fonts, media,
# workers, manifests, frames -- rather than leaving them to a fallback.
#
# `'unsafe-inline'` appears nowhere, and no directive had to be loosened when
# the front end moved to a framework: htm compiles template literals at
# runtime with ordinary JavaScript, not with `new Function`, which is the
# thing that would have needed `'unsafe-eval'`. Trusted Types are deliberately
# not set -- Preact writes to the DOM through `createElement` and property
# assignment, so they would probably survive it, but turning them on is a
# change to make on its own evidence rather than in passing.
# --------------------------------------------------------------------------

locals {
  # The browser posts to the Function URL, which is a different origin from
  # the CloudFront domain the page came from, so connect-src has to name it.
  # Taking it from the resource rather than pasting the hostname means a
  # rebuild in a fresh account gets a correct policy instead of one that
  # silently blocks every request. The trailing slash is trimmed because a
  # CSP source with a path is matched as a path prefix, and the origin is what
  # is meant here.
  api_origin = trimsuffix(aws_lambda_function_url.solver.function_url, "/")

  content_security_policy = join("; ", [
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self' ${local.api_origin}",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
  ])
}

resource "aws_cloudfront_response_headers_policy" "site" {
  name    = "${var.name}-site-security"
  comment = "CSP, HSTS and the rest of the usual headers for ${var.name}"

  security_headers_config {
    content_security_policy {
      content_security_policy = local.content_security_policy
      override                = true
    }

    # Two years, and subdomains, which is the value the preload list asks for
    # even though this site cannot use it: preloading is a claim about a whole
    # domain, and `cloudfront.net` is not ours to make claims about. Turn
    # `preload` on only after moving to a custom domain that is.
    #
    # Note that HSTS is close to redundant here -- the distribution already
    # redirects HTTP to HTTPS, and a browser that has never been to the site
    # gets the redirect before it gets this header. It earns its place for the
    # second visit onward, where it removes the plaintext request that the
    # redirect answers.
    strict_transport_security {
      access_control_max_age_sec = 63072000
      include_subdomains         = true
      preload                    = false
      override                   = true
    }

    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    # `frame-ancestors 'none'` above says the same thing and says it better;
    # this is here for browsers that predate it. Nothing about this page is
    # worth framing and clickjacking a read-only calculator is a stretch, but
    # neither header costs anything.

    referrer_policy {
      referrer_policy = "no-referrer"
      override        = true
    }

    # `X-XSS-Protection: 0`. The header's filter is removed from current
    # browsers and was itself a source of vulnerabilities in the ones that
    # still ship it, so the modern advice is to switch it off explicitly and
    # rely on the policy above.
    xss_protection {
      protection = false
      mode_block = false
      override   = true
    }
  }
}
