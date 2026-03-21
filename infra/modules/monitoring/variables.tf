variable "alert_email" {
  description = "Email address for budget and alarm notifications"
  type        = string
}

variable "ec2_instance_id" {
  description = "EC2 instance ID for CloudWatch alarms"
  type        = string
}
