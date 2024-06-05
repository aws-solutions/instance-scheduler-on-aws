// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnResource, Stack } from "aws-cdk-lib";
import { Bucket } from "aws-cdk-lib/aws-s3";
import { addCfnNagSuppressions, CfnNagSuppression } from "../../lib/cfn-nag";

describe("add cfn-nag suppression", function () {
  it("adds suppression when none present", function () {
    const stack = new Stack();
    const bucket = new Bucket(stack, "Bucket");
    const suppression: CfnNagSuppression = { id: "my id", reason: "my reason" };
    addCfnNagSuppressions(bucket, suppression);
    expect((bucket.node.defaultChild as CfnResource).cfnOptions.metadata?.cfn_nag?.rules_to_suppress).toStrictEqual(
      expect.arrayContaining([suppression]),
    );
  });

  it("adds suppression when already present", function () {
    const stack = new Stack();
    const bucket = new Bucket(stack, "Bucket");
    const firstSuppression: CfnNagSuppression = { id: "my id", reason: "my reason" };
    const secondSuppression: CfnNagSuppression = { id: "another id", reason: "another reason" };
    const thirdSuppression: CfnNagSuppression = { id: "final id", reason: "final reason" };
    (bucket.node.defaultChild as CfnResource).cfnOptions.metadata = {
      cfn_nag: { rules_to_suppress: [firstSuppression] },
    };
    addCfnNagSuppressions(bucket, secondSuppression, thirdSuppression);
    expect((bucket.node.defaultChild as CfnResource).cfnOptions.metadata?.cfn_nag?.rules_to_suppress).toStrictEqual(
      expect.arrayContaining([firstSuppression, secondSuppression, thirdSuppression]),
    );
  });
});
