# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import threading
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    List,
    NotRequired,
    Optional,
    TypedDict,
    TypeGuard,
    TypeVar,
)

from instance_scheduler.handler.base import MainHandler
from instance_scheduler.util.custom_resource import (
    CustomResourceRequest,
)

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object

ResourcePropertiesType = TypeVar("ResourcePropertiesType", bound=Mapping[str, Any])


class CustomResourceWaiterResponse(TypedDict):
    IsComplete: bool
    Status: NotRequired[str]


class CustomResourceWaiter(
    Generic[ResourcePropertiesType],
    MainHandler[CustomResourceRequest[ResourcePropertiesType]],
    ABC,
):
    EVENT_TYPE_CREATE = "Create"
    EVENT_TYPE_UPDATE = "Update"
    EVENT_TYPE_DELETE = "Delete"

    def OkResponse(
        self,
        is_complete: bool = False,
    ) -> CustomResourceWaiterResponse:
        response: CustomResourceWaiterResponse = {
            "IsComplete": is_complete,
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
        event: Mapping[str, Any],
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
        return self.event.get("ResourceProperties", {})  # type: ignore

    # Returns the previous resource properties of the custom resource, these are used to customize the updates
    @property
    def old_resource_properties(self) -> ResourcePropertiesType:
        return self.event.get("OldResourceProperties", {})  # type: ignore

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

    def purge_empty_strings(
        self, resource_properties: ResourcePropertiesType, attribute_name: str
    ) -> List[str]:
        attribute_value: List[str] = resource_properties.get(attribute_name, [])

        if len(attribute_value) == 1 and attribute_value[0] == "":
            return []
        return attribute_value

    # Handles Create request, overwrite in inherited class to implement create actions
    @abstractmethod
    def _create_request(self) -> CustomResourceWaiterResponse:
        return self.OkResponse()

    # Handles Update request, overwrite in inherited class to implement update actions
    @abstractmethod
    def _update_request(self) -> CustomResourceWaiterResponse:
        return self.OkResponse()

    # Handles Delete request, overwrite in inherited class to implement delete actions
    @abstractmethod
    def _delete_request(self) -> CustomResourceWaiterResponse:
        return self.OkResponse()

    def fn_timeout(self) -> None:
        # time out is managed by the custom resource provider
        pass

    # Handles cloudformation request
    def handle_request(self) -> CustomResourceWaiterResponse:
        timeleft = (
            (self.context.get_remaining_time_in_millis() / 1000.00) - 0.5
            if self.context is not None
            else 300
        )
        if self.timeout is not None:
            timeleft = min(timeleft, float(self.timeout))
        timer = threading.Timer(timeleft, self.fn_timeout)
        timer.start()

        response: CustomResourceWaiterResponse

        # Call handler for request type
        if self.request_type == CustomResourceWaiter.EVENT_TYPE_CREATE:
            response = self._create_request()
        elif self.request_type == CustomResourceWaiter.EVENT_TYPE_UPDATE:
            response = self._update_request()
        elif self.request_type == CustomResourceWaiter.EVENT_TYPE_DELETE:
            response = self._delete_request()
        else:
            raise ValueError(
                '"{}" is not a valid request type'.format(self.request_type)
            )

        timer.cancel()
        return response
