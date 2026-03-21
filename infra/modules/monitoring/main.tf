# --- SNS Topic for Alerts ---

resource "aws_sns_topic" "alerts" {
  name = "countyiq-alerts"

  tags = {
    Project     = "countyiq"
    Environment = "production"
  }
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- AWS Budget ---

resource "aws_budgets_budget" "monthly" {
  name         = "countyiq-monthly"
  budget_type  = "COST"
  limit_amount = "50"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 20    # $10 (20% of $50)
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 50    # $25 (50% of $50)
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100   # $50 (100% of $50)
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 150   # $75 (150% of $50)
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100   # Forecast exceeds $50
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}

# --- CloudWatch Log Groups ---

resource "aws_cloudwatch_log_group" "dagster" {
  name              = "/countyiq/dagster"
  retention_in_days = 7

  tags = {
    Project     = "countyiq"
    Environment = "production"
  }
}

resource "aws_cloudwatch_log_group" "system" {
  name              = "/countyiq/system"
  retention_in_days = 7

  tags = {
    Project     = "countyiq"
    Environment = "production"
  }
}

# --- CloudWatch Alarms ---

# 1. High CPU
resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "countyiq-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "EC2 CPU > 80% for 15 minutes"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    InstanceId = var.ec2_instance_id
  }

  tags = {
    Project = "countyiq"
  }
}

# 2. High Memory (requires CloudWatch Agent)
resource "aws_cloudwatch_metric_alarm" "high_memory" {
  alarm_name          = "countyiq-high-memory"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "mem_used_percent"
  namespace           = "CountyIQ/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 85
  alarm_description   = "EC2 memory > 85% for 10 minutes"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    InstanceId = var.ec2_instance_id
  }

  tags = {
    Project = "countyiq"
  }
}

# 3. High Disk
resource "aws_cloudwatch_metric_alarm" "high_disk" {
  alarm_name          = "countyiq-high-disk"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "disk_used_percent"
  namespace           = "CountyIQ/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "EC2 disk > 80%"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    InstanceId = var.ec2_instance_id
    path       = "/"
    fstype     = "xfs"
  }

  tags = {
    Project = "countyiq"
  }
}

# 4. Instance Status Check Failed
resource "aws_cloudwatch_metric_alarm" "instance_status" {
  alarm_name          = "countyiq-instance-status"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "EC2 status check failed"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    InstanceId = var.ec2_instance_id
  }

  tags = {
    Project = "countyiq"
  }
}

# 5. Dagster Health (process not running — custom metric from CloudWatch Agent)
resource "aws_cloudwatch_metric_alarm" "dagster_health" {
  alarm_name          = "countyiq-dagster-health"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "procstat_lookup_pid_count"
  namespace           = "CountyIQ/EC2"
  period              = 300
  statistic           = "Minimum"
  threshold           = 1
  alarm_description   = "Dagster daemon process not running"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "breaching"

  dimensions = {
    InstanceId = var.ec2_instance_id
    exe        = "dagster"
  }

  tags = {
    Project = "countyiq"
  }
}
