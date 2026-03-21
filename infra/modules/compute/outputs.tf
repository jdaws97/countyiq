output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.dagster.id
}

output "private_ip" {
  description = "EC2 private IP address"
  value       = aws_instance.dagster.private_ip
}

output "ssm_connect_command" {
  description = "Command to connect via Session Manager"
  value       = "aws ssm start-session --target ${aws_instance.dagster.id}"
}
