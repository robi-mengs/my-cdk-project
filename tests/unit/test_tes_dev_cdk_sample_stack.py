import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from tes_dev_cdk_sample.tes_dev_cdk_sample_stack import TesDevCdkSampleStack, validate_owner

ENV = cdk.Environment(account="785269092218", region="us-east-1")


@pytest.fixture(scope="module")
def template() -> Template:
    app = cdk.App()
    stack = TesDevCdkSampleStack(app, "NotesSample-test", owner="test", env=ENV)
    return Template.from_stack(stack)


# ── What the stack contains ─────────────────────────────────────────────


def test_only_cheap_serverless_resources(template):
    """Nothing that bills by the hour. If you add a resource type, add it here on purpose."""
    allowed = {
        "AWS::ApiGatewayV2::Api",
        "AWS::ApiGatewayV2::Integration",
        "AWS::ApiGatewayV2::Route",
        "AWS::ApiGatewayV2::Stage",
        "AWS::DynamoDB::GlobalTable",
        "AWS::IAM::Policy",
        "AWS::IAM::Role",
        "AWS::Lambda::Function",
        "AWS::Lambda::Permission",
        "AWS::Logs::LogGroup",
        "AWS::CDK::Metadata",
    }
    found = {r["Type"] for r in template.to_json()["Resources"].values()}
    assert found <= allowed, f"unexpected resource types: {sorted(found - allowed)}"


def test_table_is_on_demand_and_deleted_with_the_stack(template):
    template.has_resource(
        "AWS::DynamoDB::GlobalTable",
        {"Properties": {"BillingMode": "PAY_PER_REQUEST"}, "DeletionPolicy": "Delete"},
    )


def test_function_runs_python_313_on_arm(template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"Runtime": "python3.13", "Architectures": ["arm64"], "Handler": "handler.main"},
    )


def test_logs_expire_after_a_week(template):
    template.has_resource(
        "AWS::Logs::LogGroup",
        {"Properties": {"RetentionInDays": 7}, "DeletionPolicy": "Delete"},
    )


def test_api_is_throttled(template):
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Stage",
        {"StageName": "$default", "DefaultRouteSettings": {"ThrottlingRateLimit": 10}},
    )


def test_all_four_routes_exist(template):
    for route in ("GET /notes", "POST /notes", "GET /notes/{id}", "DELETE /notes/{id}"):
        template.has_resource_properties("AWS::ApiGatewayV2::Route", {"RouteKey": route})


# ── Least privilege ─────────────────────────────────────────────────────


def test_function_can_only_touch_its_own_table(template):
    """grant_read_write_data should produce table-scoped statements, never a wildcard."""
    policies = template.find_resources("AWS::IAM::Policy")
    statements = [
        s for p in policies.values() for s in p["Properties"]["PolicyDocument"]["Statement"]
    ]
    assert statements, "the function should have a DynamoDB policy"
    for s in statements:
        actions = s["Action"] if isinstance(s["Action"], list) else [s["Action"]]
        resources = s["Resource"] if isinstance(s["Resource"], list) else [s["Resource"]]
        assert "*" not in actions and "dynamodb:*" not in actions, s
        assert "*" not in resources, f"statement is not scoped to the table: {s}"


def test_no_role_gets_admin(template):
    template.resource_properties_count_is(
        "AWS::IAM::Role",
        {"ManagedPolicyArns": Match.array_with([Match.string_like_regexp("AdministratorAccess")])},
        0,
    )


# ── Sharing one account ─────────────────────────────────────────────────


@pytest.mark.parametrize("owner", [None, "", "Robiel", "a", "has space", "x" * 21, "1abc"])
def test_bad_owner_is_rejected(owner):
    with pytest.raises(ValueError, match="owner=yourname"):
        validate_owner(owner)


@pytest.mark.parametrize("owner", ["robiel", "weldu", "team-2"])
def test_good_owner_is_accepted(owner):
    assert validate_owner(owner) == owner


def test_two_owners_get_separate_stacks():
    app = cdk.App()
    a = TesDevCdkSampleStack(app, "NotesSample-robiel", owner="robiel", env=ENV)
    b = TesDevCdkSampleStack(app, "NotesSample-weldu", owner="weldu", env=ENV)
    assert a.stack_name != b.stack_name
    # No hardcoded physical names, so the resources cannot collide either.
    for stack in (a, b):
        table = Template.from_stack(stack).find_resources("AWS::DynamoDB::GlobalTable")
        assert all("TableName" not in t["Properties"] for t in table.values())
