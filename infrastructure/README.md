# Infrastructure

Terraform modules for AWS deployment.

## Structure

```
infrastructure/
├── shared/           # Provider config, backend
├── modules/          # Reusable modules
└── environments/     # Environment-specific config
```

## Usage

```bash
cd environments/production
terraform init
terraform plan
terraform apply
```
