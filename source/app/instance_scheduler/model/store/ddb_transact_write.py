# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import uuid
from types import TracebackType
from typing import TYPE_CHECKING, Optional, Self, Sequence

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_dynamodb.type_defs import TransactWriteItemTypeDef
else:
    DynamoDBClient = object
    TransactWriteItemTypeDef = object


class WriteTransaction:
    """
    A context manager object for a DynamoDB transact_write_items call.

    This transaction is will be automatically committed when __exit__ is called and may raise
    an exception when doing so

    refer to https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb/client/transact_write_items.html#
    for details
    """

    def __init__(self, client: DynamoDBClient) -> None:
        self._client = client
        self.transaction_items: list[TransactWriteItemTypeDef] = []
        self.request_token = str(uuid.uuid4())

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if exc_type is None:
            self._commit()
        else:
            pass  # exceptions allowed to bubble up to calling context

    def add(self, items: Sequence[TransactWriteItemTypeDef]) -> None:
        self.transaction_items.extend(items)

    def _commit(self) -> None:
        self._client.transact_write_items(
            TransactItems=self.transaction_items,
            ClientRequestToken=self.request_token,
        )
