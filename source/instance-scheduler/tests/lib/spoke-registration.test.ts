// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { RemovalPolicy, Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { AttributeType, BillingMode, Table } from "aws-cdk-lib/aws-dynamodb";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Topic } from "aws-cdk-lib/aws-sns";
import { trueCondition } from "../../lib/cfn";
import { TestFunctionFactory } from "../../lib/lambda-functions/function-factory";
import { SpokeRegistrationLambda } from "../../lib/lambda-functions/spoke-registration";

function mockConfigTable(scope: Stack) {
  return new Table(scope, "ConfigTable", {
    sortKey: { name: "name", type: AttributeType.STRING },
    partitionKey: { name: "type", type: AttributeType.STRING },
    billingMode: BillingMode.PAY_PER_REQUEST,
    removalPolicy: RemovalPolicy.DESTROY,
    pointInTimeRecovery: true,
  });
}

function mockErrorTopic(scope: Stack) {
  return new Topic(scope, "mockedErrorTopic", {});
}

function mockLogGroup(scope: Stack) {
  return new LogGroup(scope, "mockedLogGroup", {});
}
describe("spoke-registration", function () {
  describe("with aws-organizations enabled", function () {
    //setup
    const stack = new Stack();
    const configTable = mockConfigTable(stack);
    const errorTopic = mockErrorTopic(stack);
    const logGroup = mockLogGroup(stack);
    new SpokeRegistrationLambda(stack, {
      solutionVersion: "v9.9.9",
      logRetentionDays: RetentionDays.FIVE_DAYS,
      configTable: configTable,
      snsErrorReportingTopic: errorTopic,
      scheduleLogGroup: logGroup,
      USER_AGENT_EXTRA: "user-agent-extra",
      enableDebugLogging: trueCondition(stack, "EnableDebugLogging"),
      principals: ["o-1234567"],
      namespace: "namespace",
      enableAwsOrganizations: trueCondition(stack, "EnableAwsOrganizations"),
      factory: new TestFunctionFactory(),
    });

    const template = Template.fromStack(stack);

    describe("spoke-registration-lambda", function () {
      const lambdaPermissionResources = template.findResources("AWS::Lambda::Permission");
      expect(lambdaPermissionResources).toContainKey("SpokeRegistrationLambdaCrossAccountPermission");
      const lambdaPermission = lambdaPermissionResources["SpokeRegistrationLambdaCrossAccountPermission"];
      it("is conditional on AwsOrganizations", function () {
        expect(lambdaPermission["Condition"]).toEqual("EnableAwsOrganizations");
      });
    });
  });
});
