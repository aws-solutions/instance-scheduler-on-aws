# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Final, Literal

from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import (
    DynamoDBRecord,
)

from instance_scheduler.handler.schedule_update import schedule_names_from_records
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.in_memory_schedule_definition_store import (
    InMemoryScheduleDefinitionStore,
)


def ddb_record(
    *, record_type: Literal["schedule", "period"], record_name: str
) -> DynamoDBRecord:
    return DynamoDBRecord(
        {
            "eventID": "d9fffe842d88d0cc3d325208f0c3a7c5",
            "eventName": "MODIFY",
            "eventVersion": "1.1",
            "eventSource": "aws:dynamodb",
            "awsRegion": "us-west-2",
            "dynamodb": {
                "ApproximateCreationDateTime": 1708554658,
                "Keys": {
                    "name": {"S": record_name},
                    "type": {"S": record_type},
                },
                "SequenceNumber": "155230700000000069047952291",
                "SizeBytes": 35,
                "StreamViewType": "KEYS_ONLY",
            },
            "eventSourceARN": "arn:aws:dynamodb:us-west-2:111111111111:table/my-config-table/stream/2024-02-21T15:35:36.225",
        }
    )


def test_schedule_names_from_records() -> None:
    store: Final = InMemoryScheduleDefinitionStore(
        {
            "foo": ScheduleDefinition(
                name="foo",
                periods=[
                    PeriodIdentifier.of("a"),
                    PeriodIdentifier.of("b"),
                    PeriodIdentifier.of("c"),
                ],
            ),
            "bar": ScheduleDefinition(
                name="bar",
                periods=[
                    PeriodIdentifier.of("b"),
                    PeriodIdentifier.of("d"),
                    PeriodIdentifier.of("e"),
                ],
            ),
            "baz": ScheduleDefinition(
                name="baz",
                periods=[
                    PeriodIdentifier.of("a"),
                    PeriodIdentifier.of("f"),
                    PeriodIdentifier.of("g"),
                ],
            ),
            "qux": ScheduleDefinition(
                name="qux",
                periods=[
                    PeriodIdentifier.of("b"),
                    PeriodIdentifier.of("h"),
                    PeriodIdentifier.of("i"),
                ],
            ),
        }
    )

    periods: Final = [ddb_record(record_type="period", record_name="b")]

    assert set(schedule_names_from_records(periods, store)) == set(
        ["foo", "bar", "qux"]
    )

    schedules: Final = [ddb_record(record_type="schedule", record_name="bar")]

    assert list(schedule_names_from_records(schedules, store)) == ["bar"]

    mixed: Final = [
        ddb_record(record_type="period", record_name="h"),
        ddb_record(record_type="schedule", record_name="baz"),
    ]

    assert set(schedule_names_from_records(mixed, store)) == set(["baz", "qux"])
