variable "primary_az" {
  description = "Availability zone for EC2 and RDS co-location (deterministic, avoids cross-AZ charges)"
  type        = string
}
