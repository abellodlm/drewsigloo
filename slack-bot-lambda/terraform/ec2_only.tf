terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Variables
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "api_key" {
  description = "Talos API Key"
  type        = string
  sensitive   = true
}

variable "api_secret" {
  description = "Talos API Secret"
  type        = string
  sensitive   = true
}

variable "api_host" {
  description = "Talos API Host"
  type        = string
}

variable "slack_bot_token" {
  description = "Slack Bot Token"
  type        = string
  sensitive   = true
}

# Data sources
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

# IAM Role for EC2 Instance
resource "aws_iam_role" "talos_monitor_role" {
  name = "talos-monitor-ec2-role-${var.environment}"

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
    Environment = var.environment
  }
}

# IAM Policy for DynamoDB Access and Logs
resource "aws_iam_policy" "talos_monitor_policy" {
  name = "talos-monitor-policy-${var.environment}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = [
          "arn:aws:dynamodb:${var.aws_region}:*:table/monitor-bot-${var.environment}",
          "arn:aws:dynamodb:${var.aws_region}:*:table/monitor-bot-${var.environment}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:*"
      }
    ]
  })
}

# Attach policy to role
resource "aws_iam_role_policy_attachment" "talos_monitor_policy_attachment" {
  role       = aws_iam_role.talos_monitor_role.name
  policy_arn = aws_iam_policy.talos_monitor_policy.arn
}

# Instance profile
resource "aws_iam_instance_profile" "talos_monitor_profile" {
  name = "talos-monitor-profile-${var.environment}"
  role = aws_iam_role.talos_monitor_role.name
}

# Security Group for EC2
resource "aws_security_group" "talos_monitor_sg" {
  name        = "talos-monitor-sg-${var.environment}"
  description = "Security group for Talos WebSocket monitor"
  vpc_id      = data.aws_vpc.default.id

  # Outbound HTTPS for Talos API and Slack
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Outbound HTTP for package installation
  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Optional: SSH access (remove in production)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Restrict this to your IP
  }

  tags = {
    Name        = "talos-monitor-sg-${var.environment}"
    Environment = var.environment
  }
}

# Launch Template for Auto Scaling
resource "aws_launch_template" "talos_monitor_template" {
  name_prefix   = "talos-monitor-${var.environment}-"
  image_id      = data.aws_ami.amazon_linux.id
  instance_type = "t3.micro"

  vpc_security_group_ids = [aws_security_group.talos_monitor_sg.id]

  iam_instance_profile {
    name = aws_iam_instance_profile.talos_monitor_profile.name
  }

  user_data = base64encode(templatefile("${path.module}/user_data_ec2_only.sh", {
    aws_region     = var.aws_region
    environment    = var.environment
    api_key        = var.api_key
    api_secret     = var.api_secret
    api_host       = var.api_host
    slack_bot_token = var.slack_bot_token
  }))

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name        = "talos-monitor-${var.environment}"
      Environment = var.environment
      Purpose     = "Talos WebSocket Monitor"
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Auto Scaling Group
resource "aws_autoscaling_group" "talos_monitor_asg" {
  name               = "talos-monitor-asg-${var.environment}"
  vpc_zone_identifier = data.aws_subnets.default.ids
  target_group_arns  = []
  health_check_type  = "EC2"
  
  min_size         = 1
  max_size         = 1
  desired_capacity = 1

  launch_template {
    id      = aws_launch_template.talos_monitor_template.id
    version = "$Latest"
  }

  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 0  # Allow complete replacement since we only have 1 instance
    }
  }

  tag {
    key                 = "Name"
    value               = "talos-monitor-asg-${var.environment}"
    propagate_at_launch = false
  }

  tag {
    key                 = "Environment"
    value               = var.environment
    propagate_at_launch = true
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "talos_monitor_logs" {
  name              = "/aws/ec2/talos-monitor-${var.environment}"
  retention_in_days = 7

  tags = {
    Environment = var.environment
  }
}

# Outputs
output "auto_scaling_group_name" {
  description = "Name of the Auto Scaling Group"
  value       = aws_autoscaling_group.talos_monitor_asg.name
}

output "security_group_id" {
  description = "Security Group ID"
  value       = aws_security_group.talos_monitor_sg.id
}

output "log_group_name" {
  description = "CloudWatch Log Group name"
  value       = aws_cloudwatch_log_group.talos_monitor_logs.name
}