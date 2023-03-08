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

 import {Template} from 'aws-cdk-lib/assertions';
 import {createHubStack} from './instance-scheduler-stack-factory';

 /*
  * SnapShot Testing for the AwsInstanceSchedulerStack.
  */
 test('AwsInstanceSchedulerStack snapshot test', () => {
   let hubStackJson = Template.fromStack(createHubStack()).toJSON()
   hubStackJson.Resources.Main.Properties.Code = "Omitted to remove snapshot dependency on code hash"
   expect(hubStackJson).toMatchSnapshot();
 });
