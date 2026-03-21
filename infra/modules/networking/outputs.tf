output "vpc_id" {
  description = "Default VPC ID"
  value       = data.aws_vpc.default.id
}

output "subnet_ids" {
  description = "Default VPC subnet IDs"
  value       = data.aws_subnets.default.ids
}

output "ec2_security_group_id" {
  description = "Security group ID for EC2 Dagster instance"
  value       = aws_security_group.dagster_ec2.id
}

output "lambda_security_group_id" {
  description = "Security group ID for Lambda API"
  value       = aws_security_group.api_lambda.id
}

output "rds_security_group_id" {
  description = "Security group ID for RDS"
  value       = aws_security_group.dagster_rds.id
}

output "primary_subnet_id" {
  description = "Subnet ID in the primary AZ (for EC2 placement)"
  value       = data.aws_subnet.primary.id
}

output "primary_az" {
  description = "Availability zone for EC2 and RDS co-location"
  value       = var.primary_az
}

output "rds_subnet_group_name" {
  description = "RDS subnet group name"
  value       = aws_db_subnet_group.dagster_rds.name
}
