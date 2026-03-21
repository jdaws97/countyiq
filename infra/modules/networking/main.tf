# --- Default VPC and Subnets ---

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

# Deterministic subnet selection — filter by the chosen AZ to avoid
# relying on the arbitrary order of data.aws_subnets.default.ids
data "aws_subnet" "primary" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = var.primary_az
  default_for_az    = true
}

# --- Security Group: EC2 (Dagster) ---
# No inbound rules — Session Manager connects via outbound SSM agent.
# All outbound allowed for scraping, package installs, SSM, CloudWatch.

resource "aws_security_group" "dagster_ec2" {
  name        = "dagster-ec2-sg"
  description = "Dagster EC2 instance - no inbound, all outbound"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound traffic"
  }

  tags = {
    Name        = "dagster-ec2-sg"
    Project     = "york-county-intel"
    Environment = "production"
  }
}

# --- Security Group: Lambda (API) ---
# No inbound rules — invoked by API Gateway, not network.
# Outbound scoped to RDS only (port 5432 via RDS security group).

resource "aws_security_group" "api_lambda" {
  name        = "api-lambda-sg"
  description = "Lambda API - no inbound, outbound to RDS only"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.dagster_rds.id]
    description     = "PostgreSQL to RDS"
  }

  tags = {
    Name        = "api-lambda-sg"
    Project     = "york-county-intel"
    Environment = "production"
  }
}

# --- Security Group: RDS ---
# Inbound PostgreSQL (5432) from EC2 and Lambda security groups only.

resource "aws_security_group" "dagster_rds" {
  name        = "dagster-rds-sg"
  description = "RDS PostgreSQL - inbound from EC2 and Lambda only"
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name        = "dagster-rds-sg"
    Project     = "york-county-intel"
    Environment = "production"
  }
}

resource "aws_security_group_rule" "rds_from_ec2" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.dagster_rds.id
  source_security_group_id = aws_security_group.dagster_ec2.id
  description              = "PostgreSQL from EC2"
}

resource "aws_security_group_rule" "rds_from_lambda" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.dagster_rds.id
  source_security_group_id = aws_security_group.api_lambda.id
  description              = "PostgreSQL from Lambda"
}

# --- RDS Subnet Group ---
# Requires minimum 2 AZs.

resource "aws_db_subnet_group" "dagster_rds" {
  name       = "dagster-rds-subnets"
  subnet_ids = data.aws_subnets.default.ids

  tags = {
    Name        = "dagster-rds-subnets"
    Project     = "york-county-intel"
    Environment = "production"
  }
}
