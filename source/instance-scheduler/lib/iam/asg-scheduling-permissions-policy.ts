// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws } from "aws-cdk-lib";
import { Policy, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { NagSuppressions } from "cdk-nag";
import { addCfnNagSuppressions } from "../cfn-nag";
import { Construct } from "constructs";

export class AsgSchedulingPermissionsPolicy extends Policy {
  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.addStatements(
      new PolicyStatement({
        actions: [
          "autoscaling:BatchPutScheduledUpdateGroupAction",
          "autoscaling:BatchDeleteScheduledAction",
          "autoscaling:CreateOrUpdateTags",
        ],
        resources: [`arn:${Aws.PARTITION}:autoscaling:*:${Aws.ACCOUNT_ID}:autoScalingGroup:*:autoScalingGroupName/*`],
      }),
      new PolicyStatement({
        actions: ["autoscaling:DescribeAutoScalingGroups", "autoscaling:DescribeScheduledActions"],
        resources: ["*"],
      }),
    );

    addCfnNagSuppressions(this, {
      id: "W12",
      reason: "DescribeAutoScalingGroups and autoscaling:DescribeScheduledActions actions require wildcard permissions",
    });

    NagSuppressions.addResourceSuppressions(this, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::*"],
        reason: "Required permissions to describe AutoScaling Groups",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: [
          "Resource::arn:<AWS::Partition>:autoscaling:*:<AWS::AccountId>:autoScalingGroup:*:autoScalingGroupName/*",
        ],
        reason: "Required permissions to modify scheduled scaling actions on AutoScaling Groups",
      },
    ]);
  }
}
