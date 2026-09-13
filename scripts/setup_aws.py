#!/usr/bin/env python3
"""
Setup Script for AutoResearch AWS Infrastructure
Creates DynamoDB table 'autoresearch-sessions' and S3 bucket 'autoresearch-reports'
using boto3 based on environment configuration in .env.
"""

import sys
import os
from pathlib import Path

# Add project root to python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import boto3
from botocore.exceptions import ClientError
from backend.app.config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    DYNAMODB_TABLE_NAME,
    S3_BUCKET_NAME
)

def get_boto3_session():
    kwargs = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
    return boto3.Session(**kwargs)

def setup_dynamodb(session):
    print(f"[*] Checking DynamoDB table '{DYNAMODB_TABLE_NAME}' in region '{AWS_REGION}'...")
    dynamodb = session.resource("dynamodb")
    client = session.client("dynamodb")

    try:
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)
        table.load()
        print(f"[✓] DynamoDB table '{DYNAMODB_TABLE_NAME}' already exists (Status: {table.table_status}).")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"[+] Table '{DYNAMODB_TABLE_NAME}' not found. Creating table...")
            try:
                table = dynamodb.create_table(
                    TableName=DYNAMODB_TABLE_NAME,
                    KeySchema=[
                        {"AttributeName": "session_id", "KeyType": "HASH"}  # Partition key
                    ],
                    AttributeDefinitions=[
                        {"AttributeName": "session_id", "AttributeType": "S"}
                    ],
                    BillingMode="PAY_PER_REQUEST"
                )
                print(f"[*] Waiting for DynamoDB table creation...")
                table.meta.client.get_waiter("table_exists").wait(TableName=DYNAMODB_TABLE_NAME)
                print(f"[✓] DynamoDB table '{DYNAMODB_TABLE_NAME}' created successfully!")
            except Exception as create_err:
                print(f"[X] Failed to create DynamoDB table: {create_err}")
        else:
            print(f"[X] DynamoDB Error: {e}")

def setup_s3(session):
    print(f"[*] Checking S3 bucket '{S3_BUCKET_NAME}'...")
    s3_client = session.client("s3")

    try:
        s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
        print(f"[✓] S3 bucket '{S3_BUCKET_NAME}' already exists.")
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ["404", "NoSuchBucket"]:
            print(f"[+] S3 bucket '{S3_BUCKET_NAME}' not found. Creating bucket...")
            try:
                if AWS_REGION == "us-east-1":
                    s3_client.create_bucket(Bucket=S3_BUCKET_NAME)
                else:
                    s3_client.create_bucket(
                        Bucket=S3_BUCKET_NAME,
                        CreateBucketConfiguration={"LocationConstraint": AWS_REGION}
                    )
                
                # Apply block public access
                s3_client.put_public_access_block(
                    Bucket=S3_BUCKET_NAME,
                    PublicAccessBlockConfiguration={
                        "BlockPublicAcls": True,
                        "IgnorePublicAcls": True,
                        "BlockPublicPolicy": True,
                        "RestrictPublicBuckets": True
                    }
                )
                print(f"[✓] S3 bucket '{S3_BUCKET_NAME}' created successfully with public access blocked!")
            except Exception as create_err:
                print(f"[X] Failed to create S3 bucket: {create_err}")
        else:
            print(f"[X] S3 Error ({error_code}): {e}")

def main():
    print("=" * 60)
    print("AutoResearch AWS Infrastructure Setup")
    print("=" * 60)
    session = get_boto3_session()
    setup_dynamodb(session)
    print("-" * 60)
    setup_s3(session)
    print("=" * 60)
    print("[✓] AWS Setup check completed.")

if __name__ == "__main__":
    main()
