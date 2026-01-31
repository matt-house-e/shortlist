#!/bin/bash
# Initialize LocalStack S3 bucket

awslocal s3 mb s3://uploads
echo "Created S3 bucket: uploads"
