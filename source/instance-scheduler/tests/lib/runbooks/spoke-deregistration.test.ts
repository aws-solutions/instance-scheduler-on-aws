// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { findResource } from "../../test_utils/stack-factories";

describe("SpokeDeregistrationRunbook", () => {
  it("", () => {
    const runbookPolicy = findResource("AWS::IAM::Policy", "SpokeDeregistrationRunbookRoleDefaultPolicy");
    expect(runbookPolicy.Properties.PolicyDocument.Statement).toEqual(
      expect.arrayContaining([
        {
          Action: "lambda:InvokeFunction",
          Effect: "Allow",
          Resource: [
            {
              "Fn::GetAtt": [expect.stringContaining("SpokeRegistrationHandler"), "Arn"],
            },
            {
              "Fn::Join": [
                "",
                [
                  {
                    "Fn::GetAtt": [expect.stringContaining("SpokeRegistrationHandler"), "Arn"],
                  },
                  ":*",
                ],
              ],
            },
          ],
        },
      ]),
    );
  });
});
