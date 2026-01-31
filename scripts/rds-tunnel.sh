#!/bin/bash
# SSH tunnel to production RDS
# Usage: ./rds-tunnel.sh

# TODO: Configure bastion host and RDS endpoint
# ssh -L 5433:rds-endpoint:5432 ec2-user@bastion-host
