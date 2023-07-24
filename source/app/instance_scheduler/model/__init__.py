# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Persistence models and stores for data types used by Instance Scheduler.

Models
    Model are implemented as dataclasses. They are well-typed representations of the
    data types stored by Instance scheduler. They are validated on creation and frozen.

    Models implement two static constructors as required: 1/ from the service response
    describing that data type, and 2/ from the DyanmoDB GetItem response. They also
    implement a transformation to a `dict[str, AttributeValueTypeDef]` suitable for
    calls to DynamoDB PutItem, and a transformation to a `dict[str, str]` suitable for
    calls to DynamoDB DeleteItem.

Stores
    Stores implement an interface for list, get, put, and delete as needed for a model.

    Stores are backed by Amazon DynamoDB.

Maintenance windows
    Classes for persistence of representations of EC2 maintenance windows as implemented
    by AWS Systems Manager.

    Model: `EC2SSMMaintenanceWindow`
        Raises `EC2SSMMaintenanceWindowValidationError` on validation error
    Store: `EC2SSMMaintenanceWindowStore`
"""
from .maint_win import EC2SSMMaintenanceWindow, EC2SSMMaintenanceWindowValidationError
from .maint_win_store import EC2SSMMaintenanceWindowStore

__all__ = [
    "EC2SSMMaintenanceWindow",
    "EC2SSMMaintenanceWindowStore",
    "EC2SSMMaintenanceWindowValidationError",
]
