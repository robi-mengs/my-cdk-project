"""Notes API. One function serves every route; API Gateway says which in `routeKey`."""

import json
import os
import time
import uuid
from decimal import Decimal

import boto3

_table = None


def table():
    # Created on first use rather than at import, so tests can swap in a fake.
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


def _decimal(value):
    # DynamoDB hands numbers back as Decimal, which json cannot serialise on its own.
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


def respond(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=_decimal),
    }


def list_notes(event):
    # A scan reads the whole table. Fine for a demo; a real app would query an index.
    items = table().scan(Limit=100).get("Items", [])
    return respond(200, sorted(items, key=lambda n: n["created_at"], reverse=True))


def create_note(event):
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return respond(400, {"error": "body must be JSON"})

    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        return respond(400, {"error": 'send {"text": "..."}'})
    if len(text) > 1000:
        return respond(400, {"error": "text is limited to 1000 characters"})

    note = {"id": str(uuid.uuid4()), "text": text.strip(), "created_at": int(time.time())}
    table().put_item(Item=note)
    return respond(201, note)


def get_note(event):
    note = table().get_item(Key={"id": event["pathParameters"]["id"]}).get("Item")
    return respond(200, note) if note else respond(404, {"error": "not found"})


def delete_note(event):
    table().delete_item(Key={"id": event["pathParameters"]["id"]})
    return {"statusCode": 204}  # 204 means "no body", so send none


ROUTES = {
    "GET /notes": list_notes,
    "POST /notes": create_note,
    "GET /notes/{id}": get_note,
    "DELETE /notes/{id}": delete_note,
}


def main(event, context):
    route = ROUTES.get(event.get("routeKey"))
    if route is None:
        return respond(404, {"error": "no such route"})
    return route(event)
