#!/usr/bin/env python3
import aws_cdk as cdk

from tes_dev_cdk_sample.files_stack import FilesSampleStack
from tes_dev_cdk_sample.tes_dev_cdk_sample_stack import (
    TesDevCdkSampleStack,
    validate_owner,
)

# TES-DEV. Only us-east-1 is allowed in this account.
ACCOUNT = "785269092218"
REGION = "us-east-1"

app = cdk.App()
owner = validate_owner(app.node.try_get_context("owner"))

TesDevCdkSampleStack(
    app,
    f"NotesSample-{owner}",
    owner=owner,
    env=cdk.Environment(account=ACCOUNT, region=REGION),
    description=f"TES-DEV notes sample, owned by {owner}",
)

FilesSampleStack(
    app,
    f"FilesSample-{owner}",
    owner=owner,
    env=cdk.Environment(account=ACCOUNT, region=REGION),
    description=f"TES-DEV files sample, owned by {owner}",
)

# Tags land on every resource, so the console and the bill show whose it is.
cdk.Tags.of(app).add("owner", owner)
cdk.Tags.of(app).add("project", "tes-dev-cdk-sample")

app.synth()
