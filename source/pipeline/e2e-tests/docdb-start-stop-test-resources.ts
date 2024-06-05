// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as docdb from "aws-cdk-lib/aws-docdb";
import * as ec2 from "aws-cdk-lib/aws-ec2";

import { TestResourceProvider } from "./index";
import { Construct } from "constructs";
import { defaultTestVPC } from "./utils/vpc-utils";
import { CfnOutput, RemovalPolicy, SecretValue, Tags } from "aws-cdk-lib";
import { NagSuppressions } from "cdk-nag";

const envKeys = {
  docdbInstanceId: "DocdbStartStopInstance",
};
export const resourceParams = {
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  docdbInstanceId: process.env[envKeys.docdbInstanceId]!,
  startStopTestScheduleName: "docdb_start_stop_test_schedule",
};

export class DocdbStartStopTestResources implements TestResourceProvider {
  createTestResources(scope: Construct): Record<string, CfnOutput> {
    const docdbCluster = new docdb.DatabaseCluster(scope, "docdbStartStopTestCluster", {
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.R6G, ec2.InstanceSize.LARGE), //smallest supported size
      vpc: defaultTestVPC(scope),
      masterUser: {
        username: "username",
        password: SecretValue.unsafePlainText("password"),
      },
      removalPolicy: RemovalPolicy.DESTROY,
    });

    Tags.of(docdbCluster).add("Schedule", resourceParams.startStopTestScheduleName);

    const docdbInstanceIdOut = new CfnOutput(scope, envKeys.docdbInstanceId, {
      value: docdbCluster.clusterIdentifier,
    });

    NagSuppressions.addResourceSuppressions(docdbCluster, [
      {
        id: "AwsSolutions-DOC2",
        reason: "This is an automated test instance that will be only started and then stopped again",
      },
      {
        id: "AwsSolutions-DOC3",
        reason: "This is an automated test instance that will be only started and then stopped again",
      },
      {
        id: "AwsSolutions-DOC4",
        reason: "This is an automated test instance that will be only started and then stopped again",
      },
      {
        id: "AwsSolutions-DOC5",
        reason: "This is an automated test instance that will be only started and then stopped again",
      },
    ]);

    return {
      [envKeys.docdbInstanceId]: docdbInstanceIdOut,
    };
  }
}
