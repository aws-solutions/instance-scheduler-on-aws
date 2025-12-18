# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from functools import cached_property


class ARN(str):

    @cached_property
    def arn_parts(self) -> list[str]:
        parts = self.split(":")
        if len(parts) < 6 or parts[0] != "arn":
            raise ValueError(f"Invalid ARN format: {self}")
        # Rejoin resource part if it contains additional colons
        if len(parts) > 6:
            resource = ":".join(parts[5:])
            parts = parts[:5] + [resource]
        return parts

    @property
    def aws_partition(self) -> str:
        return self.arn_parts[1]

    @property
    def service(self) -> str:
        return self.arn_parts[2]

    @property
    def region(self) -> str:
        return self.arn_parts[3]

    @property
    def account(self) -> str:
        return self.arn_parts[4]

    @property
    def resource(self) -> str:
        return self.arn_parts[5]

    @property
    def resource_type(self) -> str:
        """Extract resource type from resource part (e.g., 'instance' from 'instance/i-123')"""
        if "/" in self.resource:
            # second split necessary for ASGs: autoScalingGroup:uuid:autoScalingGroupName/name -> autoScalingGroup
            return self.resource.split("/")[0].split(":")[0]
        elif ":" in self.resource:
            return self.resource.split(":")[0]
        return ""

    @property
    def resource_id(self) -> str:
        """Extract resource ID from resource part (e.g., 'i-123' from 'instance/i-123')"""
        if "/" in self.resource:
            return self.resource.split("/", 1)[1]
        elif ":" in self.resource:
            return self.resource.split(":", 1)[1]
        return self.resource
