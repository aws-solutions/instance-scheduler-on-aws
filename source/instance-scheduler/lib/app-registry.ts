// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import * as cdk from "aws-cdk-lib";
import * as servicecatalogappregistry from "aws-cdk-lib/aws-servicecatalogappregistry";
import { Construct } from "constructs";
import { Aws, Stack, Tags } from "aws-cdk-lib";

export interface AppRegistryIntegrationProps extends cdk.StackProps {
  readonly solutionId: string;
  readonly solutionName: string;
  readonly solutionVersion: string;
  readonly appregAppName: string;
  readonly appregSolutionName: string;
}

export class AppRegistryIntegration extends Construct {
  readonly application: servicecatalogappregistry.CfnApplication;

  constructor(scope: Stack, id: string, props: AppRegistryIntegrationProps) {
    super(scope, id);

    const map = new cdk.CfnMapping(this, "Solution");
    map.setValue("Data", "ID", props.solutionId);
    map.setValue("Data", "Version", props.solutionVersion);
    map.setValue("Data", "AppRegistryApplicationName", props.appregSolutionName);
    map.setValue("Data", "SolutionName", props.solutionName);
    map.setValue("Data", "ApplicationType", props.appregAppName);

    this.application = new servicecatalogappregistry.CfnApplication(scope, "AppRegistry", {
      name: cdk.Fn.join("-", [
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

    //update-path backwards compatibility with 3.0.8
    this.application.overrideLogicalId("AppRegistry968496A3");

    Tags.of(this.application).add("Solutions:SolutionID", map.findInMap("Data", "ID"));
    Tags.of(this.application).add("Solutions:SolutionName", map.findInMap("Data", "SolutionName"));
    Tags.of(this.application).add("Solutions:SolutionVersion", map.findInMap("Data", "Version"));
    Tags.of(this.application).add("Solutions:ApplicationType", map.findInMap("Data", "ApplicationType"));
  }

  addApplicationTags(resource: Construct) {
    Tags.of(resource).add("awsApplication", `${this.application.attrApplicationTagValue}`, {
      excludeResourceTypes: ["AWS::ServiceCatalogAppRegistry::Application", "aws:cdk:stack"],
    });
  }
}
