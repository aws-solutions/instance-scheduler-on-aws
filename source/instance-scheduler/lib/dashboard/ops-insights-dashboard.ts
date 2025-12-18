// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { Aspects, Aws, CfnCondition, Duration, Stack, Token } from "aws-cdk-lib";
import { Color, Column, Dashboard, PeriodOverride, SingleValueWidget, TextWidget } from "aws-cdk-lib/aws-cloudwatch";
import {
  ControlledEc2InstancesByTypePieChart,
  ControlledRDSInstancesByTypePieChart,
  EC2HoursSavedPieChart,
  LambdaDurationLineChart,
  LambdaErrorRateLineChart,
  RdsHoursSavedPieChart,
  Size,
  RunningEC2InstancesByTypeLineChart,
  RunningRDSInstancesByTypeLineChart,
  RunningResourcesLineChart,
} from "./widgets";
import { Metrics } from "./metrics";
import { ConditionAspect } from "../cfn";
import { SchedulingRequestHandlerLambda } from "../lambda-functions/scheduling-request-handler";
import { SchedulingOrchestrator } from "../lambda-functions/scheduling-orchestrator";

export interface OperationalInsightsDashboardProps {
  readonly enabled: CfnCondition;
  readonly schedulingRequestHandler: SchedulingRequestHandlerLambda;
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
      orchestrator: props.orchestrator,
      schedulingIntervalMinutes: props.schedulingIntervalMinutes,
    });

    dashboard.addWidgets(
      new TextWidget({
        markdown: "# Overview",
        width: Size.FULL_WIDTH,
        height: 1,
      }),
    );

    dashboard.addWidgets(
      new Column(
        new SingleValueWidget({
          title: "Controlled EC2 Instances",
          width: Size.QUARTER_WIDTH,
          height: 4,
          metrics: [
            metrics.TotalEc2InstancesControlled().with({
              label: "Controlled EC2 Instances",
              color: Color.BLUE,
            }),
          ],
          period: Duration.seconds(Token.asNumber(metrics.schedulingIntervalSeconds)),
          sparkline: true,
        }),
        new SingleValueWidget({
          title: "Controlled RDS Instances",
          width: Size.QUARTER_WIDTH,
          height: 4,
          metrics: [
            metrics.TotalRDSInstancesControlled().with({
              label: "Controlled RDS Instances",
              color: Color.RED,
            }),
          ],
          period: Duration.seconds(Token.asNumber(metrics.schedulingIntervalSeconds)),
          sparkline: true,
        }),
        new SingleValueWidget({
          title: "Controlled ASGs",
          width: Size.QUARTER_WIDTH,
          height: 4,
          metrics: [
            metrics.TotalAsgsControlled().with({
              label: "Controlled ASGs",
              color: Color.GREEN,
            }),
          ],
          period: Duration.seconds(Token.asNumber(metrics.schedulingIntervalSeconds)),
          sparkline: true,
        }),
      ),
      new Column(
        new ControlledEc2InstancesByTypePieChart(metrics, {
          width: Size.QUARTER_WIDTH,
          height: Size.QUARTER_WIDTH,
        }),
        new ControlledRDSInstancesByTypePieChart(metrics, {
          width: Size.QUARTER_WIDTH,
          height: Size.QUARTER_WIDTH,
        }),
      ),
      new Column(
        new SingleValueWidget({
          title: "EC2 Hours Saved",
          width: Size.QUARTER_WIDTH,
          height: 4,
          metrics: [
            metrics.TotalEc2HoursSaved().with({
              label: "Hours Saved",
              color: Color.BLUE,
            }),
          ],
          setPeriodToTimeRange: true,
        }),
        new SingleValueWidget({
          title: "RDS Hours Saved",
          width: Size.QUARTER_WIDTH,
          height: 4,
          metrics: [
            metrics.TotalRDSHoursSaved().with({
              label: "Hours Saved",
              color: Color.RED,
            }),
          ],
          setPeriodToTimeRange: true,
        }),
        new SingleValueWidget({
          title: "ASG Hours Saved",
          width: Size.QUARTER_WIDTH,
          height: 4,
          metrics: [
            metrics.TotalAsgHoursSaved().with({
              label: "Hours Saved",
              color: Color.GREEN,
            }),
          ],
          setPeriodToTimeRange: true,
        }),
      ),
      new Column(
        new EC2HoursSavedPieChart(metrics, {
          width: Size.QUARTER_WIDTH,
          height: Size.QUARTER_WIDTH,
        }),
        new RdsHoursSavedPieChart(metrics, {
          width: Size.QUARTER_WIDTH,
          height: Size.QUARTER_WIDTH,
        }),
      ),
    );

    dashboard.addWidgets(
      new TextWidget({
        markdown: "# Running Resources",
        width: Size.FULL_WIDTH,
        height: 1,
      }),
    );

    dashboard.addWidgets(
      new RunningResourcesLineChart(metrics, {
        width: Size.FULL_WIDTH,
        height: 6,
      }),
    );

    dashboard.addWidgets(
      new RunningEC2InstancesByTypeLineChart(metrics, {
        width: Size.HALF_WIDTH,
        height: 6,
      }),
      new RunningRDSInstancesByTypeLineChart(metrics, {
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
