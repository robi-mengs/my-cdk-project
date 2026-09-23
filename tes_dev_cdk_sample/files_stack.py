from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_apigatewayv2 as apigw,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk.aws_apigatewayv2_integrations import HttpLambdaIntegration
from constructs import Construct

LAMBDA_DIR = Path(__file__).parent.parent / "lambda" / "files_lambda"


class FilesSampleStack(Stack):
    """A small file upload/download app: browser -> API Gateway -> Lambda -> S3 (presigned URLs)."""

    def __init__(
        self, scope: Construct, construct_id: str, *, owner: str, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # DESTROY + auto_delete_objects means `cdk destroy` removes everything, files included.
        bucket = s3.Bucket(
            self,
            "FilesBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.PUT,
                        s3.HttpMethods.HEAD,
                    ],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
        )

        log_group = logs.LogGroup(
            self,
            "FilesFunctionLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        files_fn = lambda_.Function(
            self,
            "FilesFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(str(LAMBDA_DIR)),
            memory_size=256,
            timeout=Duration.seconds(10),
            log_group=log_group,
            environment={"BUCKET_NAME": bucket.bucket_name},
        )

        # Scoped to just this one bucket - never dynamodb:*/s3:* broadly.
        bucket.grant_read_write(files_fn)

        api = apigw.HttpApi(
            self,
            "FilesApi",
            description=f"Files sample API ({owner})",
            create_default_stage=False,
        )
        apigw.HttpStage(
            self,
            "FilesDefaultStage",
            http_api=api,
            stage_name="$default",
            auto_deploy=True,
            throttle=apigw.ThrottleSettings(rate_limit=10, burst_limit=20),
        )

        integration = HttpLambdaIntegration("FilesIntegration", files_fn)
        api.add_routes(
            path="/files", methods=[apigw.HttpMethod.GET], integration=integration
        )

        CfnOutput(self, "FilesApiUrl", value=api.api_endpoint)
        CfnOutput(self, "FilesBucketName", value=bucket.bucket_name)
