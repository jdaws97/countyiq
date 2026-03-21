# --- EC2 ---
output "ec2_instance_id" {
  description = "EC2 Dagster instance ID"
  value       = module.compute.instance_id
}

output "ssm_connect_command" {
  description = "Command to connect via Session Manager"
  value       = module.compute.ssm_connect_command
}

# --- RDS ---
output "rds_endpoint" {
  description = "RDS endpoint hostname"
  value       = module.database.rds_endpoint
}

output "rds_port" {
  description = "RDS port"
  value       = module.database.rds_port
}

# --- CloudFront ---
output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = module.frontend.cloudfront_distribution_id
}

output "cloudfront_domain_name" {
  description = "CloudFront URL (public access point)"
  value       = module.frontend.cloudfront_domain_name
}

# --- API Gateway ---
output "api_gateway_invoke_url" {
  description = "API Gateway invoke URL"
  value       = module.api.api_gateway_invoke_url
}

# --- S3 ---
output "frontend_bucket_name" {
  description = "Frontend S3 bucket"
  value       = module.frontend.frontend_bucket_name
}

output "tiles_bucket_name" {
  description = "Tiles S3 bucket"
  value       = module.frontend.tiles_bucket_name
}

output "raw_bucket_name" {
  description = "Raw data S3 bucket"
  value       = module.frontend.raw_bucket_name
}

# --- Lambda ---
output "lambda_function_name" {
  description = "Lambda function name"
  value       = module.api.lambda_function_name
}

# --- CI/CD ---
output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC"
  value       = module.cicd.github_actions_role_arn
}
