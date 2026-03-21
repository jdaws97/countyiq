# --- EC2 IAM Role ---

resource "aws_iam_role" "dagster_ec2" {
  name = "dagster-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project     = "countyiq"
    Environment = "production"
  }
}

# --- Instance Profile ---

resource "aws_iam_instance_profile" "dagster" {
  name = "dagster-instance-profile"
  role = aws_iam_role.dagster_ec2.name
}

# --- Managed Policies ---

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.dagster_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cloudwatch_agent" {
  role       = aws_iam_role.dagster_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# --- Inline Policy: S3 Access (raw data bucket only) ---

resource "aws_iam_role_policy" "s3_access" {
  name = "dagster-s3-access"
  role = aws_iam_role.dagster_ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.raw_bucket_name}",
          "arn:aws:s3:::${var.raw_bucket_name}/*"
        ]
      }
    ]
  })
}

# --- Inline Policy: S3 Tiles Bucket (write access for tile generation) ---

resource "aws_iam_role_policy" "s3_tiles_access" {
  name = "dagster-s3-tiles-access"
  role = aws_iam_role.dagster_ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          "arn:aws:s3:::${var.tiles_bucket_name}",
          "arn:aws:s3:::${var.tiles_bucket_name}/*"
        ]
      }
    ]
  })
}

# --- Inline Policy: Parameter Store (read-only, scoped to /countyiq/*) ---

resource "aws_iam_role_policy" "ssm_params" {
  name = "dagster-ssm-params"
  role = aws_iam_role.dagster_ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Resource = "arn:aws:ssm:${var.aws_region}:*:parameter/countyiq/*"
      }
    ]
  })
}
