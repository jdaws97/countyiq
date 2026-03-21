# --- RDS Parameter Group ---

resource "aws_db_parameter_group" "postgres16" {
  name   = "york-county-pg16"
  family = "postgres16"

  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
    # Requires reboot to take effect
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  parameter {
    name  = "max_connections"
    value = "50"
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "work_mem"
    value = "4096"
  }

  parameter {
    name  = "maintenance_work_mem"
    value = "65536"
  }

  parameter {
    name  = "effective_cache_size"
    value = "524288"
  }

  tags = {
    Name        = "york-county-pg16"
    Project     = "york-county-intel"
    Environment = "production"
  }
}

# --- RDS Instance ---

resource "aws_db_instance" "main" {
  identifier     = "york-county-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password
  port     = 5432

  vpc_security_group_ids = [var.rds_security_group_id]
  db_subnet_group_name   = var.rds_subnet_group_name
  parameter_group_name   = aws_db_parameter_group.postgres16.name

  multi_az            = false
  availability_zone   = var.availability_zone
  publicly_accessible = false

  # Backups
  backup_retention_period   = 7
  backup_window             = "06:00-06:30"
  maintenance_window        = "sun:07:00-sun:07:30"
  copy_tags_to_snapshot     = true
  delete_automated_backups  = true
  final_snapshot_identifier = "york-county-db-final"

  # Free tier: skip performance insights
  performance_insights_enabled = false

  tags = {
    Name        = "york-county-db"
    Project     = "york-county-intel"
    Environment = "production"
  }
}
