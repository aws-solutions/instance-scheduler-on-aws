# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Generic, TypeGuard, TypeVar

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

T = TypeVar("T")


class Handler(ABC, Generic[T]):
    @classmethod
    @abstractmethod
    def is_handling_request(cls, event: Mapping[str, Any]) -> TypeGuard[T]:
        pass

    @abstractmethod
    def __init__(self, event: T, context: LambdaContext) -> None:
        pass

    @abstractmethod
    def handle_request(self) -> Any:
        pass
