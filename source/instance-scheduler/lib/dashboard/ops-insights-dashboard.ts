// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aspects, Aws, CfnCondition, Duration, Stack } from "aws-cdk-lib";
import { Dashboard, PeriodOverride, TextWidget } from "aws-cdk-lib/aws-cloudwatch";
import {
  ControlledEC2InstancesByScheduleLineChart,
  ControlledEC2InstancesByTypeLineChart,
  ControlledEc2InstancesPieChart,
  ControlledRdsInstancesByScheduleLineChart,
  ControlledRDSInstancesByTypeLineChart,
  ControlledRDSInstancesPieChart,
  EC2HoursSavedPieChart,
  LambdaDurationLineChart,
  LambdaErrorRateLineChart,
  RdsHoursSavedPieChart,
  RunningEC2InstancesByScheduleLineChart,
  RunningRdsInstancesByScheduleLineChart,
  Size,
  RunningEC2InstancesByTypeLineChart,
  RunningRDSInstancesByTypeLineChart,
  TotalControlledEc2InstancesKPI,
  TotalControlledRdsInstancesKPI,
  TotalEc2HoursSavedInstancesKPI,
  TotalRdsHoursSavedInstancesKPI,
} from "./widgets";
import { Metrics } from "./metrics";
import { ConditionAspect } from "../cfn";
import { SchedulingRequestHandlerLambda } from "../lambda-functions/scheduling-request-handler";
import { AsgHandler } from "../lambda-functions/asg-handler";
import { SchedulingOrchestrator } from "../lambda-functions/scheduling-orchestrator";

export interface OperationalInsightsDashboardProps {
  readonly enabled: CfnCondition;
  readonly schedulingRequestHandler: SchedulingRequestHandlerLambda;
  readonly asgHandler: AsgHandler;
  readonly orchestrator: SchedulingOrchestrator;
  readonly schedulingIntervalMinutes: number;
  readonly namespace: string;
}
export class OperationalInsightsDashboard {
  constructor(scope: Stack, props: OperationalInsightsDashboardProps) {
    const dashboard = new Dashboard(scope, "OperationalInsightsDashboard", {
      dashboardName: `${Aws.STACK_NAME}-${props.namespace}-Operational-Insights-Dashboard`,
      defaultInterval: Duration.days(7),
      periodOverride: PeriodOverride.INHERIT,
    });

    const metrics = new Metrics(scope, {
      schedulingRequestHandler: props.schedulingRequestHandler,
      asgHandler: props.asgHandler,
      orchestrator: props.orchestrator,
      schedulingIntervalMinutes: props.schedulingIntervalMinutes,
    });

    dashboard.addWidgets(
      new TextWidget({
        markdown: "# EC2",
        width: Size.FULL_WIDTH,
        height: 1,
      }),
    );

    dashboard.addWidgets(
      new TotalControlledEc2InstancesKPI(metrics, {
        width: Size.QUARTER_WIDTH,
        height: Size.QUARTER_WIDTH,
      }),
      new ControlledEc2InstancesPieChart(metrics, {
        width: Size.QUARTER_WIDTH,
        height: Size.QUARTER_WIDTH,
      }),
      new TotalEc2HoursSavedInstancesKPI(metrics, {
        width: Size.QUARTER_WIDTH,
        height: Size.QUARTER_WIDTH,
      }),
      new EC2HoursSavedPieChart(metrics, {
        width: Size.QUARTER_WIDTH,
        height: Size.QUARTER_WIDTH,
      }),
    );

    dashboard.addWidgets(
      new ControlledEC2InstancesByTypeLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
      new RunningEC2InstancesByTypeLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
    );

    dashboard.addWidgets(
      new ControlledEC2InstancesByScheduleLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
      new RunningEC2InstancesByScheduleLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
    );

    dashboard.addWidgets(
      new TextWidget({
        markdown: "# RDS",
        width: Size.FULL_WIDTH,
        height: 1,
      }),
    );

    dashboard.addWidgets(
      new TotalControlledRdsInstancesKPI(metrics, {
        width: Size.QUARTER_WIDTH,
        height: Size.QUARTER_WIDTH,
      }),
      new ControlledRDSInstancesPieChart(metrics, {
        width: Size.QUARTER_WIDTH,
        height: Size.QUARTER_WIDTH,
      }),
      new TotalRdsHoursSavedInstancesKPI(metrics, {
        width: Size.QUARTER_WIDTH,
        height: Size.QUARTER_WIDTH,
      }),
      new RdsHoursSavedPieChart(metrics, {
        width: Size.QUARTER_WIDTH,
        height: Size.QUARTER_WIDTH,
      }),
    );

    dashboard.addWidgets(
      new ControlledRDSInstancesByTypeLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
      new RunningRDSInstancesByTypeLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
    );

    dashboard.addWidgets(
      new ControlledRdsInstancesByScheduleLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
      new RunningRdsInstancesByScheduleLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
    );

    dashboard.addWidgets(
      new TextWidget({
        markdown: "# Lambda",
        width: Size.FULL_WIDTH,
        height: 1,
      }),
    );

    dashboard.addWidgets(
      new LambdaDurationLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
      new LambdaErrorRateLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
    );

    const dashboardConditionAspect = new ConditionAspect(props.enabled);
    Aspects.of(dashboard).add(dashboardConditionAspect);
  }
}
