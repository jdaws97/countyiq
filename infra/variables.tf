variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "db_name" {
  description = "RDS database name — single source of truth for all modules"
  type        = string
  default     = "york_county_intel"
}

variable "db_username" {
  description = "RDS master username — single source of truth for all modules"
  type        = string
  default     = "dagster_admin"
}

variable "primary_az" {
  description = "Availability zone for EC2 and RDS co-location (deterministic selection)"
  type        = string
  default     = "us-east-1a"
}

variable "origin_verify_secret" {
  description = "Shared secret between CloudFront and Lambda for origin verification"
  type        = string
  sensitive   = true
}

variable "alert_email" {
  description = "Email address for budget and alarm notifications"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository in owner/repo format"
  type        = string
  default     = "jarod/countyiq"
}

variable "frontend_bucket_name" {
  description = "S3 bucket name for frontend static site"
  type        = string
  default     = "york-county-frontend"
}

variable "tiles_bucket_name" {
  description = "S3 bucket name for vector tiles"
  type        = string
  default     = "york-county-tiles"
}

variable "raw_bucket_name" {
  description = "S3 bucket name for raw data archives"
  type        = string
  default     = "york-county-raw"
}
