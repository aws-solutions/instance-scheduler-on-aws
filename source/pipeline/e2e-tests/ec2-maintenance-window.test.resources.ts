// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as cdk from "aws-cdk-lib";

import { Construct } from "constructs";
import { NagSuppressions } from "cdk-nag";
import { TestResourceProvider } from "./index";
import { defaultTestVPC } from "./utils/vpc-utils";

const envKeys = {
  ec2InstanceId: "ec2_maintenance_window_start_instance_id",
};
export const resourceParams = {
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  ec2InstanceId: process.env[envKeys.ec2InstanceId]!,
  maintWindowTestScheduleName: "ec2_maintenance_window_test_schedule",
};
export class EC2MaintenanceWindowStartTestResource implements TestResourceProvider {
  createTestResources(scope: Construct) {
    const testInstance = new ec2.Instance(scope, "maint_window_start_instance", {
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T2, ec2.InstanceSize.MICRO),
      machineImage: ec2.MachineImage.latestAmazonLinux2(),
      vpc: defaultTestVPC(scope),
    });

    cdk.Tags.of(testInstance).add("Schedule", resourceParams.maintWindowTestScheduleName);

    const startStopOut = new cdk.CfnOutput(scope, envKeys.ec2InstanceId, {
      value: testInstance.instanceId,
    });

    NagSuppressions.addResourceSuppressions(testInstance, [
      {
        id: "AwsSolutions-EC26",
        reason: "This is an automated test instance without any need for encrypted EBS volumes",
      },
      {
        id: "AwsSolutions-EC28",
        reason: "This is a test instance that only ever needs to be started/stopped (work workloads)",
      },
      {
        id: "AwsSolutions-EC29",
        reason: "This is an automated test instance without any need for termination protection",
      },
    ]);

    return {
      [envKeys.ec2InstanceId]: startStopOut,
    };
  }
}
