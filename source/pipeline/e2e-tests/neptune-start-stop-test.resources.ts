// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as neptune from "@aws-cdk/aws-neptune-alpha";
import * as cdk from "aws-cdk-lib";
import { CfnOutput, RemovalPolicy } from "aws-cdk-lib";

import { TestResourceProvider } from "./index";
import { Construct } from "constructs";
import { defaultTestVPC } from "./utils/vpc-utils";
import { NagSuppressions } from "cdk-nag";

const envKeys = {
  neptuneInstanceId: "NeptuneStartStopInstanceId",
};
export const resourceParams = {
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  neptuneInstanceId: process.env[envKeys.neptuneInstanceId]!,
  startStopTestScheduleName: "neptune_start_stop_test_schedule",
};
export class NeptuneStartStopTestResources implements TestResourceProvider {
  createTestResources(scope: Construct): Record<string, CfnOutput> {
    const neptuneCluster = new neptune.DatabaseCluster(scope, "NeptuneStartStopTestCluster", {
      instanceType: neptune.InstanceType.T3_MEDIUM,
      vpc: defaultTestVPC(scope),
      removalPolicy: RemovalPolicy.DESTROY,
    });

    cdk.Tags.of(neptuneCluster).add("Schedule", resourceParams.startStopTestScheduleName);

    const neptuneInstanceIdOut = new cdk.CfnOutput(scope, envKeys.neptuneInstanceId, {
      value: neptuneCluster.clusterIdentifier,
    });

    NagSuppressions.addResourceSuppressions(
      neptuneCluster,
      [
        {
          id: "AwsSolutions-N2",
          reason: "This is an automated test instance that will be only started and then stopped again",
        },
        {
          id: "AwsSolutions-N3",
          reason: "This is an automated test instance that will be only started and then stopped again",
        },
        {
          id: "AwsSolutions-N5",
          reason: "This is an automated test instance that will be only started and then stopped again",
        },
      ],
      true,
    );

    return {
      [envKeys.neptuneInstanceId]: neptuneInstanceIdOut,
    };
  }
}
