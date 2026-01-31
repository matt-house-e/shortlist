# Production Environment

variable "aws_region" {
  default = "us-east-1"
}

variable "project_name" {
  default = "agent-template"
}

variable "environment" {
  default = "production"
}

module "vpc" {
  source       = "../../modules/vpc"
  project_name = var.project_name
}

module "ecs" {
  source       = "../../modules/ecs-fargate"
  project_name = var.project_name
  vpc_id       = module.vpc.vpc_id
}
