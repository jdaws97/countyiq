variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "raw_bucket_name" {
  description = "S3 bucket name for raw data"
  type        = string
  default     = "york-county-raw"
}

variable "tiles_bucket_name" {
  description = "S3 bucket name for vector tiles"
  type        = string
  default     = "york-county-tiles"
}
