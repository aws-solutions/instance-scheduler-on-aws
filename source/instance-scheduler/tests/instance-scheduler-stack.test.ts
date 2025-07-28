// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Template } from "aws-cdk-lib/assertions";
import { createHubStack } from "./instance-scheduler-stack-factory";

// share Templates for testing to avoid redundant Docker builds
const hubStack = Template.fromStack(createHubStack());

test("InstanceSchedulerStack snapshot test", () => {
  const resources = hubStack.findResources("AWS::Lambda::Function");
  const hubStackJson = hubStack.toJSON();

  for (const lambda_function in resources) {
    hubStackJson["Resources"][lambda_function]["Properties"]["Code"] =
      "Omitted to remove snapshot dependency on code hash";
  }
  expect(hubStackJson).toMatchSnapshot();
});

test("Hub stack has expected defaults for started and stopped tags", () => {
  expect(hubStack.findParameters("StartedTags")["StartedTags"]["Default"]).toBe(
    "InstanceScheduler-LastAction=Started By {scheduler} {year}-{month}-{day} {hour}:{minute} {timezone}",
  );
  expect(hubStack.findParameters("StoppedTags")["StoppedTags"]["Default"]).toBe(
    "InstanceScheduler-LastAction=Stopped By {scheduler} {year}-{month}-{day} {hour}:{minute} {timezone}",
  );
});

type CfnParameterGroup = { Label: { default: string }; Parameters: string[] };

describe("hub template", function () {
  const hubTemplateJson = hubStack.toJSON();

  describe("parameters", function () {
    const parameters = hubStack.findParameters("*");
    const cfnInterface = hubTemplateJson.Metadata["AWS::CloudFormation::Interface"];

    expect(Object.getOwnPropertyNames(parameters).length).toBeGreaterThan(0);

    Object.getOwnPropertyNames(parameters).forEach((parameterName: string) => {
      if (parameterName === "BootstrapVersion") {
        // skip automatically-generated parameter, it will not be present in the prod template
        return;
      }

      describe(parameterName, function () {
        it("has a label", function () {
          const label = cfnInterface.ParameterLabels[parameterName].default;
          expect(typeof label).toStrictEqual("string");
          expect(label.length).toBeGreaterThan(0);
        });

        it("belongs to a group", function () {
          expect(Array.isArray(cfnInterface.ParameterGroups)).toStrictEqual(true);
          expect(
            cfnInterface.ParameterGroups.some((group: CfnParameterGroup) => {
              return (
                Array.isArray(group.Parameters) &&
                group.Parameters.includes(parameterName) &&
                typeof group.Label.default === "string" &&
                group.Label.default.length > 0
              );
            }),
          ).toStrictEqual(true);
        });
      });
    });
  });
});
