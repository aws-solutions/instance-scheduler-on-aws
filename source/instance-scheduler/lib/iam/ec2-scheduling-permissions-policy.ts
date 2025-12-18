// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Effect, Policy, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { Fn } from "aws-cdk-lib";

export class Ec2SchedulingPermissionsPolicy extends Policy {
  constructor(scope: Construct, id: string) {
    super(scope, id);
    // describe ec2 instances for scheduling (cannot be scoped to tagged instances)
    this.addStatements(
      new PolicyStatement({
        actions: ["ec2:DescribeInstances"],
        effect: Effect.ALLOW,
        resources: ["*"],
      }),

      // start/stop/resize permissions scoped to tagged EC2 instances only
      new PolicyStatement({
        actions: [
          "ec2:StartInstances",
          "ec2:StopInstances",
          "ec2:CreateTags",
          "ec2:DeleteTags",
          "ec2:ModifyInstanceAttribute",
        ],
        effect: Effect.ALLOW,
        resources: [Fn.sub("arn:${AWS::Partition}:ec2:*:${AWS::AccountId}:instance/*")],
      }),

      // describe ec2 maintenance windows
      new PolicyStatement({
        actions: ["ssm:DescribeMaintenanceWindows"],
        effect: Effect.ALLOW,
        resources: ["*"],
      }),
    );
  }
}
