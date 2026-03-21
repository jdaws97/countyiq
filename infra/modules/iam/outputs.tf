output "instance_profile_name" {
  description = "IAM instance profile name for EC2"
  value       = aws_iam_instance_profile.dagster.name
}

output "instance_profile_arn" {
  description = "IAM instance profile ARN for EC2"
  value       = aws_iam_instance_profile.dagster.arn
}

output "ec2_role_arn" {
  description = "IAM role ARN for EC2"
  value       = aws_iam_role.dagster_ec2.arn
}
