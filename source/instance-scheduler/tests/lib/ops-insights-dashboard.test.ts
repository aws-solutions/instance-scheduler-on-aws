// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { conditions, findResource } from "../test_utils/stack-factories";

describe("OpsInsights dashboard", function () {
  const opsInsightsDashboard = findResource("AWS::CloudWatch::Dashboard", "OperationalInsightsDashboard");

  test("is conditional on being enabled", function () {
    expect(opsInsightsDashboard).toHaveProperty("Condition", conditions.deployOpsInsightsDashboard);
  });
});
