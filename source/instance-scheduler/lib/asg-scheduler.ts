// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { Aspects, CfnCondition, Duration } from "aws-cdk-lib";
import { Table } from "aws-cdk-lib/aws-dynamodb";
import { Rule, RuleTargetInput, Schedule } from "aws-cdk-lib/aws-events";
import { LambdaFunction as LambdaFunctionTarget } from "aws-cdk-lib/aws-events-targets";
import { Key } from "aws-cdk-lib/aws-kms";
import { Function as LambdaFunction } from "aws-cdk-lib/aws-lambda";
import { RetentionDays } from "aws-cdk-lib/aws-logs";
import { Topic } from "aws-cdk-lib/aws-sns";
import { Construct } from "constructs";
import { AnonymizedMetricsEnvironment } from "./anonymized-metrics-environment";
import { AsgSchedulingRole } from "./iam/asg-scheduling-role";
import { AsgHandler } from "./lambda-functions/asg-handler";
import { AsgOrchestrator } from "./lambda-functions/asg-orchestrator";
import { FunctionFactory } from "./lambda-functions/function-factory";
import { ScheduleUpdateHandler } from "./lambda-functions/schedule-update-handler";
import { ConditionAspect } from "./cfn";

interface AsgSchedulerProps {
  readonly USER_AGENT_EXTRA: string;
  readonly asgHandler: AsgHandler;
  readonly orchestratorMemorySizeMB: number;
  readonly configTable: Table;
  readonly enableAsgs: CfnCondition;
  readonly enableDebugLogging: CfnCondition;
  readonly enableSchedulingHubAccount: CfnCondition;
  readonly encryptionKey: Key;
  readonly factory: FunctionFactory;
  readonly logRetentionDays: RetentionDays;
  readonly metricsEnv: AnonymizedMetricsEnvironment;
  readonly namespace: string;
  readonly regions: string[];
  readonly snsErrorReportingTopic: Topic;
  readonly solutionVersion: string;
}

export class AsgScheduler extends Construct {
  public asgOrchestratorLambdaFunction: LambdaFunction;

  constructor(scope: Construct, id: string, props: AsgSchedulerProps) {
    super(scope, id);

    const asgOrchestrator = new AsgOrchestrator(this, {
      USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
      asgHandler: props.asgHandler.lambdaFunction,
      memorySizeMB: props.orchestratorMemorySizeMB,
      configTable: props.configTable,
      enableDebugLogging: props.enableDebugLogging,
      enableSchedulingHubAccount: props.enableSchedulingHubAccount,
      encryptionKey: props.encryptionKey,
      factory: props.factory,
      logRetentionDays: props.logRetentionDays,
      metricsEnv: props.metricsEnv,
      regions: props.regions,
      snsErrorReportingTopic: props.snsErrorReportingTopic,
    });
    this.asgOrchestratorLambdaFunction = asgOrchestrator.lambdaFunction;

    new ScheduleUpdateHandler(this, {
      USER_AGENT_EXTRA: props.USER_AGENT_EXTRA,
      asgHandler: props.asgHandler.lambdaFunction,
      memorySizeMB: props.orchestratorMemorySizeMB,
      configTable: props.configTable,
      enableDebugLogging: props.enableDebugLogging,
      enableSchedulingHubAccount: props.enableSchedulingHubAccount,
      encryptionKey: props.encryptionKey,
      factory: props.factory,
      logRetentionDays: props.logRetentionDays,
      metricsEnv: props.metricsEnv,
      regions: props.regions,
      snsErrorReportingTopic: props.snsErrorReportingTopic,
    });

    new Rule(this, "ASGOrchRule", {
      description: `Instance Scheduler - Rule to trigger scheduling for AutoScaling Groups version ${props.solutionVersion}`,
      schedule: Schedule.rate(Duration.hours(1)),
      targets: [
        new LambdaFunctionTarget(asgOrchestrator.lambdaFunction, {
          event: RuleTargetInput.fromObject({}),
          retryAttempts: 5,
        }),
      ],
    });

    new AsgSchedulingRole(this, "AsgSchedulingRole", {
      assumedBy: props.asgHandler.role.grantPrincipal,
      namespace: props.namespace,
    });

    const conditionAspect = new ConditionAspect(props.enableAsgs);
    Aspects.of(this).add(conditionAspect);
  }
}
