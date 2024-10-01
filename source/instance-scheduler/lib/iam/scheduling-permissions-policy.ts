// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Effect, Policy, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { Fn } from "aws-cdk-lib";
import { NagSuppressions } from "cdk-nag";
import { addCfnNagSuppressions } from "../cfn-nag";

export class SchedulingPermissionsPolicy extends Policy {
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

      // describe rds instances and clusters
      new PolicyStatement({
        actions: ["rds:DescribeDBClusters", "rds:DescribeDBInstances", "tag:GetResources"],
        effect: Effect.ALLOW,
        resources: ["*"],
      }),

      new PolicyStatement({
        //StopDBInstance here is required
        actions: [
          "rds:DeleteDBSnapshot",
          "rds:DescribeDBSnapshots",
          "rds:StopDBInstance",
          "rds:CreateDBSnapshot",
          "rds:AddTagsToResource",
        ],
        effect: Effect.ALLOW,
        resources: [Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:snapshot:*")],
      }),

      // start/stop/tag for rds instances
      new PolicyStatement({
        actions: [
          "rds:AddTagsToResource",
          "rds:RemoveTagsFromResource",
          "rds:StartDBInstance",
          "rds:StopDBInstance",
          "rds:CreateDBSnapshot",
        ],
        effect: Effect.ALLOW,
        resources: [Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:db:*")],
      }),

      // start/stop/tag for rds clusters
      new PolicyStatement({
        actions: [
          "rds:AddTagsToResource",
          "rds:RemoveTagsFromResource",
          "rds:StartDBCluster",
          "rds:StopDBCluster",
          "rds:CreateDBClusterSnapshot",
        ],
        effect: Effect.ALLOW,
        resources: [Fn.sub("arn:${AWS::Partition}:rds:*:${AWS::AccountId}:cluster:*")],
      }),
    );

    addCfnNagSuppressions(this, { id: "W12", reason: "required scheduling permissions" });

    NagSuppressions.addResourceSuppressions(this, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: [
          "Resource::arn:<AWS::Partition>:rds:*:<AWS::AccountId>:db:*",
          "Resource::arn:<AWS::Partition>:rds:*:<AWS::AccountId>:cluster:*",
          "Resource::arn:<AWS::Partition>:ec2:*:<AWS::AccountId>:instance/*",
          "Resource::arn:<AWS::Partition>:rds:*:<AWS::AccountId>:snapshot:*",
          "Resource::*",
        ],
        reason: "required scheduling permissions",
      },
    ]);
  }
}
