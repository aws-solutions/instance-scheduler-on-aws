// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { CfnCondition, CfnOutput, CfnParameter, Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { Bucket } from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";
import {
  EnabledDisabledParameter,
  ParameterWithLabel,
  YesNoParameter,
  addParameterGroup,
  addParameterLabel,
  cfnConditionToTrueFalse,
  enabledDisabledCondition,
  overrideLogicalId,
  trueCondition,
  yesNoCondition,
} from "../../lib/cfn";

describe("override logical id", function () {
  it("sets id to expected value", function () {
    const stack = new Stack();
    const bucket = new Bucket(stack, "Bucket");
    const myLogicalId = "MyLogicalId";
    overrideLogicalId(bucket, myLogicalId);
    Template.fromStack(stack).templateMatches({ Resources: { [myLogicalId]: { Type: "AWS::S3::Bucket" } } });
  });

  it("fails on non-CfnResource", function () {
    const stack = new Stack();
    const construct = new Construct(stack, "Construct");
    expect(function () {
      overrideLogicalId(construct, "MyLogicalId");
    }).toThrow();
  });
});

describe("yes/no condition", function () {
  it("resolves to a condition that is true when the value is Yes", function () {
    const stack = new Stack();
    const conditionId = "Condition";
    yesNoCondition(stack, conditionId, "Yes");
    const template = Template.fromStack(stack);
    const conditions = template.findConditions(conditionId);
    const conditionIds = Object.getOwnPropertyNames(conditions);
    expect(conditionIds).toHaveLength(1);
    const condition = conditions[conditionIds[0]];
    expect(condition).toEqual({ "Fn::Equals": ["Yes", "Yes"] });
  });
});

describe("enabled/disabled condition", function () {
  it("resolves to a condition that is true when the value is Enabled", function () {
    const stack = new Stack();
    const conditionId = "Condition";
    enabledDisabledCondition(stack, conditionId, "Enabled");
    const template = Template.fromStack(stack);
    const conditions = template.findConditions(conditionId);
    const conditionIds = Object.getOwnPropertyNames(conditions);
    expect(conditionIds).toHaveLength(1);
    const condition = conditions[conditionIds[0]];
    expect(condition).toEqual({ "Fn::Equals": ["Enabled", "Enabled"] });
  });
});

describe("true condition", function () {
  it("resolves to a true condition", function () {
    const stack = new Stack();
    const conditionId = "Condition";
    trueCondition(stack, conditionId);
    const template = Template.fromStack(stack);
    const conditions = template.findConditions(conditionId);
    const conditionIds = Object.getOwnPropertyNames(conditions);
    expect(conditionIds).toHaveLength(1);
    const condition = conditions[conditionIds[0]];
    expect(condition).toEqual({ "Fn::Equals": [true, true] });
  });
});

describe("condition to true/false", function () {
  it("resolves to True or False depending on condition", function () {
    const stack = new Stack();
    const conditionId = "Condition";
    const condition = new CfnCondition(stack, conditionId);
    const outputId = "Output";
    new CfnOutput(stack, outputId, { value: cfnConditionToTrueFalse(condition) });
    const template = Template.fromStack(stack);
    const outputs = template.findOutputs(outputId);
    const outputIds = Object.getOwnPropertyNames(outputs);
    expect(outputIds).toHaveLength(1);
    const output = outputs[outputIds[0]];
    expect(output.Value).toEqual({ "Fn::If": [conditionId, "True", "False"] });
  });
});

describe("parameter label helpers", function () {
  it("add expected labels and groups", function () {
    const stack = new Stack();
    const firstParamId = "FirstParam";
    const firstParam = new CfnParameter(stack, firstParamId);
    const secondParamId = "SecondParam";
    const secondParam = new CfnParameter(stack, secondParamId);

    const firstParamLabel = "my-first-param";
    addParameterLabel(firstParam, firstParamLabel);
    const secondParamLabel = "my-second-param";
    addParameterLabel(secondParam, secondParamLabel);

    const groupLabel = "my-group";
    addParameterGroup(stack, { label: groupLabel, parameters: [firstParam, secondParam] });

    const cfnInterface = Template.fromStack(stack).toJSON().Metadata["AWS::CloudFormation::Interface"];
    expect(cfnInterface.ParameterGroups).toEqual([
      { Label: { default: groupLabel }, Parameters: expect.arrayContaining([firstParamId, secondParamId]) },
    ]);
    expect(cfnInterface.ParameterLabels[firstParamId]).toEqual({ default: firstParamLabel });
    expect(cfnInterface.ParameterLabels[secondParamId]).toEqual({ default: secondParamLabel });
  });
});

describe("parameter with label", function () {
  it("adds expected label", function () {
    const stack = new Stack();
    const paramId = "MyParam";
    const label = "my-param";
    new ParameterWithLabel(stack, paramId, { label });

    const cfnInterface = Template.fromStack(stack).toJSON().Metadata["AWS::CloudFormation::Interface"];
    expect(cfnInterface.ParameterLabels[paramId]).toEqual({ default: label });
  });
});

describe("yes/no parameter", function () {
  it("does not add condition if not used", function () {
    const stack = new Stack();
    const paramId = "MyParam";
    new YesNoParameter(stack, paramId);
    const template = Template.fromStack(stack);
    const conditions = template.findConditions("*");
    const conditionIds = Object.getOwnPropertyNames(conditions);
    expect(conditionIds).toHaveLength(0);
  });

  it("adds condition", function () {
    const stack = new Stack();
    const paramId = "MyParam";
    const param = new YesNoParameter(stack, paramId);
    param.getCondition();
    const template = Template.fromStack(stack);
    const conditions = template.findConditions("*");
    const conditionIds = Object.getOwnPropertyNames(conditions);
    expect(conditionIds).toHaveLength(1);
    expect(conditionIds[0]).toStrictEqual(`${paramId}Condition`);
    const condition = conditions[conditionIds[0]];
    expect(condition).toEqual({ "Fn::Equals": [{ Ref: paramId }, "Yes"] });
  });
});

describe("enabled/disabled parameter", function () {
  it("does not add condition if not used", function () {
    const stack = new Stack();
    const paramId = "MyParam";
    new EnabledDisabledParameter(stack, paramId);
    const template = Template.fromStack(stack);
    const conditions = template.findConditions("*");
    const conditionIds = Object.getOwnPropertyNames(conditions);
    expect(conditionIds).toHaveLength(0);
  });

  it("adds condition", function () {
    const stack = new Stack();
    const paramId = "MyParam";
    const param = new EnabledDisabledParameter(stack, paramId);
    param.getCondition();
    const template = Template.fromStack(stack);
    const conditions = template.findConditions("*");
    const conditionIds = Object.getOwnPropertyNames(conditions);
    expect(conditionIds).toHaveLength(1);
    expect(conditionIds[0]).toStrictEqual(`${paramId}Condition`);
    const condition = conditions[conditionIds[0]];
    expect(condition).toEqual({ "Fn::Equals": [{ Ref: paramId }, "Enabled"] });
  });
});
