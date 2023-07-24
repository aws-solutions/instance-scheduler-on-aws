// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as cdk from "aws-cdk-lib";
import * as rds from "aws-cdk-lib/aws-rds";

import { Construct } from "constructs";
import { TestResourceProvider } from "./index";
import { defaultTestVPC } from "./utils/vpc-utils";
import { NagSuppressions } from "cdk-nag";

const envKeys = {
  rdsInstanceId: "basic_start_stop_rds_instance_id",
};
export const resourceParams = {
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  rdsInstanceId: process.env[envKeys.rdsInstanceId]!,
  taggedScheduleName: "rds_basic_start_stop_test_schedule",
};
export class BasicRdsStartStopTestResources implements TestResourceProvider {
  createTestResources(scope: Construct) {
    const rdsInstance = new rds.DatabaseInstance(scope, "rds-basic-start-stop", {
      engine: rds.DatabaseInstanceEngine.POSTGRES,
      vpc: defaultTestVPC(scope),
    });

    cdk.Tags.of(rdsInstance).add("Schedule", resourceParams.taggedScheduleName);

    const rdsIDOutput = new cdk.CfnOutput(scope, envKeys.rdsInstanceId, {
      value: rdsInstance.instanceIdentifier,
    });

    NagSuppressions.addResourceSuppressions(rdsInstance, [
      {
        id: "AwsSolutions-RDS2",
        reason: "Test instance with no data stored",
      },
      {
        id: "AwsSolutions-RDS3",
        reason: "Test instance that does not need multi-az availability",
      },
      {
        id: "AwsSolutions-RDS10",
        reason: "Test instance that does not need Deletion Protection",
      },
      {
        id: "AwsSolutions-RDS11",
        reason: "Test instance with no need for the extra protection",
      },
      {
        id: "AwsSolutions-SMG4",
        reason: "Short-lived test instance with no need for secrets rotation",
      },
    ]);

    NagSuppressions.addResourceSuppressions(
      rdsInstance,
      [
        {
          id: "AwsSolutions-SMG4",
          reason: "Short-lived test instance with no need for secrets rotation",
        },
      ],
      true,
    );

    return {
      [envKeys.rdsInstanceId]: rdsIDOutput,
    };
  }
}
