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

variable "api_gateway_id" {
  description = "API Gateway REST API ID"
  type        = string
}

variable "api_gateway_stage" {
  description = "API Gateway stage name"
  type        = string
  default     = "prod"
}

variable "origin_verify_secret" {
  description = "Shared secret between CloudFront and Lambda for origin verification"
  type        = string
  sensitive   = true
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}
