// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { conditions, findResourceWithPartialId, mockCoreScheduler } from "../test_utils/stack-factories";

describe("OpsInsights dashboard", function () {
  const coreScheduler = mockCoreScheduler();
  const opsInsightsDashboard = findResourceWithPartialId(
    coreScheduler,
    "AWS::CloudWatch::Dashboard",
    "OperationalInsightsDashboard",
  );

  test("is conditional on being enabled", function () {
    expect(opsInsightsDashboard).toHaveProperty("Condition", conditions.deployOpsInsightsDashboard);
  });
});
