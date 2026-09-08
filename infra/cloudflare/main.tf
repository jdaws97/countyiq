locals {
  app_domain     = "app.${var.domain}"
  dagster_domain = "dagster.${var.domain}"
}

resource "cloudflare_zero_trust_organization" "countyiq" {
  account_id              = var.cloudflare_account_id
  name                    = "CountyIQ"
  auth_domain             = var.access_auth_domain
  session_duration        = "24h"
  deny_unmatched_requests = false
}

resource "cloudflare_zero_trust_access_identity_provider" "email_otp" {
  account_id = var.cloudflare_account_id
  name       = "Email one-time PIN"
  type       = "onetimepin"
  config     = {}

  depends_on = [cloudflare_zero_trust_organization.countyiq]
}

resource "random_bytes" "tunnel_secret" {
  length = 32
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "production" {
  account_id    = var.cloudflare_account_id
  name          = "countyiq-production"
  config_src    = "cloudflare"
  tunnel_secret = random_bytes.tunnel_secret.base64
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "production" {
  # Install the gate before a hostname can reach even the old origin.
  depends_on = [
    cloudflare_zero_trust_access_application.product,
    cloudflare_zero_trust_access_application.dagster,
  ]

  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.production.id

  config = {
    ingress = [
      {
        hostname = var.domain
        service  = "http://caddy:8080"
        origin_request = {
          http_host_header = var.domain
        }
      },
      {
        hostname = local.app_domain
        service  = "http://caddy:8080"
        origin_request = {
          http_host_header = local.app_domain
        }
      },
      {
        hostname = local.dagster_domain
        service  = "http://dagster-webserver:3000"
      },
      {
        service = "http_status:404"
      }
    ]
  }
}

# Pipeline controls are operator-only; customer/tester access never grants this.
resource "cloudflare_zero_trust_access_application" "dagster" {
  account_id                = var.cloudflare_account_id
  name                      = "CountyIQ Dagster operator"
  domain                    = local.dagster_domain
  type                      = "self_hosted"
  session_duration          = "8h"
  app_launcher_visible      = true
  allowed_idps              = [cloudflare_zero_trust_access_identity_provider.email_otp.id]
  auto_redirect_to_identity = true

  policies = [{
    name       = "CountyIQ owner only"
    decision   = "allow"
    precedence = 1
    include = [{
      email = { email = var.operator_email }
    }]
  }]
}

resource "cloudflare_dns_record" "dagster" {
  depends_on = [cloudflare_zero_trust_access_application.dagster]

  zone_id = var.cloudflare_zone_id
  name    = local.dagster_domain
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.production.id}.cfargotunnel.com"
  ttl     = 1
  proxied = true
}

resource "cloudflare_dns_record" "application" {
  zone_id = var.cloudflare_zone_id
  name    = var.domain
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.production.id}.cfargotunnel.com"
  ttl     = 1
  proxied = true
}

moved {
  from = cloudflare_zero_trust_access_application.application
  to   = cloudflare_zero_trust_access_application.application[0]
}

resource "cloudflare_zero_trust_access_application" "application" {
  count                     = var.publish_marketing_site ? 0 : 1
  account_id                = var.cloudflare_account_id
  name                      = "CountyIQ private alpha"
  domain                    = var.domain
  type                      = "self_hosted"
  session_duration          = "24h"
  app_launcher_visible      = false
  allowed_idps              = [cloudflare_zero_trust_access_identity_provider.email_otp.id]
  auto_redirect_to_identity = true

  policies = [
    {
      name       = "Allow invited testers"
      decision   = "allow"
      precedence = 1
      include = [
        for address in sort(tolist(var.access_allowed_emails)) : {
          email = {
            email = address
          }
        }
      ]
    }
  ]
}

resource "cloudflare_dns_record" "product" {
  depends_on = [cloudflare_zero_trust_access_application.product]

  zone_id = var.cloudflare_zone_id
  name    = local.app_domain
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.production.id}.cfargotunnel.com"
  ttl     = 1
  proxied = true
}

resource "cloudflare_zero_trust_access_application" "product" {
  account_id                = var.cloudflare_account_id
  name                      = "CountyIQ app private alpha"
  domain                    = local.app_domain
  type                      = "self_hosted"
  session_duration          = "24h"
  app_launcher_visible      = false
  allowed_idps              = [cloudflare_zero_trust_access_identity_provider.email_otp.id]
  auto_redirect_to_identity = true

  policies = [
    {
      name       = "Allow invited testers"
      decision   = "allow"
      precedence = 1
      include = [
        for address in sort(tolist(var.access_allowed_emails)) : {
          email = {
            email = address
          }
        }
      ]
    }
  ]
}

# Release checks can reach only the readiness path. Machine credentials never
# grant access to customer pages or establish a customer account identity.
resource "cloudflare_zero_trust_access_service_token" "readiness" {
  account_id = var.cloudflare_account_id
  name       = "CountyIQ production readiness"
  duration   = "8760h"
}

resource "cloudflare_zero_trust_access_application" "readiness" {
  account_id           = var.cloudflare_account_id
  name                 = "CountyIQ readiness check"
  domain               = "${local.app_domain}/api/ready"
  type                 = "self_hosted"
  app_launcher_visible = false

  policies = [{
    name       = "Production readiness service"
    decision   = "non_identity"
    precedence = 1
    include = [{
      service_token = {
        token_id = cloudflare_zero_trust_access_service_token.readiness.id
      }
    }]
  }]
}

resource "cloudflare_r2_bucket" "raw" {
  account_id    = var.cloudflare_account_id
  name          = var.raw_bucket_name
  location      = "enam"
  storage_class = "Standard"

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_r2_bucket" "backups" {
  account_id    = var.cloudflare_account_id
  name          = var.backup_bucket_name
  location      = "enam"
  storage_class = "Standard"

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_r2_bucket_lifecycle" "raw" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.raw.name

  rules = [
    {
      id         = "expire-raw-archives"
      enabled    = true
      conditions = { prefix = "" }
      abort_multipart_uploads_transition = {
        condition = {
          type    = "Age"
          max_age = 86400
        }
      }
      delete_objects_transition = {
        condition = {
          type    = "Age"
          max_age = var.raw_retention_days * 86400
        }
      }
    }
  ]
}

resource "cloudflare_r2_bucket_lifecycle" "backups" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.backups.name

  rules = [
    {
      id         = "expire-backup-manifests"
      enabled    = true
      conditions = { prefix = "manifests/" }
      abort_multipart_uploads_transition = {
        condition = {
          type    = "Age"
          max_age = 86400
        }
      }
      delete_objects_transition = {
        condition = {
          type    = "Age"
          max_age = var.database_backup_retention_days * 86400
        }
      }
    },
    {
      id         = "expire-database-dumps"
      enabled    = true
      conditions = { prefix = "postgres/" }
      abort_multipart_uploads_transition = {
        condition = {
          type    = "Age"
          max_age = 86400
        }
      }
      delete_objects_transition = {
        condition = {
          type    = "Age"
          max_age = var.database_backup_retention_days * 86400
        }
      }
    }
  ]
}

resource "cloudflare_r2_bucket_lock" "raw" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.raw.name

  rules = [
    {
      id      = "protect-raw-archives"
      enabled = true
      prefix  = ""
      condition = {
        type            = "Age"
        max_age_seconds = var.backup_lock_days * 86400
      }
    }
  ]
}

resource "cloudflare_r2_bucket_lock" "backups" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.backups.name

  rules = [
    for prefix in ["manifests/", "postgres/"] : {
      id      = "protect-${replace(trim(prefix, "/"), "/", "-")}"
      enabled = true
      prefix  = prefix
      condition = {
        type            = "Age"
        max_age_seconds = var.backup_lock_days * 86400
      }
    }
  ]
}
