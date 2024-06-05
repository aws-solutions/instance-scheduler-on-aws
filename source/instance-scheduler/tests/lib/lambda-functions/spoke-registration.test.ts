// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { findResource } from "../../test_utils/stack-factories";

describe("spoke-registration-handler", function () {
  const spokeRegistrationPolicy = findResource("AWS::IAM::Policy", "SpokeRegistrationPolicy");

  test("has SNS publish permissions", function () {
    expect(spokeRegistrationPolicy.Properties.PolicyDocument.Statement).toEqual(
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
