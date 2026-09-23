import re
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigw,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_logs as logs,
)
from aws_cdk.aws_apigatewayv2_integrations import HttpLambdaIntegration
from constructs import Construct

LAMBDA_DIR = Path(__file__).parent.parent / "lambda"

OWNER_PATTERN = re.compile(r"[a-z][a-z0-9-]{1,19}")


def validate_owner(owner: str | None) -> str:
    """Everyone shares one AWS account, so every stack is named after its owner.

    Without this, two people deploying the same app would overwrite each other's stack.
    """
    if not owner or not OWNER_PATTERN.fullmatch(owner):
        raise ValueError(
            "Tell CDK whose stack this is: cdk deploy -c owner=yourname "
            "(2-20 characters: lowercase letters, digits and dashes, starting with a letter)"
        )
    return owner


class TesDevCdkSampleStack(Stack):
    """A small notes API: HTTP API -> Lambda -> DynamoDB.

    Everything here costs nothing while idle, and `cdk destroy` removes all of it.
    """

    def __init__(self, scope: Construct, construct_id: str, *, owner: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # On-demand billing: you pay per request, nothing while idle.
        table = dynamodb.TableV2(
            self,
            "NotesTable",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing=dynamodb.Billing.on_demand(),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Declared explicitly so logs expire after a week and are deleted with the stack.
        log_group = logs.LogGroup(
            self,
            "NotesFunctionLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        notes_fn = lambda_.Function(
            self,
            "NotesFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="handler.main",
            code=lambda_.Code.from_asset(str(LAMBDA_DIR)),
            memory_size=256,
            timeout=Duration.seconds(10),
            log_group=log_group,
            environment={"TABLE_NAME": table.table_name, "OWNER": owner},
        )

        # grant_* writes a policy scoped to this one table. Never hand a function "dynamodb:*".
        table.grant_read_write_data(notes_fn)

        api = apigw.HttpApi(
            self,
            "NotesApi",
            description=f"Notes sample API ({owner})",
            create_default_stage=False,
        )
        # Throttled, because the URL is public: anyone who finds it can call it.
        apigw.HttpStage(
            self,
            "DefaultStage",
            http_api=api,
            stage_name="$default",
            auto_deploy=True,
            throttle=apigw.ThrottleSettings(rate_limit=10, burst_limit=20),
        )

        integration = HttpLambdaIntegration("NotesIntegration", notes_fn)
        api.add_routes(
            path="/notes",
            methods=[apigw.HttpMethod.GET, apigw.HttpMethod.POST],
            integration=integration,
        )
        api.add_routes(
            path="/notes/{id}",
            methods=[apigw.HttpMethod.GET, apigw.HttpMethod.DELETE],
            integration=integration,
        )

        CfnOutput(self, "ApiUrl", value=api.api_endpoint)
        CfnOutput(self, "TableName", value=table.table_name)
