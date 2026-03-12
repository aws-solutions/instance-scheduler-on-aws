# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator


class MockEnvironment(ABC):
    @abstractmethod
    @contextmanager
    def patch_env(self, clear: bool = True) -> Iterator[None]:
        """Context manager that patches environment variables."""
        pass
