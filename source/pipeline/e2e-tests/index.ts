// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Construct } from "constructs";
import { EC2StartStopTestResources } from "./basic-ec2-start-stop.test.resources";
import { CfnOutput } from "aws-cdk-lib";
import { BasicRdsStartStopTestResources } from "./basic-rds-start-stop.test.resources";
import { EC2MaintenanceWindowStartTestResource } from "./ec2-maintenance-window.test.resources";

export interface TestResourceProvider {
  createTestResources(scope: Construct): Record<string, CfnOutput>;
}

export const testResourceProviders: TestResourceProvider[] = [
  new EC2StartStopTestResources(),
  new BasicRdsStartStopTestResources(),
  new EC2MaintenanceWindowStartTestResource(),
];

export const delaySeconds = (seconds: number) => new Promise((res) => setTimeout(res, seconds * 1000));
export const delayMinutes = (minutes: number) => new Promise((res) => setTimeout(res, minutes * 60000));
