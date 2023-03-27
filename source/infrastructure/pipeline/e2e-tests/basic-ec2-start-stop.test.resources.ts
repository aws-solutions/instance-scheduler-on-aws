// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as cdk from "aws-cdk-lib";

import { Construct } from "constructs";
import { NagSuppressions } from "cdk-nag";
import { TestResourceProvider } from "./index";

const envKeys = {
  ec2InstanceId: "basic_start_stop_instance_id",
};
export const resourceParams = {
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  ec2InstanceId: process.env[envKeys.ec2InstanceId]!,
  startStopTestScheduleName: "ec2_basic_start_stop_test_schedule",
};
export class EC2StartStopTestResources implements TestResourceProvider {
  createTestResources(scope: Construct) {
    const vpc = new ec2.Vpc(scope, "basic-start-stop-vpc", {
      natGateways: 0,
      ipAddresses: ec2.IpAddresses.cidr("10.0.0.0/16"),
    });

    const testInstance = new ec2.Instance(scope, "basic-start-stop-instance", {
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T2, ec2.InstanceSize.MICRO),
      machineImage: ec2.MachineImage.latestAmazonLinux(),
      vpc: vpc,
    });

    cdk.Tags.of(testInstance).add("Schedule", resourceParams.startStopTestScheduleName);

    const startStopOut = new cdk.CfnOutput(scope, envKeys.ec2InstanceId, {
      value: testInstance.instanceId,
    });

    NagSuppressions.addResourceSuppressions(testInstance, [
      {
        id: "AwsSolutions-EC28",
        reason: "This is a test instance that only ever needs to be started/stopped (work workloads)",
      },
      {
        id: "AwsSolutions-EC29",
        reason: "This is an automated test instance without any need for termination protection",
      },
    ]);

    NagSuppressions.addResourceSuppressions(vpc, [
      {
        id: "AwsSolutions-VPC7",
        reason: "The VPC  is for a test instance that only ever needs to be started/stopped (no traffic)",
      },
    ]);

    return {
      [envKeys.ec2InstanceId]: startStopOut,
    };
  }
}
