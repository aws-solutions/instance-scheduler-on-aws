// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import * as cdk from "aws-cdk-lib";
import { Construct, IConstruct } from "constructs";
import { Aspects, Aws, Stack, Tags } from "aws-cdk-lib";
import { CfnResourceAssociation } from "aws-cdk-lib/aws-servicecatalogappregistry";
import * as appreg from "@aws-cdk/aws-servicecatalogappregistry-alpha";

export interface AppRegistryForInstanceSchedulerProps extends cdk.StackProps {
  readonly solutionId: string;
  readonly solutionName: string;
  readonly solutionVersion: string;
  readonly appregAppName: string;
  readonly appregSolutionName: string;
}

export class AppRegistryForInstanceScheduler extends Construct {
  constructor(scope: Stack, id: string, props: AppRegistryForInstanceSchedulerProps) {
    super(scope, id);

    const isNotChinaRegionCondition = new cdk.CfnCondition(this, "IsNotChinaRegionCondition", {
      expression: cdk.Fn.conditionNot(cdk.Fn.conditionEquals(Aws.PARTITION, "aws-cn")),
    });

    const map = new cdk.CfnMapping(this, "Solution");
    map.setValue("Data", "ID", props.solutionId);
    map.setValue("Data", "Version", props.solutionVersion);
    map.setValue("Data", "AppRegistryApplicationName", props.appregSolutionName);
    map.setValue("Data", "SolutionName", props.solutionName);
    map.setValue("Data", "ApplicationType", props.appregAppName);

    const application = new appreg.Application(scope, "AppRegistry", {
      applicationName: cdk.Fn.join("-", [
        map.findInMap("Data", "AppRegistryApplicationName"),
        Aws.REGION,
        Aws.ACCOUNT_ID,
        Aws.STACK_NAME,
      ]),
      description: `Service Catalog application to track and manage all your resources for the solution ${map.findInMap(
        "Data",
        "SolutionName",
      )}`,
    });
    application.associateApplicationWithStack(scope);
    Tags.of(application).add("Solutions:SolutionID", map.findInMap("Data", "ID"));
    Tags.of(application).add("Solutions:SolutionName", map.findInMap("Data", "SolutionName"));
    Tags.of(application).add("Solutions:SolutionVersion", map.findInMap("Data", "Version"));
    Tags.of(application).add("Solutions:ApplicationType", map.findInMap("Data", "ApplicationType"));

    application.addAttributeGroup("DefaultApplicationAttributes", {
      attributeGroupName: `attgroup-${cdk.Fn.join("-", [Aws.REGION, Aws.STACK_NAME])}`,
      description: "Attribute group for solution information",
      attributes: {
        applicationType: map.findInMap("Data", "ApplicationType"),
        version: map.findInMap("Data", "Version"),
        solutionID: map.findInMap("Data", "ID"),
        solutionName: map.findInMap("Data", "SolutionName"),
      },
    });

    Aspects.of(application).add(new InjectCondition(isNotChinaRegionCondition));
    Aspects.of(scope).add(new InjectCondition(isNotChinaRegionCondition, CfnResourceAssociation));
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
class InjectCondition<T extends new (...p: any[]) => cdk.CfnResource> implements cdk.IAspect {
  public constructor(
    private condition: cdk.CfnCondition,
    private cls?: T,
  ) {}

  public visit(node: IConstruct): void {
    if (node instanceof (this.cls ?? cdk.CfnResource)) {
      node.cfnOptions.condition = this.condition;
    }
  }
}
