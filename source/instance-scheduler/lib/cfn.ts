// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CfnCondition, CfnParameter, CfnParameterProps, CfnResource, Fn, IAspect, Stack } from "aws-cdk-lib";
import { Construct, IConstruct } from "constructs";

export const UniqueStackIdPart = Fn.select(2, Fn.split("/", `${Aws.STACK_ID}`));

export function overrideLogicalId(construct: IConstruct, logicalId: string) {
  const cfnResource = construct.node.defaultChild as CfnResource;
  if (!cfnResource) {
    throw new Error("Unable to override logical ID, not a CfnResource");
  }

  cfnResource.overrideLogicalId(logicalId);
}

export function overrideRetentionPolicies(construct: IConstruct, value: unknown) {
  const cfnResource = construct.node.defaultChild as CfnResource;
  if (!cfnResource) {
    throw new Error("Unable to override retention policies, not a CfnResource");
  }
  cfnResource.addOverride("DeletionPolicy", value);
  cfnResource.addOverride("UpdateReplacePolicy", value);
}

export function overrideProperty(construct: IConstruct, propertyPath: string, value: unknown) {
  const cfnResource = construct.node.defaultChild as CfnResource;
  if (!cfnResource) {
    throw new Error("Unable to override property, not a CfnResource");
  }

  cfnResource.addPropertyOverride(propertyPath, value);
}

export const YesNoType = {
  Yes: "Yes",
  No: "No",
} as const;

export const yesNoValues: (keyof typeof YesNoType)[] = [YesNoType.Yes, YesNoType.No];

export function yesNoCondition(scope: Construct, id: string, value: string): CfnCondition {
  return new CfnCondition(scope, id, { expression: Fn.conditionEquals(value, YesNoType.Yes) });
}

export const EnabledDisabledType = {
  Enabled: "Enabled",
  Disabled: "Disabled",
} as const;

export const enabledDisabledValues: (keyof typeof EnabledDisabledType)[] = [
  EnabledDisabledType.Enabled,
  EnabledDisabledType.Disabled,
];

export function enabledDisabledCondition(scope: Construct, id: string, value: string): CfnCondition {
  return new CfnCondition(scope, id, { expression: Fn.conditionEquals(value, EnabledDisabledType.Enabled) });
}

export function trueCondition(scope: Construct, id: string): CfnCondition {
  return new CfnCondition(scope, id, { expression: Fn.conditionEquals(true, true) });
}

export function cfnConditionToTrueFalse(condition: CfnCondition): string {
  return Fn.conditionIf(condition.logicalId, "True", "False").toString();
}

const cfnInterfaceKey = "AWS::CloudFormation::Interface";
const parameterGroupsKey = "ParameterGroups";
const parameterLabelsKey = "ParameterLabels";

function initCfnInterface(scope: Construct): void {
  const stack = Stack.of(scope);
  if (!stack.templateOptions.metadata) {
    stack.templateOptions.metadata = {};
  }
  const metadata = stack.templateOptions.metadata;
  if (!(cfnInterfaceKey in metadata)) {
    metadata[cfnInterfaceKey] = {};
  }
  const cfnInterface = metadata[cfnInterfaceKey];
  if (!(parameterLabelsKey in cfnInterface)) {
    cfnInterface[parameterLabelsKey] = {};
  }
  if (!(parameterGroupsKey in cfnInterface)) {
    cfnInterface[parameterGroupsKey] = [];
  }
}

export function addParameterLabel(parameter: CfnParameter, label: string): void {
  const stack = Stack.of(parameter);
  initCfnInterface(stack);
  stack.templateOptions.metadata![cfnInterfaceKey][parameterLabelsKey][parameter.logicalId] = { default: label };
}

export interface ParameterGroup {
  readonly label: string;
  readonly parameters: CfnParameter[];
}

export function addParameterGroup(scope: Construct, group: ParameterGroup): void {
  initCfnInterface(scope);
  const stack = Stack.of(scope);
  stack.templateOptions.metadata![cfnInterfaceKey][parameterGroupsKey].push({
    Label: { default: group.label },
    Parameters: group.parameters.map((parameter: CfnParameter) => parameter.logicalId),
  });
}

export class ConditionAspect<T extends new (...args: never[]) => CfnResource> implements IAspect {
  constructor(
    private condition: CfnCondition,
    private resourceType?: T,
  ) {}

  visit(node: IConstruct): void {
    if (node instanceof (this.resourceType ?? CfnResource)) {
      node.cfnOptions.condition = this.condition;
    }
  }
}

export interface ParameterWithLabelProps extends CfnParameterProps {
  label?: string;
}

export class ParameterWithLabel extends CfnParameter {
  constructor(scope: Construct, id: string, props: ParameterWithLabelProps) {
    super(scope, id, props);

    if (props.label) {
      addParameterLabel(this, props.label);
    }
  }
}

export interface YesNoParameterProps extends ParameterWithLabelProps {
  default?: keyof typeof YesNoType;
}

export class YesNoParameter extends ParameterWithLabel {
  private condition?: CfnCondition;
  private conditionId: string;

  constructor(scope: Construct, id: string, props?: ParameterWithLabelProps) {
    super(scope, id, {
      allowedValues: [YesNoType.Yes, YesNoType.No],
      ...props,
    });
    this.conditionId = `${id}Condition`;
  }

  getCondition(): CfnCondition {
    if (!this.condition) {
      this.condition = yesNoCondition(this.stack, this.conditionId, this.valueAsString);
    }
    return this.condition;
  }
}

export interface EnabledDisabledParameterProps extends ParameterWithLabelProps {
  default?: keyof typeof EnabledDisabledType;
}

export class EnabledDisabledParameter extends ParameterWithLabel {
  private condition?: CfnCondition;
  private conditionId: string;

  constructor(scope: Construct, id: string, props?: ParameterWithLabelProps) {
    super(scope, id, {
      allowedValues: [EnabledDisabledType.Enabled, EnabledDisabledType.Disabled],
      ...props,
    });
    this.conditionId = `${id}Condition`;
  }

  getCondition(): CfnCondition {
    if (!this.condition) {
      this.condition = enabledDisabledCondition(this.stack, this.conditionId, this.valueAsString);
    }
    return this.condition;
  }
}
