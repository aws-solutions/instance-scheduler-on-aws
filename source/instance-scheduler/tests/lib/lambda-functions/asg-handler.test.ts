// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { findResource } from "../../test_utils/stack-factories";

describe("asg-handler", function () {
  const asgPermissionsPolicy = findResource("AWS::IAM::Policy", "ASGPolicy");

  test("has SNS publish permissions", function () {
    expect(asgPermissionsPolicy.Properties.PolicyDocument.Statement).toEqual(
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
