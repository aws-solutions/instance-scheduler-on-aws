######################################################################################################################
#  Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance     #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://www.apache.org/licenses/                                                                               #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

import json
import threading
import uuid

import requests


class CustomResource:
    EVENT_TYPE_CREATE = "Create"
    EVENT_TYPE_UPDATE = "Update"
    EVENT_TYPE_DELETE = "Delete"

    def __init__(self, event, context):
        self.event = event
        self.context = context
        # physical resource is empty for create request, for other requests is it the returned physical id from the create request
        self.physical_resource_id = event.get("PhysicalResourceId")
        self.response = {
            "Data": {},
            "Reason": "",
            "StackId": self.stack_id,
            "RequestId": self.request_id,
            "LogicalResourceId": self.logical_resource_id
        }

    # Returned attributes of custom resource
    @property
    def response_data(self):
        return self.response["Data"]

    # Test if event is a request custom resource request from cloudformation
    @staticmethod
    def is_handling_request(event):
        return event.get("StackId") is not None

    # Returns Logical Resource Id in cloudformation stack
    @property
    def logical_resource_id(self):
        return self.event.get("LogicalResourceId")

    # Returns the id of the cloudformation request
    @property
    def request_id(self):
        return self.event.get("RequestId")

    # Returns the resource properties of the custom resource, these are used to pass data to te custom resource
    @property
    def resource_properties(self):
        return self.event.get("ResourceProperties", {})

    # Returns optional timeout
    @property
    def timeout(self):
        return self.resource_properties.get("timeout", None)

    # Returns the type of the custom resource
    @property
    def resource_type(self):
        return self.event.get("ResourceType")

    # Returns the URL to send the response to cloudformation with the result of the request
    @property
    def response_url(self):
        return self.event.get("ResponseURL")

    # Returns the type of the request which can be one of the following: Create, Update, Delete
    @property
    def request_type(self):
        return self.event.get("RequestType")

    # Returns the service token of the request
    @property
    def service_token(self):
        return self.event.get("ServiceToken")

    # Returns the id of the stack
    @property
    def stack_id(self):
        return self.event.get("StackId")

    # Returns the short name of the stack
    @property
    def stack_name(self):
        sid = self.stack_id
        last = sid.split(":")[-1]
        name = last.split("/")[-2]
        return name

    @property
    def region(self):
        return self.stack_id.split(":")[3]

    # Build unique physical id
    def new_physical_resource_id(self):
        uu = str(uuid.uuid4()).replace("-", "")[0:14]
        new_id = "{}-{}-{}".format(self.__class__.__name__, self.stack_name, uu)
        return new_id.lower()

    # Handles Create request, overwrite in inherited class to implement create actions
    # Return True on success, False if on failure
    def _create_request(self):
        self.response["Reason"] = "No handler for Create request"
        return True

    # Handles Update request, overwrite in inherited class to implement update actions
    # Return True on success, False if on failure
    def _update_request(self):
        self.response["Reason"] = "No handler for Update request"
        return True

    # Handles Delete request, overwrite in inherited class to implement delete actions
    # Return True on success, False if on failure
    def _delete_request(self):
        self.response["Reason"] = "No handler for Delete request"
        return True

    def fn_timeout(self):
        print("Execution is about to time out, sending failure message")
        self.response["Status"] = "FAILED"
        self.response["Reason"] = "Timeout"
        self._send_response()

    # Handles cloudformation request
    def handle_request(self):
        timeleft = (self.context.get_remaining_time_in_millis() / 1000.00) - 0.5 if self.context is not None else 300
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
                raise ValueError("\"{}\" is not a valid request type".format(self.request_type))

            # Set status based on return value of handler
            self.response["Status"] = "SUCCESS" if result else "FAILED"

            # set physical resource id or create new one
            self.response["PhysicalResourceId"] = self.physical_resource_id or self.new_physical_resource_id()

        except Exception as ex:
            self.response["Status"] = "FAILED"
            self.response["Reason"] = str(ex)

        timer.cancel()
        return self._send_response()

    # Send the response to cloudformation
    def _send_response(self):
        # Build the PUT request and the response data
        resp = json.dumps(self.response)

        headers = {
            'content-type': '',
            'content-length': str(len(resp))
        }

        # PUT request to cloudformation
        try:
            response = requests.put(self.response_url, data=json.dumps(self.response), headers=headers)
            response.raise_for_status()
            print("Status code: {}".format(response.status_code))
            print("Status message: {}".format(response.text))
            return True
        except Exception as exc:
            print("Failed executing HTTP request to respond to CloudFormation stack {}".format(self.stack_id))
            print("Error code is {}".format(str(exc)))
            print("Url is {}".format(self.response_url))
            print("Response data is {}".format(resp))
            return False
