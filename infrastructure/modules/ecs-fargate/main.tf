# ECS Fargate Module

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"
}

# TODO: Add task definition, service, security groups
