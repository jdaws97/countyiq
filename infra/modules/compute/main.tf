# --- Amazon Linux 2023 AMI ---

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-kernel-default-x86_64-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# --- EC2 Instance ---

resource "aws_instance" "dagster" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.ec2_security_group_id]
  iam_instance_profile   = var.instance_profile_name

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    aws_region = var.aws_region
  })

  # No key pair — Session Manager replaces SSH entirely
  monitoring = false # Basic monitoring (free tier sufficient)

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  tags = {
    Name        = "york-county-dagster"
    Project     = "york-county-intel"
    Environment = "production"
  }
}
