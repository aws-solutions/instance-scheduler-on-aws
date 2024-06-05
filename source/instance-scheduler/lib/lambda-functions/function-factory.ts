// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import { Duration } from "aws-cdk-lib";
import { IRole } from "aws-cdk-lib/aws-iam";
import { Code, Function as LambdaFunction, Runtime, Tracing } from "aws-cdk-lib/aws-lambda";
import { ILogGroup } from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";
import path from "path";

export interface FunctionProps {
  readonly functionName?: string;
  readonly description: string;
  readonly index: string;
  readonly handler: string;
  readonly role: IRole;
  readonly memorySize: number;
  readonly timeout: Duration;
  readonly logGroup?: ILogGroup;
  environment: { [_: string]: string };
}

export abstract class FunctionFactory {
  abstract createFunction(scope: Construct, id: string, props: FunctionProps): LambdaFunction;
}

export class PythonFunctionFactory extends FunctionFactory {
  override createFunction(scope: Construct, id: string, props: FunctionProps): LambdaFunction {
    return new PythonFunction(scope, id, {
      functionName: props.functionName,
      description: props.description,
      entry: path.join(__dirname, "..", "..", "..", "app"),
      index: props.index,
      handler: props.handler,
      runtime: Runtime.PYTHON_3_11,
      role: props.role,
      memorySize: props.memorySize,
      timeout: props.timeout,
      logGroup: props.logGroup,
      environment: props.environment,
      tracing: Tracing.ACTIVE,
      bundling: { assetExcludes: [".mypy_cache", ".tox", "__pycache__", "tests"] },
    });
  }
}

export class TestFunctionFactory extends FunctionFactory {
  override createFunction(scope: Construct, id: string, props: FunctionProps): LambdaFunction {
    return new LambdaFunction(scope, id, {
      code: Code.fromAsset(path.join(__dirname, "..", "..", "tests", "test_function")),
      runtime: Runtime.PYTHON_3_11,
      functionName: props.functionName,
      description: props.description,
      handler: props.handler,
      role: props.role,
      memorySize: props.memorySize,
      timeout: props.timeout,
      logGroup: props.logGroup,
      environment: props.environment,
      tracing: Tracing.ACTIVE,
    });
  }
}
