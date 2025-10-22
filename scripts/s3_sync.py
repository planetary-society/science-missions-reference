#!/usr/bin/env python3
"""
s3_sync.py - Utility script to upload JSON files to an S3 bucket.

This simplified version uploads local files to S3 without requiring list permissions.
It supports only uploading files, not deleting those that don't exist locally.

Prerequisites:
- AWS CLI installed and configured with appropriate credentials
- The boto3 Python package (pip install boto3)
- A profile named 'json_files' in ~/.aws/credentials
"""

import sys
import argparse
import boto3
from pathlib import Path
from botocore.exceptions import ClientError

def upload_file(s3_client, file_path, bucket, s3_key):
    """Upload a file to an S3 bucket."""
    try:
        s3_client.upload_file(
            file_path, 
            bucket, 
            s3_key,
            ExtraArgs={'ContentType': get_content_type(file_path)}
        )
        return True
    except ClientError as e:
        print(f"Error uploading {file_path}: {e}")
        return False

def get_content_type(file_path):
    """Determine the content type based on file extension."""
    extension = Path(file_path).suffix.lower()
    content_types = {
        '.json': 'application/json',
    }
    return content_types.get(extension, 'application/octet-stream')

def upload_directory_to_s3(local_dir, bucket_name, s3_prefix, dry_run=False):
    """Upload JSON files from a local directory to an S3 bucket without listing existing objects."""
    session = boto3.Session(profile_name='json_files')
    s3_client = session.client('s3')
    local_dir = Path(local_dir)
    
    if dry_run:
        print(f"DRY RUN: Would upload files from {local_dir} to s3://{bucket_name}/{s3_prefix}")
    
    # Track successful uploads
    uploaded_count = 0
    
    # Upload all JSON files in the local directory
    ALLOWED_TYPES = ['.json']
    for file_path in local_dir.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in ALLOWED_TYPES:
            # Get the relative path from the local_dir
            relative_path = file_path.relative_to(local_dir)
            s3_key = str(Path(s3_prefix) / relative_path)
            
            if dry_run:
                print(f"DRY RUN: Would upload {file_path} to s3://{bucket_name}/{s3_key}")
                uploaded_count += 1
            else:
                print(f"Uploading {file_path} to s3://{bucket_name}/{s3_key}")
                if upload_file(s3_client, str(file_path), bucket_name, s3_key):
                    uploaded_count += 1
    
    # Report results
    if dry_run:
        print(f"DRY RUN: Would upload {uploaded_count} files to s3://{bucket_name}/{s3_prefix}")
    else:
        print(f"Upload completed. {uploaded_count} files uploaded to s3://{bucket_name}/{s3_prefix}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Upload JSON files from a local directory to an S3 bucket")
    parser.add_argument("--local-dir", default="site/data", help="Local directory to upload (default: site/data)")
    parser.add_argument("--bucket", default="planetary", help="S3 bucket name (default: planetary)")
    parser.add_argument("--prefix", default="assets/json/", help="S3 prefix (default: assets/json/)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without uploading")
    
    args = parser.parse_args()
    
    local_dir = Path(args.local_dir)
    if not local_dir.exists() or not local_dir.is_dir():
        print(f"Error: {local_dir} does not exist or is not a directory")
        return 1
    
    success = upload_directory_to_s3(
        local_dir=args.local_dir,
        bucket_name=args.bucket,
        s3_prefix=args.prefix,
        dry_run=args.dry_run
    )
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())