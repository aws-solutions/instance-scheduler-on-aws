// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aws, CfnCondition, CustomResource, Duration, Stack } from "aws-cdk-lib";
import { Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { Topic } from "aws-cdk-lib/aws-sns";
import { NagSuppressions } from "cdk-nag";
import { cfnConditionToTrueFalse, overrideLogicalId } from "../cfn";
import { FunctionFactory } from "./function-factory";
import { AnonymizedMetricsEnvironment } from "../anonymized-metrics-environment";
import { InstanceSchedulerDataLayer } from "../instance-scheduler-data-layer";
import { ISLogGroups } from "../observability/log-groups";

export interface MainLambdaProps {
  readonly DEFAULT_TIMEZONE: string;
  readonly USER_AGENT_EXTRA: string;
  readonly dataLayer: InstanceSchedulerDataLayer;
  readonly metricsEnv: AnonymizedMetricsEnvironment;
  readonly snsErrorReportingTopic: Topic;
  readonly enableAwsOrganizations: CfnCondition;
  readonly principals: string[];
  readonly factory: FunctionFactory;
}
export class MainLambda {
  /*
  For backwards compatibility with <1.5.x this function encapsulates the CFN, CLI, and ServiceSetup handlers
   */

  readonly lambdaFunction: LambdaFunction;

  constructor(scope: Stack, props: MainLambdaProps) {
    const role = new Role(scope, "MainLambdaRole", {
      assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
    });

    const functionName = Aws.STACK_NAME + "-InstanceSchedulerMain";
    this.lambdaFunction = props.factory.createFunction(scope, "scheduler-lambda", {
      functionName: functionName,
      description: "CLI and CFN schedule manager for Instance Scheduler version " + props.metricsEnv.SOLUTION_VERSION,
      index: "instance_scheduler/main.py",
      handler: "lambda_handler",
      role: role,
      memorySize: 512,
      timeout: Duration.seconds(300),
      logGroup: ISLogGroups.adminLogGroup(scope),
      environment: {
        ISSUES_TOPIC_ARN: props.snsErrorReportingTopic.topicArn,
        USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
        DEFAULT_TIMEZONE: props.DEFAULT_TIMEZONE,
        ENABLE_AWS_ORGANIZATIONS: cfnConditionToTrueFalse(props.enableAwsOrganizations),
        CONFIG_TABLE: props.dataLayer.configTable.tableName,
        ...props.metricsEnv,
      },
    });

    //backwards compatibility (<1.5.x) override
    overrideLogicalId(this.lambdaFunction, "Main");

    const customService = new CustomResource(scope, "ServiceSetup", {
      serviceToken: this.lambdaFunction.functionArn,
      resourceType: "Custom::ServiceSetup",
      properties: {
        timeout: 120,
        remote_account_ids: props.principals,
      },
    });
    overrideLogicalId(customService, "SchedulerConfigHelper");

    if (!this.lambdaFunction.role) {
      throw new Error("lambdaFunction role is missing");
    }

    props.dataLayer.configTable.grantReadWriteData(this.lambdaFunction.role);
    ISLogGroups.adminLogGroup(scope).grantWrite(this.lambdaFunction.role);
    props.snsErrorReportingTopic.grantPublish(this.lambdaFunction.role);

    const defaultPolicy = this.lambdaFunction.role.node.tryFindChild("DefaultPolicy");
    if (!defaultPolicy) {
      throw Error("Unable to find default policy on lambda role");
    }

    NagSuppressions.addResourceSuppressions(defaultPolicy, [
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Action::kms:GenerateDataKey*", "Action::kms:ReEncrypt*"],
        reason: "Permission to use solution CMK with dynamo/sns",
      },
      {
        id: "AwsSolutions-IAM5",
        appliesTo: ["Resource::*"],
        reason: "required for xray",
      },
    ]);
  }
}
