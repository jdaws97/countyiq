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
  description = "Database name"
  type        = string
  default     = "york_county_intel"
}

variable "database_user" {
  description = "Database username"
  type        = string
  default     = "dagster_admin"
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
