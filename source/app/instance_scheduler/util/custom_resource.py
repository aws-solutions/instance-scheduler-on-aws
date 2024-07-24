# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import threading
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Literal,
    NotRequired,
    Optional,
    TypedDict,
    TypeGuard,
    TypeVar,
)

from urllib3 import HTTPResponse, PoolManager

from instance_scheduler.handler.base import MainHandler

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


class CustomResourceResponse(TypedDict):
    Status: str
    Reason: NotRequired[str]
    PhysicalResourceId: str
    NoEcho: NotRequired[bool]
    Data: NotRequired[dict[str, str]]
    # do not edit
    StackId: str
    RequestId: str
    LogicalResourceId: str


class CustomResource(
    Generic[ResourcePropertiesType],
    MainHandler[CustomResourceRequest[ResourcePropertiesType]],
    ABC,
):
    EVENT_TYPE_CREATE = "Create"
    EVENT_TYPE_UPDATE = "Update"
    EVENT_TYPE_DELETE = "Delete"

    def OkResponse(
        self,
        data: Optional[dict[str, str]] = None,
        reason: Optional[str] = None,
        no_echo: bool = False,
        physical_resource_id: Optional[str] = None,
    ) -> CustomResourceResponse:
        response: CustomResourceResponse = {
            "Status": "SUCCESS",
            "PhysicalResourceId": self.resolve_physical_resource_id(
                override=physical_resource_id
            ),
            "StackId": self.stack_id,
            "RequestId": self.request_id,
            "LogicalResourceId": self.logical_resource_id,
        }
        if data:
            response["Data"] = data
        if no_echo:
            response["NoEcho"] = True
        if reason:
            response["Reason"] = reason

        return response

    def ErrorResponse(
        self,
        reason: str,
        physical_resource_id: Optional[str] = None,
    ) -> CustomResourceResponse:
        """
        :param reason: the reason for the error
        :param physical_resource_id: custom resource physical id -- note. If using custom ids here,
        It is critical that they be consistent between Ok and Error responses,
        otherwise CloudFormation may generate additional delete calls on failed updates.
        :return:
        """
        response: CustomResourceResponse = {
            "Status": "FAILED",
            "Reason": reason,
            "PhysicalResourceId": self.resolve_physical_resource_id(
                override=physical_resource_id
            ),
            "StackId": self.stack_id,
            "RequestId": self.request_id,
            "LogicalResourceId": self.logical_resource_id,
        }

        return response

    def resolve_physical_resource_id(self, override: Optional[str] = None) -> str:
        # order of precendence:
        # id passed to this function > id included in event > generate new id
        if override:
            return override
        else:
            return self.physical_resource_id or self.new_physical_resource_id()

    def __init__(self, event: Mapping[str, Any], context: LambdaContext) -> None:
        self.event = event
        self.context = context
        # physical resource is empty for create request, for other requests is it the returned physical id from the create request
        self.physical_resource_id: Optional[str] = event.get("PhysicalResourceId")

    # Test if event is a request custom resource request from cloudformation
    @staticmethod
    def is_handling_request(
        event: Mapping[str, Any]
    ) -> TypeGuard[CustomResourceRequest[ResourcePropertiesType]]:
        return event.get("StackId") is not None

    # Returns Logical Resource Id in cloudformation stack
    @property
    def logical_resource_id(self) -> Any:
        # todo type this as "str" -- requires typing the event
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
    @abstractmethod
    def _create_request(self) -> CustomResourceResponse:
        return self.OkResponse(reason="No handler for Create request")

    # Handles Update request, overwrite in inherited class to implement update actions
    @abstractmethod
    def _update_request(self) -> CustomResourceResponse:
        return self.OkResponse(reason="No handler for Update request")

    # Handles Delete request, overwrite in inherited class to implement delete actions
    @abstractmethod
    def _delete_request(self) -> CustomResourceResponse:
        return self.OkResponse(reason="No handler for Delete request")

    def fn_timeout(self) -> None:
        print("Execution is about to time out, sending failure message")
        self._send_response(self.ErrorResponse(reason="Timeout"))

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

        response: CustomResourceResponse

        try:
            # Call handler for request type
            if self.request_type == CustomResource.EVENT_TYPE_CREATE:
                response = self._create_request()
            elif self.request_type == CustomResource.EVENT_TYPE_UPDATE:
                response = self._update_request()
            elif self.request_type == CustomResource.EVENT_TYPE_DELETE:
                response = self._delete_request()
            else:
                raise ValueError(
                    '"{}" is not a valid request type'.format(self.request_type)
                )
        except Exception as ex:
            response = self.ErrorResponse(reason=str(ex))

        timer.cancel()
        return self._send_response(response)

    # Send the response to cloudformation
    def _send_response(self, custom_resource_response: CustomResourceResponse) -> bool:
        # Build the PUT request and the response data
        # todo: need to trim response to 4KB (check ASR code for example)
        resp = json.dumps(custom_resource_response)

        headers = {"content-type": "", "content-length": str(len(resp))}

        # PUT request to cloudformation
        try:
            http = PoolManager()
            http_response: HTTPResponse = http.request(  # type: ignore[no-untyped-call]
                "PUT",
                self.response_url,
                headers=headers,
                body=resp,
            )
            print("Status code: {}".format(http_response.status))
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
