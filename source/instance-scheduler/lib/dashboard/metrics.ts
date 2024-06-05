// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { MathExpression, Metric } from "aws-cdk-lib/aws-cloudwatch";
import { Aws, Stack } from "aws-cdk-lib";
import { SchedulingRequestHandlerLambda } from "../lambda-functions/scheduling-request-handler";
import { AsgHandler } from "../lambda-functions/asg-handler";
import { SchedulingOrchestrator } from "../lambda-functions/scheduling-orchestrator";
import { SchedulingIntervalToSeconds } from "../scheduling-interval-mappings";

export interface MetricProps {
  readonly schedulingRequestHandler: SchedulingRequestHandlerLambda;
  readonly asgHandler: AsgHandler;
  readonly orchestrator: SchedulingOrchestrator;
  readonly schedulingIntervalMinutes: number;
}
export class Metrics {
  /*
  helper class for defining the underlying metrics available to the solution for ingestion into dashboard widgets

   */
  public static readonly metricNamespace = `${Aws.STACK_NAME}:InstanceScheduler`;

  public readonly schedulingIntervalMinutes;
  public readonly schedulingIntervalSeconds;
  private readonly props;

  constructor(scope: Stack, props: MetricProps) {
    this.props = props;
    this.schedulingIntervalMinutes = props.schedulingIntervalMinutes;
    // use a mapping to translate interval minutes to seconds
    this.schedulingIntervalSeconds = new SchedulingIntervalToSeconds(
      scope,
      "MetricsSchedulingIntervalToSeconds",
      {},
    ).getMapping(this.props.schedulingIntervalMinutes.toString());
  }

  TotalEc2InstancesControlled() {
    return new MathExpression({
      expression: `SUM(SEARCH('{"${Metrics.metricNamespace}",Service,InstanceType,SchedulingInterval} "Service"="ec2" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName=ManagedInstances', 'Sum', ${this.schedulingIntervalSeconds}))`,
    });
  }

  TotalEc2HoursSaved() {
    const searchExpr = `SEARCH('{"${Metrics.metricNamespace}",Service,InstanceType,SchedulingInterval} Service="ec2" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="StoppedInstances"', 'Sum', ${this.schedulingIntervalSeconds})`;
    return new MathExpression({
      expression: `SUM(${searchExpr}) * ${this.props.schedulingIntervalMinutes} / 60`,
    });
  }

  TotalRDSInstancesControlled() {
    return new MathExpression({
      expression: `SUM(SEARCH('{"${Metrics.metricNamespace}",Service,InstanceType,SchedulingInterval} "Service"="rds" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName=ManagedInstances', 'Sum', ${this.schedulingIntervalSeconds}))`,
    });
  }

  TotalRDSHoursSaved() {
    const searchExpr = `SEARCH('{"${Metrics.metricNamespace}",Service,InstanceType,SchedulingInterval} Service="rds" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="StoppedInstances"', 'Sum', ${this.schedulingIntervalSeconds})`;
    return new MathExpression({
      expression: `SUM(${searchExpr}) * ${this.props.schedulingIntervalMinutes} / 60`,
    });
  }
  Ec2InstancesControlledByType() {
    return new MathExpression({
      expression: `SEARCH('{"${Metrics.metricNamespace}",Service,InstanceType,SchedulingInterval} "Service"="ec2" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName=ManagedInstances', 'Sum', ${this.schedulingIntervalSeconds})`,
    });
  }

  Ec2InstancesControlledBySchedule() {
    return new MathExpression({
      expression: `SEARCH('{"${Metrics.metricNamespace}",Service,Schedule,SchedulingInterval} Service="ec2" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="ManagedInstances"', 'Sum', ${this.schedulingIntervalSeconds})`,
    });
  }

  Ec2InstancesRunningByType() {
    return new MathExpression({
      expression: `SEARCH('{"${Metrics.metricNamespace}",Service,InstanceType,SchedulingInterval} Service="ec2" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="RunningInstances"', 'Sum', ${this.schedulingIntervalSeconds})`,
    });
  }

  Ec2InstancesRunningBySchedule() {
    return new MathExpression({
      expression: `SEARCH('{"${Metrics.metricNamespace}",Service,Schedule,SchedulingInterval} Service="ec2" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="RunningInstances"', 'Sum', ${this.schedulingIntervalSeconds})`,
    });
  }

  Ec2HoursSaved() {
    const searchExpr = `SEARCH('{"${Metrics.metricNamespace}",Service,InstanceType,SchedulingInterval} Service="ec2" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="StoppedInstances"', 'Sum', ${this.schedulingIntervalSeconds})`;
    return new MathExpression({
      expression: `${searchExpr} * ${this.props.schedulingIntervalMinutes} / 60`,
    });
  }

  RdsInstancesControlledByType() {
    return new MathExpression({
      expression: `SEARCH('{"${Metrics.metricNamespace}",Service,InstanceType,SchedulingInterval} "Service"="rds" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="ManagedInstances"', 'Sum', ${this.schedulingIntervalSeconds})`,
    });
  }

  RdsInstancesControlledBySchedule() {
    return new MathExpression({
      expression: `SEARCH('{"${Metrics.metricNamespace}",Service,Schedule,SchedulingInterval} Service="rds" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="ManagedInstances"', 'Sum', ${this.schedulingIntervalSeconds})`,
    });
  }

  RdsInstancesRunningByType() {
    return new MathExpression({
      expression: `SEARCH('{"${Metrics.metricNamespace}",Service,InstanceType,SchedulingInterval} Service="rds" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="RunningInstances"', 'Sum', ${this.schedulingIntervalSeconds})`,
    });
  }

  RdsInstancesRunningBySchedule() {
    return new MathExpression({
      expression: `SEARCH('{"${Metrics.metricNamespace}",Service,Schedule,SchedulingInterval} Service="rds" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="RunningInstances"', 'Sum', ${this.schedulingIntervalSeconds})`,
    });
  }

  RdsHoursSaved() {
    const searchExpr = `SEARCH('{"${Metrics.metricNamespace}",Service,InstanceType,SchedulingInterval} Service="rds" "SchedulingInterval"="${this.schedulingIntervalMinutes}" MetricName="StoppedInstances"', 'Sum', ${this.schedulingIntervalSeconds})`;
    return new MathExpression({
      expression: `${searchExpr} * ${this.props.schedulingIntervalMinutes} / 60`,
    });
  }

  OrchestratorLambdaErrors() {
    return new Metric({
      namespace: "AWS/Lambda",
      metricName: "Errors",
      dimensionsMap: {
        FunctionName: this.props.orchestrator.lambdaFunction.functionName,
      },
    });
  }

  SchedulingRequestHandlerLambdaErrors() {
    return new Metric({
      namespace: "AWS/Lambda",
      metricName: "Errors",
      dimensionsMap: {
        FunctionName: this.props.schedulingRequestHandler.lambdaFunction.functionName,
      },
    });
  }

  AsgHandlerLambdaErrors() {
    return new Metric({
      namespace: "AWS/Lambda",
      metricName: "Errors",
      dimensionsMap: {
        FunctionName: this.props.asgHandler.lambdaFunction.functionName,
      },
    });
  }

  OrchestratorLambdaDuration() {
    return new Metric({
      namespace: "AWS/Lambda",
      metricName: "Duration",
      dimensionsMap: {
        FunctionName: this.props.orchestrator.lambdaFunction.functionName,
      },
    });
  }

  SchedulingRequestHandlerLambdaDuration() {
    return new Metric({
      namespace: "AWS/Lambda",
      metricName: "Duration",
      dimensionsMap: {
        FunctionName: this.props.schedulingRequestHandler.lambdaFunction.functionName,
      },
    });
  }

  AsgHandlerLambdaDuration() {
    return new Metric({
      namespace: "AWS/Lambda",
      metricName: "Duration",
      dimensionsMap: {
        FunctionName: this.props.asgHandler.lambdaFunction.functionName,
      },
    });
  }
}
