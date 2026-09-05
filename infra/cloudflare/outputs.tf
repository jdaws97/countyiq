data "cloudflare_zero_trust_tunnel_cloudflared_token" "production" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.production.id
}

output "tunnel_id" {
  value = cloudflare_zero_trust_tunnel_cloudflared.production.id
}

output "tunnel_token" {
  value     = data.cloudflare_zero_trust_tunnel_cloudflared_token.production.token
  sensitive = true
}

output "r2_endpoint_url" {
  value = "https://${var.cloudflare_account_id}.r2.cloudflarestorage.com"
}

output "app_url" {
  value = "https://${local.app_domain}"
}

output "app_access_audience" {
  description = "Use this product application's AUD for CountyIQ identity verification."
  value       = cloudflare_zero_trust_access_application.product.aud
}

output "public_ready_curl_config" {
  description = "Stream to the root-only readiness curl config on the VPS; never print or commit."
  sensitive   = true
  value = format("header = \"CF-Access-Client-ID: %s\"\nheader = \"CF-Access-Client-Secret: %s\"\n",
    cloudflare_zero_trust_access_service_token.readiness.client_id,
  cloudflare_zero_trust_access_service_token.readiness.client_secret)
}

output "readiness_token_expires_at" {
  value = cloudflare_zero_trust_access_service_token.readiness.expires_at
}
