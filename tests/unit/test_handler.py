"""Tests for the Lambda code, with an in-memory stand-in for the DynamoDB table."""

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

HANDLER = Path(__file__).parents[2] / "lambda" / "handler.py"


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        # Real DynamoDB returns numbers as Decimal; mimic that.
        self.items[Item["id"]] = {
            k: Decimal(v) if isinstance(v, int) else v for k, v in Item.items()
        }

    def get_item(self, Key):
        item = self.items.get(Key["id"])
        return {"Item": item} if item else {}

    def delete_item(self, Key):
        self.items.pop(Key["id"], None)

    def scan(self, Limit):
        return {"Items": list(self.items.values())[:Limit]}


@pytest.fixture
def handler(monkeypatch):
    spec = importlib.util.spec_from_file_location("handler", HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_table", FakeTable())
    return module


def call(handler, route, body=None, note_id=None):
    event = {"routeKey": route}
    if body is not None:
        event["body"] = body if isinstance(body, str) else json.dumps(body)
    if note_id:
        event["pathParameters"] = {"id": note_id}
    response = handler.main(event, None)
    return response["statusCode"], json.loads(response["body"]) if "body" in response else None


def test_create_then_read_then_delete(handler):
    status, note = call(handler, "POST /notes", {"text": "  hello  "})
    assert status == 201
    assert note["text"] == "hello"

    status, fetched = call(handler, "GET /notes/{id}", note_id=note["id"])
    assert status == 200
    assert fetched == note  # also proves Decimal from DynamoDB serialises

    status, body = call(handler, "DELETE /notes/{id}", note_id=note["id"])
    assert (status, body) == (204, None)

    status, _ = call(handler, "GET /notes/{id}", note_id=note["id"])
    assert status == 404


def test_list_is_newest_first(handler):
    handler._table.put_item(Item={"id": "old", "text": "a", "created_at": 1})
    handler._table.put_item(Item={"id": "new", "text": "b", "created_at": 2})
    status, notes = call(handler, "GET /notes")
    assert status == 200
    assert [n["id"] for n in notes] == ["new", "old"]


@pytest.mark.parametrize(
    "body",
    ["not json", {"text": ""}, {"text": "   "}, {"text": 42}, {}, ["a list"], {"text": "x" * 1001}],
)
def test_bad_input_is_rejected(handler, body):
    status, response = call(handler, "POST /notes", body)
    assert status == 400
    assert "error" in response


def test_unknown_route(handler):
    status, _ = call(handler, "PUT /notes")
    assert status == 404
