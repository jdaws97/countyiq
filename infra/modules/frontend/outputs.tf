output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.main.id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.main.domain_name
}

output "frontend_bucket_name" {
  description = "Frontend S3 bucket name"
  value       = aws_s3_bucket.frontend.id
}

output "tiles_bucket_name" {
  description = "Tiles S3 bucket name"
  value       = aws_s3_bucket.tiles.id
}

output "raw_bucket_name" {
  description = "Raw data S3 bucket name"
  value       = aws_s3_bucket.raw.id
}

output "cloudfront_arn" {
  description = "CloudFront distribution ARN"
  value       = aws_cloudfront_distribution.main.arn
}
