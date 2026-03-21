variable "subnet_ids" {
  description = "Subnet IDs for Lambda VPC configuration"
  type        = list(string)
}

variable "lambda_security_group_id" {
  description = "Security group ID for Lambda"
  type        = string
}

variable "database_host" {
  description = "RDS endpoint hostname"
  type        = string
}

variable "database_name" {
  description = "Database name (passed from root — no default, single source of truth)"
  type        = string
}

variable "database_user" {
  description = "Database username (passed from root — no default, single source of truth)"
  type        = string
}

variable "database_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "origin_verify_secret" {
  description = "Shared secret for CloudFront origin verification"
  type        = string
  sensitive   = true
}
