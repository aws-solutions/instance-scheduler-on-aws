// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnOutput } from "aws-cdk-lib";
import { AutoScalingGroup } from "aws-cdk-lib/aws-autoscaling";
import {
  AmazonLinuxCpuType,
  InstanceClass,
  InstanceSize,
  InstanceType,
  LaunchTemplate,
  MachineImage,
} from "aws-cdk-lib/aws-ec2";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { TestResourceProvider } from ".";
import { defaultTestVPC } from "./utils/vpc-utils";

const envKeys = {
  configureGroup: "ConfigureGroupName",
};

export const resourceParams = {
  configureGroupName: process.env[envKeys.configureGroup],
  scheduleName: "asg-schedule",
};

export class AsgConfigureTestResources implements TestResourceProvider {
  createTestResources(scope: Construct): Record<string, CfnOutput> {
    const launchTemplate = new LaunchTemplate(scope, "ConfigureTemplate", {
      instanceType: InstanceType.of(InstanceClass.T4G, InstanceSize.NANO),
      machineImage: MachineImage.latestAmazonLinux2023({ cpuType: AmazonLinuxCpuType.ARM_64 }),
    });
    const testGroup = new AutoScalingGroup(scope, "ConfigureGroup", {
      vpc: defaultTestVPC(scope),
      launchTemplate,
    });

    NagSuppressions.addResourceSuppressions(testGroup, [
      {
        id: "AwsSolutions-EC26",
        reason: "This is an automated test group without any need for encrypted EBS volumes",
      },
      {
        id: "AwsSolutions-AS3",
        reason: "This is an automated test group without any need for notifications",
      },
    ]);

    const testGroupOutput = new CfnOutput(scope, envKeys.configureGroup, {
      value: testGroup.autoScalingGroupName,
    });

    return { [envKeys.configureGroup]: testGroupOutput };
  }
}
