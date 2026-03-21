# --- S3 Bucket: Frontend (React static site) ---

resource "aws_s3_bucket" "frontend" {
  bucket = var.frontend_bucket_name

  tags = {
    Name        = var.frontend_bucket_name
    Project     = "countyiq"
    Environment = "production"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOAC"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.main.arn
          }
        }
      }
    ]
  })
}

# --- S3 Bucket: Vector Tiles ---

resource "aws_s3_bucket" "tiles" {
  bucket = var.tiles_bucket_name

  tags = {
    Name        = var.tiles_bucket_name
    Project     = "countyiq"
    Environment = "production"
  }
}

resource "aws_s3_bucket_public_access_block" "tiles" {
  bucket = aws_s3_bucket.tiles.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "tiles" {
  bucket = aws_s3_bucket.tiles.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOAC"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.tiles.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.main.arn
          }
        }
      }
    ]
  })
}

# --- S3 Bucket: Raw Data ---

resource "aws_s3_bucket" "raw" {
  bucket = var.raw_bucket_name

  tags = {
    Name        = var.raw_bucket_name
    Project     = "countyiq"
    Environment = "production"
  }
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket = aws_s3_bucket.raw.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id

  versioning_configuration {
    status = "Enabled"
  }
}

# No lifecycle rule on raw bucket — historical snapshots are kept indefinitely.
# Storage is date-keyed (s3://countyiq-raw/<source>/<date>/), not overwrites,
# so versioning noncurrent expiration doesn't apply. At $0.023/GB/month the
# projected 15 GB by Phase 3 costs ~$0.35/month. Not worth optimizing.

# --- CloudFront Origin Access Control ---

resource "aws_cloudfront_origin_access_control" "s3" {
  name                              = "countyiq-s3-oac"
  description                       = "OAC for CountyIQ S3 buckets"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# --- CloudFront Function: SPA URL Rewrite ---
# Rewrites requests for client-side routes (paths without file extensions)
# to /index.html so React Router can handle them. Only attached to the
# default cache behavior — /api/* and /tiles/* are unaffected.

resource "aws_cloudfront_function" "spa_rewrite" {
  name    = "countyiq-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  publish = true

  code = <<-JSEOF
    function handler(event) {
      var request = event.request;
      var uri = request.uri;

      // If the URI has a file extension (e.g. .js, .css, .png), pass through
      if (uri.match(/\.[a-zA-Z0-9]+$/)) {
        return request;
      }

      // Otherwise rewrite to /index.html for SPA client-side routing
      request.uri = '/index.html';
      return request;
    }
  JSEOF
}

# --- CloudFront Distribution ---

resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  # WAF deferred to post-MVP — add web_acl_id here when enabled
  price_class = "PriceClass_100" # US, Canada, Europe only

  # Origin 1: Frontend S3 bucket (default)
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.s3.id
  }

  # Origin 2: Tiles S3 bucket
  origin {
    domain_name              = aws_s3_bucket.tiles.bucket_regional_domain_name
    origin_id                = "s3-tiles"
    origin_access_control_id = aws_cloudfront_origin_access_control.s3.id
  }

  # Origin 3: API Gateway
  origin {
    domain_name = "${var.api_gateway_id}.execute-api.${var.aws_region}.amazonaws.com"
    origin_id   = "api-gateway"
    origin_path = "/${var.api_gateway_stage}"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    custom_header {
      name  = "x-origin-verify"
      value = var.origin_verify_secret
    }
  }

  # Default behavior: React app from S3
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    # SPA routing: rewrite requests for client-side routes to /index.html
    # This is scoped to the default behavior only — does NOT affect /api/* or /tiles/*
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_rewrite.arn
    }

    min_ttl     = 0
    default_ttl = 3600  # 1 hour
    max_ttl     = 86400
  }

  # /api/* → API Gateway (no cache)
  ordered_cache_behavior {
    path_pattern           = "/api/*"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "api-gateway"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = true
      headers      = ["Origin", "Accept", "Authorization"]
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  # /tiles/* → S3 tiles bucket (7-day cache)
  ordered_cache_behavior {
    path_pattern           = "/tiles/*"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-tiles"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 604800  # 7 days
    max_ttl     = 604800
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name        = "countyiq-distribution"
    Project     = "countyiq"
    Environment = "production"
  }
}
