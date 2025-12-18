// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import {
  Color,
  GraphWidget,
  GraphWidgetView,
  LegendPosition,
  Shading,
  SingleValueWidget,
  Stats,
} from "aws-cdk-lib/aws-cloudwatch";
import { Duration, Token } from "aws-cdk-lib";
import { Metrics } from "./metrics";

export enum Size {
  FULL_WIDTH = 24,
  HALF_WIDTH = 12,
  QUARTER_WIDTH = 6,
  SMALL = 3,
}
export interface WidgetProps {
  width: number;
  height: number;
}
export class TotalHoursSavedInstancesKPI extends SingleValueWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Total Hours Saved",
      width: props.width,
      height: props.height,
      metrics: [
        metrics.TotalEc2HoursSaved().with({
          label: "EC2",
          color: Color.BLUE,
        }),
        metrics.TotalRDSHoursSaved().with({
          label: "RDS",
          color: Color.RED,
        }),
        metrics.TotalAsgHoursSaved().with({
          label: "ASG",
          color: Color.GREEN,
        }),
      ],
      setPeriodToTimeRange: true,
    });
  }
}

export class TotalRdsHoursSavedInstancesKPI extends SingleValueWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Total RDS Hours Saved",
      width: props.width,
      height: props.height,
      metrics: [
        metrics.TotalRDSHoursSaved().with({
          label: "Hours Saved",
        }),
      ],
      setPeriodToTimeRange: true,
    });
  }
}

export class ControlledResourcesKPI extends SingleValueWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Controlled Resources",
      width: props.width,
      height: props.height,
      metrics: [
        metrics.TotalEc2InstancesControlled().with({
          label: "EC2 Instances",
          color: Color.BLUE,
        }),
        metrics.TotalRDSInstancesControlled().with({
          label: "RDS Instances",
          color: Color.RED,
        }),
        metrics.TotalAsgsControlled().with({
          label: "ASGs",
          color: Color.GREEN,
        }),
      ],
      period: Duration.seconds(Token.asNumber(metrics.schedulingIntervalSeconds)),
      sparkline: true,
    });
  }
}

export class TotalControlledRdsInstancesKPI extends SingleValueWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Total RDS Instances Controlled",
      width: props.width,
      height: props.height,
      metrics: [
        metrics.TotalRDSInstancesControlled().with({
          label: "RDS Instances",
        }),
      ],
      period: Duration.seconds(Token.asNumber(metrics.schedulingIntervalSeconds)),
    });
  }
}

export class EC2HoursSavedPieChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "EC2 Hours Saved",
      view: GraphWidgetView.PIE,
      left: [
        metrics.Ec2HoursSaved().with({
          label: "[${SUM}]",
        }),
      ],
      legendPosition: LegendPosition.RIGHT,
      statistic: Stats.SUM,
      width: props.width,
      height: props.height,
      setPeriodToTimeRange: true,
    });
  }
}

export class RdsHoursSavedPieChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "RDS Hours Saved",
      view: GraphWidgetView.PIE,
      left: [
        metrics.RdsHoursSaved().with({
          period: Duration.days(30),
          label: "[${SUM}]",
        }),
      ],
      legendPosition: LegendPosition.RIGHT,
      statistic: Stats.SUM,
      width: props.width,
      height: props.height,
      setPeriodToTimeRange: true,
    });
  }
}

export class ControlledEc2InstancesByTypePieChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Controlled EC2 Instances by Type",
      view: GraphWidgetView.PIE,
      width: props.width,
      height: props.height,
      left: [
        metrics.Ec2InstancesControlledByType().with({
          label: "[${LAST}]",
        }),
      ],
      legendPosition: LegendPosition.RIGHT,
      period: Duration.seconds(Token.asNumber(metrics.schedulingIntervalSeconds)),
    });
  }
}

export class ControlledResourcesPieChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "ControlledResources",
      view: GraphWidgetView.PIE,
      width: props.width,
      height: props.height,
      left: [
        metrics.TotalAsgsControlled().with({
          label: "[${LAST}] ASG",
          color: Color.GREEN,
        }),
        metrics.TotalEc2InstancesControlled().with({
          label: "[${LAST}] EC2",
          color: Color.BLUE,
        }),
        metrics.TotalRDSInstancesControlled().with({
          label: "[${LAST}] RDS",
          color: Color.RED,
        }),
      ],
      legendPosition: LegendPosition.RIGHT,
      period: Duration.seconds(Token.asNumber(metrics.schedulingIntervalSeconds)),
    });
  }
}

export class ControlledRDSInstancesByTypePieChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Controlled RDS Instances by Type",
      view: GraphWidgetView.PIE,
      width: props.width,
      height: props.height,
      left: [
        metrics.RdsInstancesControlledByType().with({
          label: "[${LAST}]",
        }),
      ],
      legendPosition: LegendPosition.RIGHT,
      period: Duration.seconds(Token.asNumber(metrics.schedulingIntervalSeconds)),
    });
  }
}

export class ControlledEC2InstancesByTypeLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Controlled EC2 Instances by Type",
      width: props.width,
      height: props.height,
      left: [
        metrics.Ec2InstancesControlledByType().with({
          label: "",
        }),
        metrics.AsgsControlledByType().with({
          label: "",
        }),
      ],
      leftYAxis: {
        label: "EC2 Instances",
        showUnits: false,
        min: 0,
      },
      legendPosition: LegendPosition.BOTTOM,
    });
  }
}

export class ControlledEC2InstancesByScheduleLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Controlled EC2 Instances by Schedule",
      width: props.width,
      height: props.height,
      left: [
        metrics.Ec2InstancesControlledBySchedule().with({
          label: "",
        }),
      ],
      leftYAxis: {
        label: "EC2 Instances",
        showUnits: false,
        min: 0,
      },
      legendPosition: LegendPosition.BOTTOM,
    });
  }
}

export class RunningEC2InstancesByScheduleLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Running EC2 Instances by Schedule",
      width: props.width,
      height: props.height,
      left: [
        metrics.Ec2InstancesRunningBySchedule().with({
          label: "",
        }),
      ],
      leftYAxis: {
        label: "Running EC2 Instances",
        showUnits: false,
        min: 0,
      },
      legendPosition: LegendPosition.BOTTOM,
    });
  }
}

export class RunningResourcesLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Running Resources",
      width: props.width,
      height: props.height,
      left: [
        metrics.RunningEC2Instances().with({
          label: "EC2",
          color: Color.BLUE,
        }),
        metrics.RunningRDSInstances().with({
          label: "RDS",
          color: Color.RED,
        }),
        metrics.RunningASGs().with({
          label: "ASG",
          color: Color.GREEN,
        }),
      ],
      leftYAxis: {
        showUnits: false,
        min: 0,
      },
      legendPosition: LegendPosition.BOTTOM,
    });
  }
}

export class RunningEC2InstancesByTypeLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Running EC2 Instances by Type",
      width: props.width,
      height: props.height,
      left: [
        metrics.Ec2InstancesRunningByType().with({
          label: "",
        }),
      ],
      leftYAxis: {
        showUnits: false,
        min: 0,
      },
      legendPosition: LegendPosition.BOTTOM,
    });
  }
}

export class ControlledRDSInstancesByTypeLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Controlled RDS Instances by Type",
      width: props.width,
      height: props.height,
      left: [
        metrics.RdsInstancesControlledByType().with({
          label: "",
        }),
      ],
      leftYAxis: {
        label: "Controlled RDS Instances",
        showUnits: false,
        min: 0,
      },
      legendPosition: LegendPosition.BOTTOM,
    });
  }
}

export class RunningRDSInstancesByTypeLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Running RDS Instances By Type",
      width: props.width,
      height: props.height,
      left: [
        metrics.RdsInstancesRunningByType().with({
          label: "",
        }),
      ],
      leftYAxis: {
        showUnits: false,
        min: 0,
      },
      legendPosition: LegendPosition.BOTTOM,
    });
  }
}

export class ControlledRdsInstancesByScheduleLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Controlled RDS Instances By Schedule",
      width: props.width,
      height: props.height,
      left: [
        metrics.RdsInstancesControlledBySchedule().with({
          label: "",
        }),
      ],
      leftYAxis: {
        label: "Controlled RDS Instances",
        showUnits: false,
        min: 0,
      },
      legendPosition: LegendPosition.BOTTOM,
    });
  }
}

export class RunningRdsInstancesByScheduleLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Running RDS Instances by Schedule",
      width: props.width,
      height: props.height,
      left: [
        metrics.RdsInstancesRunningBySchedule().with({
          label: "",
        }),
      ],
      leftYAxis: {
        label: "Running RDS Instances",
        showUnits: false,
        min: 0,
      },
      legendPosition: LegendPosition.BOTTOM,
    });
  }
}

export class LambdaErrorRateLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Lambda Errors",
      width: props.width,
      height: props.height,
      view: GraphWidgetView.TIME_SERIES,
      period: Duration.minutes(30),
      liveData: true,
      left: [
        metrics.OrchestratorLambdaErrors().with({
          label: "Orchestrator",
        }),
        metrics.SchedulingRequestHandlerLambdaErrors().with({
          label: "SchedulingRequestHandler",
        }),
      ],
      leftYAxis: {
        label: "Errors",
        showUnits: false,
      },
      legendPosition: LegendPosition.BOTTOM,
      statistic: Stats.SUM,
    });
  }
}

export class LambdaDurationLineChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Lambda Duration (P99)",
      width: props.width,
      height: props.height,
      view: GraphWidgetView.TIME_SERIES,
      period: Duration.minutes(30),
      liveData: true,
      left: [
        metrics.OrchestratorLambdaDuration().with({
          label: "Orchestrator",
          color: Color.PINK,
          statistic: Stats.MAXIMUM,
        }),
        metrics.SchedulingRequestHandlerLambdaDuration().with({
          label: "SchedulingRequestHandler(Avg)",
          color: Color.BLUE,
          statistic: Stats.AVERAGE,
        }),
        metrics.SchedulingRequestHandlerLambdaDuration().with({
          label: "SchedulingRequestHandler(Max)",
          color: Color.PURPLE,
          statistic: Stats.MAXIMUM,
        }),
      ],
      leftYAxis: {
        label: "duration (ms)",
        showUnits: false,
      },
      leftAnnotations: [
        // lambda times out after 5 minutes, runtime < 3 mins is healthy, 4 mins iffy, close to 5 is a warning
        {
          value: 5 * 60 * 1000,
          fill: Shading.BELOW,
          color: Color.RED,
          label: "Timeout Threshold (Scheduling will error above this line)",
        },
        {
          value: 4 * 60 * 1000,
          fill: Shading.BELOW,
          color: Color.ORANGE,
          label: "Peak warning -- consider increasing lambda size or scheduling regions with less latency",
        },
        {
          value: 3 * 60 * 1000,
          fill: Shading.BELOW,
          color: Color.GREEN,
          label: "Acceptable infrequent peaks below this line",
        },
        {
          value: 90 * 1000,
          fill: Shading.BELOW,
          color: Color.GREEN,
          label: "Average runtime should stay below this line",
        },
      ],
      legendPosition: LegendPosition.BOTTOM,
    });
  }
}
