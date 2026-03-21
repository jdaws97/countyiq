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
  description = "Database name"
  type        = string
  default     = "york_county_intel"
}

variable "db_username" {
  description = "Master database username"
  type        = string
  default     = "dagster_admin"
}

variable "db_password" {
  description = "Master database password"
  type        = string
  sensitive   = true
}

variable "rds_security_group_id" {
  description = "Security group ID for RDS"
  type        = string
}

variable "rds_subnet_group_name" {
  description = "DB subnet group name"
  type        = string
}
