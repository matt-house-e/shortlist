# S3 backend for state storage
# Uncomment and configure for your environment

# terraform {
#   backend "s3" {
#     bucket         = "your-terraform-state-bucket"
#     key            = "agent-template/terraform.tfstate"
#     region         = "us-east-1"
#     encrypt        = true
#     dynamodb_table = "terraform-state-lock"
#   }
# }
