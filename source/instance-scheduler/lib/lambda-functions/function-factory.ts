// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { PythonFunction, PythonFunctionProps } from "@aws-cdk/aws-lambda-python-alpha";
import { Duration } from "aws-cdk-lib";
import { IRole } from "aws-cdk-lib/aws-iam";
import {
  ApplicationLogLevel,
  Code,
  Function as LambdaFunction,
  LoggingFormat,
  Runtime,
  SystemLogLevel,
  Tracing,
} from "aws-cdk-lib/aws-lambda";
import { ILogGroup } from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";
import path from "path";
import { InstanceSchedulerStack } from "../instance-scheduler-stack";
import { cfnConditionToLogLevel } from "../cfn";
import { TargetStack } from "../stack-types";
import { addCfnGuardSuppression } from "../helpers/cfn-guard";

export interface FunctionProps extends Omit<PythonFunctionProps, "entry" | "runtime"> {
  readonly functionName?: string;
  readonly description: string;
  readonly index: string;
  readonly handler: string;
  readonly role: IRole;
  readonly memorySize: number;
  readonly timeout: Duration;
  readonly logGroup?: ILogGroup;
  readonly targetStack?: TargetStack;
  environment: { [_: string]: string };
}

export abstract class FunctionFactory {
  abstract createFunction(scope: Construct, id: string, props: FunctionProps): LambdaFunction;
}

export class PythonFunctionFactory extends FunctionFactory {
  override createFunction(scope: Construct, id: string, props: FunctionProps): LambdaFunction {
    const targetStack = props.targetStack ?? TargetStack.HUB;
    const func = new PythonFunction(scope, id, {
      entry: path.join(__dirname, "..", "..", "..", "app"),
      runtime: Runtime.PYTHON_3_12,
      loggingFormat: LoggingFormat.JSON,
      systemLogLevelV2: SystemLogLevel.INFO,
      applicationLogLevelV2:
        targetStack === TargetStack.REMOTE
          ? ApplicationLogLevel.INFO
          : (cfnConditionToLogLevel(
              InstanceSchedulerStack.sharedConfig.enableDebugLoggingCondition,
            ) as ApplicationLogLevel),
      tracing: Tracing.ACTIVE,
      bundling: { assetExcludes: [".mypy_cache", ".tox", "__pycache__", "tests"] },
      ...props,
      environment: {
        POWERTOOLS_SERVICE_NAME: "instance-scheduler",
        POWERTOOLS_LOG_LEVEL: "INFO",
        ...props.environment,
      },
    });
    addCfnGuardSuppression(func, ["LAMBDA_INSIDE_VPC", "LAMBDA_CONCURRENCY_CHECK"]);
    return func;
  }
}

export class TestFunctionFactory extends FunctionFactory {
  override createFunction(scope: Construct, id: string, props: FunctionProps): LambdaFunction {
    const targetStack = props.targetStack ?? TargetStack.HUB;
    return new LambdaFunction(scope, id, {
      code: Code.fromAsset(path.join(__dirname, "..", "..", "tests", "test_function")),
      runtime: Runtime.PYTHON_3_11,
      loggingFormat: LoggingFormat.JSON,
      systemLogLevelV2: SystemLogLevel.INFO,
      applicationLogLevelV2:
        targetStack === TargetStack.REMOTE
          ? ApplicationLogLevel.INFO
          : (cfnConditionToLogLevel(
              InstanceSchedulerStack.sharedConfig.enableDebugLoggingCondition,
            ) as ApplicationLogLevel),
      tracing: Tracing.ACTIVE,
      bundling: { assetExcludes: [".mypy_cache", ".tox", "__pycache__", "tests"] },
      ...props,
      environment: {
        POWERTOOLS_SERVICE_NAME: "instance-scheduler",
        ...props.environment,
      },
    });
  }
}
