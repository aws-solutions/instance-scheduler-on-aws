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
export class TotalEc2HoursSavedInstancesKPI extends SingleValueWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Total EC2 Hours Saved",
      width: props.width,
      height: props.height,
      metrics: [
        metrics.TotalEc2HoursSaved().with({
          label: "Hours Saved",
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

export class TotalControlledEc2InstancesKPI extends SingleValueWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "Total EC2 Instances Controlled",
      width: props.width,
      height: props.height,
      metrics: [
        metrics.TotalEc2InstancesControlled().with({
          label: "EC2 Instances",
        }),
      ],
      period: Duration.seconds(Token.asNumber(metrics.schedulingIntervalSeconds)),
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

export class ControlledEc2InstancesPieChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "EC2 Instances Controlled",
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

export class ControlledRDSInstancesPieChart extends GraphWidget {
  constructor(metrics: Metrics, props: WidgetProps) {
    super({
      title: "RDS Instances Controlled",
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
        label: "Running EC2 Instances",
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
        label: "Running RDS Instances",
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
        metrics.AsgHandlerLambdaErrors().with({
          label: "AsgHandler",
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
        }),
        metrics.SchedulingRequestHandlerLambdaDuration().with({
          label: "SchedulingRequestHandler",
        }),
        metrics.AsgHandlerLambdaDuration().with({
          label: "AsgHandler",
        }),
      ],
      leftYAxis: {
        label: "duration (ms)",
        showUnits: false,
      },
      leftAnnotations: [
        // lambda times out after 5 minutes, runtime < 3 mins is health, 4 mins iffy, close to 5 is a warning
        {
          value: 5 * 60 * 1000,
          fill: Shading.BELOW,
          color: Color.RED,
          label: "Timeout Threshold (5 minutes)",
        },
        {
          value: 4 * 60 * 1000,
          fill: Shading.BELOW,
          color: Color.ORANGE,
        },
        {
          value: 3 * 60 * 1000,
          fill: Shading.BELOW,
          color: Color.GREEN,
        },
      ],
      legendPosition: LegendPosition.BOTTOM,
      statistic: Stats.p(99),
    });
  }
}
