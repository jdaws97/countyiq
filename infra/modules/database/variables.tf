variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database name (passed from root — no default, single source of truth)"
  type        = string
}

variable "db_username" {
  description = "Master database username (passed from root — no default, single source of truth)"
  type        = string
}

variable "db_password" {
  description = "Master database password"
  type        = string
  sensitive   = true
}

variable "availability_zone" {
  description = "AZ to place the RDS instance in (should match EC2 to avoid cross-AZ charges)"
  type        = string
}

variable "rds_security_group_id" {
  description = "Security group ID for RDS"
  type        = string
}

variable "rds_subnet_group_name" {
  description = "DB subnet group name"
  type        = string
}
