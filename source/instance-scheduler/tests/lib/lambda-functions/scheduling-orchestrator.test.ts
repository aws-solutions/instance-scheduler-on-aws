// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { findResource } from "../../test_utils/stack-factories";

describe("scheduling-orchestrator", function () {
  const orchestratorPermissionsPolicy = findResource("AWS::IAM::Policy", "SchedulingOrchestratorPermissionsPolicy");

  test("has SNS publish permissions", function () {
    expect(orchestratorPermissionsPolicy.Properties.PolicyDocument.Statement).toEqual(
      expect.arrayContaining([
        {
          Action: expect.arrayContaining(["kms:Decrypt", "kms:GenerateDataKey*"]),
          Effect: "Allow",
          Resource: { "Fn::GetAtt": ["InstanceSchedulerEncryptionKey", "Arn"] },
        },
        {
          Action: "sns:Publish",
          Effect: "Allow",
          Resource: {
            Ref: "InstanceSchedulerSnsTopic",
          },
        },
      ]),
    );
  });
});
