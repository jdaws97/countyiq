variable "github_repo" {
  description = "GitHub repository in owner/repo format"
  type        = string
  default     = "jarod/countyiq"
}

variable "frontend_bucket_name" {
  description = "Frontend S3 bucket name for deploy permissions"
  type        = string
}

variable "cloudfront_arn" {
  description = "CloudFront distribution ARN for invalidation permissions"
  type        = string
}

variable "lambda_function_arn" {
  description = "Lambda function ARN for code update permissions"
  type        = string
}

variable "ec2_instance_id" {
  description = "EC2 instance ID for SSM send-command permissions"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}
