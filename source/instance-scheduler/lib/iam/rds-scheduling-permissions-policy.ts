// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Effect, Policy, PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";
import { Fn } from "aws-cdk-lib";

export class RdsSchedulingPermissionsPolicy extends Policy {
  constructor(scope: Construct, id: string) {
    super(scope, id);
    this.addStatements(
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
  }
}
