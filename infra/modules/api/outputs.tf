output "api_gateway_id" {
  description = "API Gateway REST API ID"
  value       = aws_api_gateway_rest_api.countyiq.id
}

output "api_gateway_invoke_url" {
  description = "API Gateway invoke URL"
  value       = aws_api_gateway_stage.prod.invoke_url
}

output "api_gateway_stage_name" {
  description = "API Gateway stage name (used by CloudFront origin path)"
  value       = aws_api_gateway_stage.prod.stage_name
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.api.function_name
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.api.arn
}
