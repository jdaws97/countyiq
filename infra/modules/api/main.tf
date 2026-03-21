# --- Lambda IAM Role ---

resource "aws_iam_role" "lambda" {
  name = "york-county-api-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project     = "york-county-intel"
    Environment = "production"
  }
}

# Lambda needs VPC access for RDS
resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Basic execution role for CloudWatch Logs
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- Lambda Function ---

# Placeholder zip for initial deployment (Lambda requires code at creation)
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/lambda_placeholder.zip"

  source {
    content  = "def handler(event, context): return {'statusCode': 200, 'body': 'placeholder'}"
    filename = "handler.py"
  }
}

resource "aws_lambda_function" "api" {
  function_name = "york-county-api"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 256

  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  reserved_concurrent_executions = 10

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      DATABASE_HOST          = var.database_host
      DATABASE_NAME          = var.database_name
      DATABASE_USER          = var.database_user
      DATABASE_PASSWORD      = var.database_password
      ORIGIN_VERIFY_SECRET   = var.origin_verify_secret
    }
  }

  tags = {
    Name        = "york-county-api"
    Project     = "york-county-intel"
    Environment = "production"
  }
}

# --- API Gateway (REST API) ---

resource "aws_api_gateway_rest_api" "countyiq" {
  name        = "countyiq-api"
  description = "CountyIQ REST API"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = {
    Project     = "york-county-intel"
    Environment = "production"
  }
}

# Proxy resource to catch all /api/* paths
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.countyiq.id
  parent_id   = aws_api_gateway_rest_api.countyiq.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy" {
  rest_api_id   = aws_api_gateway_rest_api.countyiq.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "lambda" {
  rest_api_id             = aws_api_gateway_rest_api.countyiq.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

# Also handle root path
resource "aws_api_gateway_method" "root" {
  rest_api_id   = aws_api_gateway_rest_api.countyiq.id
  resource_id   = aws_api_gateway_rest_api.countyiq.root_resource_id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "lambda_root" {
  rest_api_id             = aws_api_gateway_rest_api.countyiq.id
  resource_id             = aws_api_gateway_rest_api.countyiq.root_resource_id
  http_method             = aws_api_gateway_method.root.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

# --- API Gateway Deployment ---

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.countyiq.id

  # Force redeployment when any method or integration changes
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_method.proxy.id,
      aws_api_gateway_integration.lambda.id,
      aws_api_gateway_method.root.id,
      aws_api_gateway_integration.lambda_root.id,
    ]))
  }

  depends_on = [
    aws_api_gateway_integration.lambda,
    aws_api_gateway_integration.lambda_root,
  ]

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.countyiq.id
  stage_name    = "prod"

  tags = {
    Project     = "york-county-intel"
    Environment = "production"
  }
}

# --- Lambda Permission for API Gateway ---

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.countyiq.execution_arn}/*/*"
}

# --- CloudWatch Event: Lambda Keepalive (cold start mitigation) ---

resource "aws_cloudwatch_event_rule" "lambda_keepalive" {
  name                = "york-county-api-keepalive"
  description         = "Ping Lambda every 5 minutes to prevent cold starts"
  schedule_expression = "rate(5 minutes)"

  tags = {
    Project = "york-county-intel"
  }
}

resource "aws_cloudwatch_event_target" "lambda_keepalive" {
  rule = aws_cloudwatch_event_rule.lambda_keepalive.name
  arn  = aws_lambda_function.api.arn

  input = jsonencode({
    httpMethod = "GET"
    path       = "/api/health"
    resource   = "/{proxy+}"
    pathParameters = {
      proxy = "api/health"
    }
    requestContext = {
      httpMethod = "GET"
      path       = "/api/health"
    }
    headers     = {}
    queryStringParameters = null
    body        = null
    isBase64Encoded = false
  })
}

resource "aws_lambda_permission" "cloudwatch_keepalive" {
  statement_id  = "AllowCloudWatchKeepalive"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.lambda_keepalive.arn
}
