#!/usr/bin/env node
/*****************************************************************************
 *  Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.   *
 *                                                                            *
 *  Licensed under the Apache License, Version 2.0 (the "License"). You may   *
 *  not use this file except in compliance with the License. A copy of the    *
 *  License is located at                                                     *
 *                                                                            *
 *      http://www.apache.org/licenses/LICENSE-2.0                            *
 *                                                                            *
 *  or in the 'license' file accompanying this file. This file is distributed *
 *  on an 'AS IS' BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,        *
 *  express or implied. See the License for the specific language governing   *
 *  permissions and limitations under the License.                            *
 *****************************************************************************/

import * as cdk from 'aws-cdk-lib';
import {Aspects} from "aws-cdk-lib";
import {AwsSolutionsChecks} from "cdk-nag";
import {E2eTestStack} from "../lib/e2e-test-stack";
import PipelineStack from "../lib/pipeline-stack";


const app = new cdk.App();

new PipelineStack(app, 'aws-instance-scheduler-testing-pipeline');

/*
E2eTestStack does not actually need to be built here to work in the pipeline,
but building it here ensures it gets covered by CDK-Nag
 */
new E2eTestStack(app, 'aws-instance-scheduler-end-to-end-testing-resources');

Aspects.of(app).add(new AwsSolutionsChecks({
    verbose: true
}))
