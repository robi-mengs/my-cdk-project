import json
import os

import boto3
from botocore.config import Config

BUCKET_NAME = os.environ["BUCKET_NAME"]

s3_client = boto3.client("s3", config=Config(signature_version="s3v4"))

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    params = event.get("queryStringParameters") or {}
    action = params.get("action", "list").lower()

    if action == "list":
        result = s3_client.list_objects_v2(Bucket=BUCKET_NAME)
        files = [
            {"key": obj["Key"], "size": obj["Size"]}
            for obj in result.get("Contents", [])
        ]
        return _response(200, {"files": files})

    file_key = params.get("filename")
    if not file_key:
        return _response(400, {"error": "Missing required query parameter 'filename'"})

    if action == "download":
        client_method = "get_object"
        s3_params = {
            "Bucket": BUCKET_NAME,
            "Key": file_key,
            "ResponseContentDisposition": f'attachment; filename="{file_key}"',
        }
    elif action == "upload":
        client_method = "put_object"
        s3_params = {"Bucket": BUCKET_NAME, "Key": file_key}
    else:
        return _response(400, {"error": f"Unknown action '{action}'"})

    presigned_url = s3_client.generate_presigned_url(
        ClientMethod=client_method, Params=s3_params, ExpiresIn=1800
    )
    return _response(200, {"presignedUrl": presigned_url})
