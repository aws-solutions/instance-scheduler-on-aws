# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import threading
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeGuard, TypeVar

import requests
from typing_extensions import NotRequired, TypedDict

from instance_scheduler.handler.base import Handler

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

ResourcePropertiesType = TypeVar("ResourcePropertiesType", bound=Mapping[str, Any])


class CustomResourceRequest(TypedDict, Generic[ResourcePropertiesType]):
    ServiceToken: str  # Lambda Function ARN
    RequestType: Literal["Create", "Update", "Delete"]
    ResponseURL: str  # CloudFormation pre-signed URL
    StackId: str  # CloudFormation Stack ARN
    RequestId: str  # UUID
    ResourceType: str
    LogicalResourceId: str
    PhysicalResourceId: str
    ResourceProperties: ResourcePropertiesType
    OldResourceProperties: NotRequired[ResourcePropertiesType]


class CustomResource(
    Generic[ResourcePropertiesType],
    Handler[CustomResourceRequest[ResourcePropertiesType]],
    ABC,
):
    EVENT_TYPE_CREATE = "Create"
    EVENT_TYPE_UPDATE = "Update"
    EVENT_TYPE_DELETE = "Delete"

    def __init__(self, event: Mapping[str, Any], context: LambdaContext) -> None:
        self.event = event
        self.context = context
        # physical resource is empty for create request, for other requests is it the returned physical id from the create request
        self.physical_resource_id = event.get("PhysicalResourceId")
        self.response = {
            "Data": {},
            "Reason": "",
            "StackId": self.stack_id,
            "RequestId": self.request_id,
            "LogicalResourceId": self.logical_resource_id,
        }

    # Returned attributes of custom resource
    @property
    def response_data(self) -> Any:
        return self.response["Data"]

    # Test if event is a request custom resource request from cloudformation
    @staticmethod
    def is_handling_request(
        event: Mapping[str, Any]
    ) -> TypeGuard[CustomResourceRequest[ResourcePropertiesType]]:
        return event.get("StackId") is not None

    # Returns Logical Resource Id in cloudformation stack
    @property
    def logical_resource_id(self) -> Any:
        return self.event.get("LogicalResourceId")

    # Returns the id of the cloudformation request
    @property
    def request_id(self) -> Any:
        return self.event.get("RequestId")

    # Returns the resource properties of the custom resource, these are used to pass data to te custom resource
    @property
    def resource_properties(self) -> ResourcePropertiesType:
        return self.event.get("ResourceProperties", {})

    # Returns the previous resource properties of the custom resource, these are used to customize the updates
    @property
    def old_resource_properties(self) -> ResourcePropertiesType:
        return self.event.get("OldResourceProperties", {})

    # Returns optional timeout
    @property
    def timeout(self) -> Any:
        return self.resource_properties.get("timeout", None)

    # Returns the type of the custom resource
    @property
    def resource_type(self) -> Any:
        return self.event.get("ResourceType")

    # Returns the URL to send the response to cloudformation with the result of the request
    @property
    def response_url(self) -> Any:
        return self.event.get("ResponseURL")

    # Returns the type of the request which can be one of the following: Create, Update, Delete
    @property
    def request_type(self) -> Any:
        return self.event.get("RequestType")

    # Returns the id of the stack
    @property
    def stack_id(self) -> Any:
        return self.event.get("StackId")

    # Returns the short name of the stack
    @property
    def stack_name(self) -> Any:
        sid = self.stack_id
        last = sid.split(":")[-1]
        name = last.split("/")[-2]
        return name

    @property
    def region(self) -> Any:
        return self.stack_id.split(":")[3]

    # Build unique physical id
    def new_physical_resource_id(self) -> str:
        uu = str(uuid.uuid4()).replace("-", "")[0:14]
        new_id = "{}-{}-{}".format(self.__class__.__name__, self.stack_name, uu)
        return new_id.lower()

    # Handles Create request, overwrite in inherited class to implement create actions
    # Return True on success, False if on failure
    @abstractmethod
    def _create_request(self) -> bool:
        self.response["Reason"] = "No handler for Create request"
        return True

    # Handles Update request, overwrite in inherited class to implement update actions
    # Return True on success, False if on failure
    @abstractmethod
    def _update_request(self) -> bool:
        self.response["Reason"] = "No handler for Update request"
        return True

    # Handles Delete request, overwrite in inherited class to implement delete actions
    # Return True on success, False if on failure
    @abstractmethod
    def _delete_request(self) -> bool:
        self.response["Reason"] = "No handler for Delete request"
        return True

    def fn_timeout(self) -> None:
        print("Execution is about to time out, sending failure message")
        self.response["Status"] = "FAILED"
        self.response["Reason"] = "Timeout"
        self._send_response()

    # Handles cloudformation request
    def handle_request(self) -> Any:
        timeleft = (
            (self.context.get_remaining_time_in_millis() / 1000.00) - 0.5
            if self.context is not None
            else 300
        )
        if self.timeout is not None:
            timeleft = min(timeleft, float(self.timeout))
        timer = threading.Timer(timeleft, self.fn_timeout)
        timer.start()

        try:
            # Call handler for request type
            if self.request_type == CustomResource.EVENT_TYPE_CREATE:
                result = self._create_request()
            elif self.request_type == CustomResource.EVENT_TYPE_UPDATE:
                result = self._update_request()
            elif self.request_type == CustomResource.EVENT_TYPE_DELETE:
                result = self._delete_request()
            else:
                raise ValueError(
                    '"{}" is not a valid request type'.format(self.request_type)
                )

            # Set status based on return value of handler
            self.response["Status"] = "SUCCESS" if result else "FAILED"

            # set physical resource id or create new one
            self.response["PhysicalResourceId"] = (
                self.physical_resource_id or self.new_physical_resource_id()
            )

        except Exception as ex:
            self.response["Status"] = "FAILED"
            self.response["Reason"] = str(ex)

        timer.cancel()
        return self._send_response()

    # Send the response to cloudformation
    def _send_response(self) -> bool:
        # Build the PUT request and the response data
        resp = json.dumps(self.response)

        headers = {"content-type": "", "content-length": str(len(resp))}

        # PUT request to cloudformation
        try:
            response = requests.put(
                self.response_url,
                data=json.dumps(self.response),
                headers=headers,
                timeout=300,
            )
            response.raise_for_status()
            print("Status code: {}".format(response.status_code))
            print("Status message: {}".format(response.text))
            return True
        except Exception as exc:
            print(
                "Failed executing HTTP request to respond to CloudFormation stack {}".format(
                    self.stack_id
                )
            )
            print("Error code is {}".format(str(exc)))
            print("Url is {}".format(self.response_url))
            print("Response data is {}".format(resp))
            return False
