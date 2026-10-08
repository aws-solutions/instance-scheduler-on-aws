// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { findResourceWithPartialId, mockCoreScheduler } from "../../test_utils/stack-factories";

// Single template synthesis shared across all tests to avoid SequencingGates static map conflicts
const template = mockCoreScheduler();

/**
 * Bug Condition Exploration Test
 *
 * Validates: Requirements 1.1, 2.1, 2.2
 *
 * This test synthesizes the CloudFormation template and asserts that the
 * CreateRegionalEventRulesLambda function has a DependsOn relationship
 * to CreateRegionalEventRulesPolicy.
 *
 * On UNFIXED code, this test is EXPECTED TO FAIL — proving the race condition bug exists.
 */
describe("RegionEventRulesCustomResource - Lambda DependsOn Policy", () => {
  test("CreateRegionalEventRulesLambda DependsOn includes CreateRegionalEventRulesPolicy", () => {
    // Find the Lambda function resource
    const lambdaResource = findResourceWithPartialId(
      template,
      "AWS::Lambda::Function",
      "CreateRegionalEventRulesLambda",
    );

    // Find the policy logical ID
    const allPolicies = template.findResources("AWS::IAM::Policy");
    const policyLogicalId = Object.keys(allPolicies).find((id) =>
      id.includes("CreateRegionalEventRulesPolicy"),
    );

    expect(policyLogicalId).toBeDefined();

    // Assert the Lambda's DependsOn array includes the policy's logical ID
    // On unfixed code, DependsOn will either be undefined or not contain the policy
    const dependsOn: string[] = lambdaResource.DependsOn ?? [];
    expect(dependsOn).toContain(policyLogicalId);
  });
});

/**
 * Preservation Property Tests
 *
 * Validates: Requirements 3.1, 3.2, 3.3
 *
 * These tests capture baseline behavior on UNFIXED code.
 * They must PASS on unfixed code to establish a preservation baseline.
 * After the fix is applied, they must continue to PASS (no regressions).
 */
describe("RegionEventRulesCustomResource - Preservation", () => {
  /**
   * **Validates: Requirements 3.1**
   *
   * Property 2: Preservation - SequencingGates on RegisterRegions custom resource
   *
   * The RegisterRegions custom resource (Custom::RegisterRegion) must depend on
   * all four SequencingGates: IamRoleDeploymentGate, LambdaDeploymentGate,
   * IamPolicyDeploymentGate, and DynamoDbTableDeploymentGate.
   */
  test("RegisterRegions custom resource DependsOn includes all SequencingGates", () => {
    const registerRegionsResource = findResourceWithPartialId(
      template,
      "Custom::RegisterRegion",
      "RegisterRegions",
    );

    const dependsOn: string[] = registerRegionsResource.DependsOn ?? [];

    const expectedGatePartialIds = [
      "IamRoleDeploymentGate",
      "LambdaDeploymentGate",
      "IamPolicyDeploymentGate",
      "DynamoDbTableDeploymentGate",
    ];

    for (const gatePartialId of expectedGatePartialIds) {
      const matchingDep = dependsOn.find((dep) => dep.includes(gatePartialId));
      expect(matchingDep).toBeDefined();
    }
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * Property 2: Preservation - Template validity
   *
   * Template synthesis completes without errors (no circular dependencies).
   * The fact that mockCoreScheduler() returns a Template without throwing
   * confirms the template is valid.
   */
  test("template synthesis completes without errors", () => {
    // mockCoreScheduler() would throw if synthesis failed (e.g., circular dependencies)
    // Verify the template has resources as a basic validity check
    const templateJson = template.toJSON();
    expect(templateJson).toHaveProperty("Resources");
    expect(Object.keys(templateJson.Resources).length).toBeGreaterThan(0);
  });

  /**
   * **Validates: Requirements 3.1, 3.2, 3.3**
   *
   * Property 2: Preservation - Other resources' DependsOn arrays unchanged
   *
   * Captures a baseline snapshot of DependsOn arrays for all resources
   * EXCEPT CreateRegionalEventRulesLambda (which is the fix target).
   * After the fix, only the Lambda's DependsOn should change.
   */
  test("other resources DependsOn arrays match baseline snapshot", () => {
    const templateJson = template.toJSON();
    const resources = templateJson.Resources;

    // Find the Lambda logical ID to exclude it
    const lambdaLogicalId = Object.keys(
      template.findResources("AWS::Lambda::Function"),
    ).find((id) => id.includes("CreateRegionalEventRulesLambda"));

    // Build a map of logicalId -> DependsOn for all resources except the target Lambda
    const dependsOnBaseline: Record<string, string[] | undefined> = {};
    for (const [logicalId, resource] of Object.entries(resources)) {
      if (logicalId === lambdaLogicalId) continue;
      dependsOnBaseline[logicalId] = (resource as Record<string, unknown>).DependsOn as string[] | undefined;
    }

    expect(dependsOnBaseline).toMatchSnapshot();
  });
});