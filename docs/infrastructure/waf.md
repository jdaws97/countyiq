# WAF Rate Limiting

> **Status: Deferred to post-MVP.** WAF is not included in the initial Terraform apply. Add it when the platform goes public. The Terraform code below is ready to be placed in `infra/modules/frontend/waf.tf` and the `web_acl_id` uncommented in the CloudFront distribution when needed.

## WAF Rate Limiting

### Why

The frontend and API are publicly accessible with no authentication. Without rate limiting, someone (or a bot) could:
- Hammer the API endpoint and run up Lambda invocation costs
- Scrape all the data from the API (ironic, given that CountyIQ is itself a scraper platform)
- DDoS the CloudFront distribution

AWS WAF attached to CloudFront provides basic protection with minimal cost.

### Configuration

A single Web ACL with two rules: a rate-based rule (throttles any IP that exceeds a request threshold) and a geographic restriction (optional — limit to US traffic since this is county-level data).

**Terraform (add to `infra/modules/frontend/` alongside the CloudFront distribution):**

```hcl
# infra/modules/frontend/waf.tf

resource "aws_wafv2_web_acl" "countyiq" {
  name        = "countyiq-rate-limit"
  description = "Rate limiting for CountyIQ CloudFront distribution"
  scope       = "CLOUDFRONT"
  provider    = aws.us_east_1  # WAF for CloudFront must be in us-east-1

  default_action {
    allow {}
  }

  # Rule 1: Rate limiting — block IPs that exceed 2,000 requests in 5 minutes
  rule {
    name     = "rate-limit"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 2000      # Requests per 5-minute window per IP
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "countyiq-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  # Rule 2: Block non-US traffic (optional — uncomment if desired)
  # rule {
  #   name     = "geo-restrict-us"
  #   priority = 2
  #
  #   action {
  #     block {}
  #   }
  #
  #   statement {
  #     not_statement {
  #       statement {
  #         geo_match_statement {
  #           country_codes = ["US"]
  #         }
  #       }
  #     }
  #   }
  #
  #   visibility_config {
  #     cloudwatch_metrics_enabled = true
  #     metric_name                = "countyiq-geo-block"
  #     sampled_requests_enabled   = true
  #   }
  # }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "countyiq-waf"
    sampled_requests_enabled   = true
  }
}

# Attach WAF to CloudFront distribution
resource "aws_wafv2_web_acl_association" "countyiq" {
  resource_arn = aws_cloudfront_distribution.frontend.arn
  web_acl_arn  = aws_wafv2_web_acl.countyiq.arn
}
```

### Rate Limit Tuning

The 2,000 requests per 5 minutes (400/minute) threshold is generous for normal usage — a user browsing the map generates maybe 20-50 requests per minute (tile loads, API calls, searches). The rate limit is there to catch abuse, not restrict normal users.

| Scenario | Requests/5min | Blocked? |
|---|---|---|
| Normal user browsing map | 50–100 | No |
| User rapidly searching | 100–200 | No |
| Bot scraping API systematically | 2,000+ | Yes |
| DDoS attempt | 10,000+ | Yes |

If legitimate users hit the rate limit (unlikely), increase the threshold in Terraform and re-apply.

### Cost

| Component | Monthly Cost |
|---|---|
| Web ACL (1) | $5.00 |
| Rate-based rule (1) | $1.00 |
| Request inspection (est. 1M requests/month) | $0.60 |
| **Total WAF cost** | **~$6.60/month** |

CloudFront does not charge for requests that WAF blocks, so blocked abuse traffic is free on the CloudFront side.

**Year 1 note:** WAF has no free tier. This $6.60/month applies from day one. If that feels steep for a platform that initially has no users, you can defer WAF and add it later when you make the frontend publicly known. The Terraform is ready — just uncomment and apply.

### CloudWatch Metrics

WAF automatically publishes metrics to CloudWatch:
- `BlockedRequests` — how many requests are being blocked (should be near zero normally)
- `AllowedRequests` — total traffic volume
- `CountedRequests` — requests matching count-only rules

Add a CloudWatch alarm for `BlockedRequests > 1000 in 5 minutes` to alert on active abuse. SNS sends to email (the original alerting path) AND to the CloudWatch-to-Slack forwarder Lambda, which is documented in `docs/operations/alerting.md`.

---
