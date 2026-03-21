terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "countyiq"
      Environment = "production"
      ManagedBy   = "terraform"
    }
  }
}

# --- RDS Password (auto-generated, stored in SSM) ---
resource "random_password" "rds" {
  length  = 24
  special = false
}

resource "aws_ssm_parameter" "rds_password" {
  name  = "/countyiq/rds-password"
  type  = "SecureString"
  value = random_password.rds.result
}

resource "aws_ssm_parameter" "rds_host" {
  name  = "/countyiq/rds-host"
  type  = "String"
  value = module.database.rds_endpoint
}

resource "aws_ssm_parameter" "rds_dbname" {
  name  = "/countyiq/rds-dbname"
  type  = "String"
  value = var.db_name
}

resource "aws_ssm_parameter" "rds_username" {
  name  = "/countyiq/rds-username"
  type  = "String"
  value = var.db_username
}

# --- Module 1: Networking ---
module "networking" {
  source = "./modules/networking"

  primary_az = var.primary_az
}

# --- Module 2: IAM ---
module "iam" {
  source = "./modules/iam"

  aws_region        = var.aws_region
  raw_bucket_name   = var.raw_bucket_name
  tiles_bucket_name = var.tiles_bucket_name
}

# --- Module 3: Database ---
module "database" {
  source = "./modules/database"

  db_name               = var.db_name
  db_username           = var.db_username
  db_password           = random_password.rds.result
  availability_zone     = module.networking.primary_az
  rds_security_group_id = module.networking.rds_security_group_id
  rds_subnet_group_name = module.networking.rds_subnet_group_name
}

# --- Module 4: Compute ---
# depends_on ensures all 4 SSM parameters exist before EC2 boots,
# so user_data.sh can retrieve them without a race condition.
module "compute" {
  source = "./modules/compute"

  subnet_id             = module.networking.primary_subnet_id
  ec2_security_group_id = module.networking.ec2_security_group_id
  instance_profile_name = module.iam.instance_profile_name
  aws_region            = var.aws_region

  depends_on = [
    aws_ssm_parameter.rds_host,
    aws_ssm_parameter.rds_password,
    aws_ssm_parameter.rds_dbname,
    aws_ssm_parameter.rds_username,
  ]
}

# --- Module 5: Monitoring ---
module "monitoring" {
  source = "./modules/monitoring"

  alert_email     = var.alert_email
  ec2_instance_id = module.compute.instance_id
}

# --- Module 6: API ---
module "api" {
  source = "./modules/api"

  subnet_ids               = module.networking.subnet_ids
  lambda_security_group_id = module.networking.lambda_security_group_id
  database_host            = module.database.rds_endpoint
  database_name            = var.db_name
  database_user            = var.db_username
  database_password        = random_password.rds.result
  origin_verify_secret     = var.origin_verify_secret
}

# --- Module 7: Frontend ---
module "frontend" {
  source = "./modules/frontend"

  frontend_bucket_name = var.frontend_bucket_name
  tiles_bucket_name    = var.tiles_bucket_name
  raw_bucket_name      = var.raw_bucket_name
  api_gateway_id       = module.api.api_gateway_id
  api_gateway_stage    = module.api.api_gateway_stage_name
  origin_verify_secret = var.origin_verify_secret
  aws_region           = var.aws_region
}

# --- Module 8: CI/CD ---
module "cicd" {
  source = "./modules/cicd"

  github_repo          = var.github_repo
  frontend_bucket_name = module.frontend.frontend_bucket_name
  cloudfront_arn       = module.frontend.cloudfront_arn
  lambda_function_arn  = module.api.lambda_function_arn
  ec2_instance_id      = module.compute.instance_id
  aws_region           = var.aws_region
}
