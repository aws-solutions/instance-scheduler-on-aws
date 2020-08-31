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

import * as cdk from '@aws-cdk/core';
import * as kms from '@aws-cdk/aws-kms';
import * as iam from '@aws-cdk/aws-iam';
import * as logs from '@aws-cdk/aws-logs';
import * as lambda from '@aws-cdk/aws-lambda';
import * as s3 from '@aws-cdk/aws-s3';
import * as sns from '@aws-cdk/aws-sns';
import * as events from '@aws-cdk/aws-events';
import { ArnPrincipal, Effect, PolicyStatement } from '@aws-cdk/aws-iam';
import { LambdaToDynamoDBProps, LambdaToDynamoDB } from '@aws-solutions-constructs/aws-lambda-dynamodb';
import * as EventlambdaConstruct from '@aws-solutions-constructs/aws-events-rule-lambda';
import * as dynamodb from '@aws-cdk/aws-dynamodb';
import { Aws, RemovalPolicy } from '@aws-cdk/core';

/*
* AWS instance scheduler stack, utilizes two cdk constructs, aws-lambda-dynamodb and aws-events-rule-lambda.
* The stack has three dynamoDB tables defined for storing the state, configuration and maintenance information.
* The stack also includes one lambda, which is scheduled using a AWS CloudWatch Event Rule. 
* The stack also includes a cloudwatch log group for the entire solution, encrycption key, encyrption key alias and SNS topic,
* and the necessary AWS IAM Policies and IAM Roles. For more information on the architecture, refer to the documentation at
* https://aws.amazon.com/solutions/implementations/instance-scheduler/?did=sl_card&trk=sl_card
*/
export class AwsInstanceSchedulerStack extends cdk.Stack {

  constructor(scope: cdk.Construct, id: string, props?: any) {
    super(scope, id, props);

    //Start CFN Parameters for instance scheduler.

    const schedulingActive = new cdk.CfnParameter(this, 'SchedulingActive', {
      description: 'Activate or deactivate scheduling.',
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "Yes"
    });

    const scheduledServices = new cdk.CfnParameter(this, 'ScheduledServices', {
      description: 'Scheduled Services.',
      type: "String",
      allowedValues: ["EC2", "RDS", "Both"],
      default: "EC2"
    });

    const scheduleRdsClusters = new cdk.CfnParameter(this, 'ScheduleRdsClusters', {
      description: 'Enable scheduling of Aurora clusters for RDS Service.',
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "No"
    });

    const createRdsSnapshot = new cdk.CfnParameter(this, 'CreateRdsSnapshot', {
      description: 'Create snapshot before stopping RDS instances(does not apply to Aurora Clusters).',
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "No"
    });

    const memorySize = new cdk.CfnParameter(this, 'MemorySize', {
      description: 'Size of the Lambda function running the scheduler, increase size when processing large numbers of instances.',
      type: "Number",
      allowedValues: ["128", "384", "512", "640", "768", "896", "1024", "1152", "1280", "1408", "1536"],
      default: 128
    });

    const useCloudWatchMetrics = new cdk.CfnParameter(this, 'UseCloudWatchMetrics', {
      description: 'Collect instance scheduling data using CloudWatch metrics.',
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "No"
    });

    const logRetention = new cdk.CfnParameter(this, 'LogRetentionDays', {
      description: 'Retention days for scheduler logs.',
      type: "Number",
      allowedValues: ["1", "3", "5", "7", "14", "14", "30", "60", "90", "120", "150", "180", "365", "400", "545", "731", "1827", "3653"],
      default: 30
    });

    const trace = new cdk.CfnParameter(this, 'Trace', {
      description: 'Enable logging of detailed informtion in CloudWatch logs.',
      type: 'String',
      allowedValues: ["Yes", "No"],
      default: "No"
    });

    const tagName = new cdk.CfnParameter(this, 'TagName', {
      description: 'Name of tag to use for associating instance schedule schemas with service instances.',
      type: 'String',
      default: "Schedule",
      minLength: 1,
      maxLength: 127
    });

    const defaultTimezone = new cdk.CfnParameter(this, 'DefaultTimezone', {
      description: 'Choose the default Time Zone. Default is \'UTC\'',
      type: 'String',
      default: 'UTC',
      allowedValues: [
        "Africa/Abidjan",
        "Africa/Accra",
        "Africa/Addis_Ababa",
        "Africa/Algiers",
        "Africa/Asmara",
        "Africa/Bamako",
        "Africa/Bangui",
        "Africa/Banjul",
        "Africa/Bissau",
        "Africa/Blantyre",
        "Africa/Brazzaville",
        "Africa/Bujumbura",
        "Africa/Cairo",
        "Africa/Casablanca",
        "Africa/Ceuta",
        "Africa/Conakry",
        "Africa/Dakar",
        "Africa/Dar_es_Salaam",
        "Africa/Djibouti",
        "Africa/Douala",
        "Africa/El_Aaiun",
        "Africa/Freetown",
        "Africa/Gaborone",
        "Africa/Harare",
        "Africa/Johannesburg",
        "Africa/Juba",
        "Africa/Kampala",
        "Africa/Khartoum",
        "Africa/Kigali",
        "Africa/Kinshasa",
        "Africa/Lagos",
        "Africa/Libreville",
        "Africa/Lome",
        "Africa/Luanda",
        "Africa/Lubumbashi",
        "Africa/Lusaka",
        "Africa/Malabo",
        "Africa/Maputo",
        "Africa/Maseru",
        "Africa/Mbabane",
        "Africa/Mogadishu",
        "Africa/Monrovia",
        "Africa/Nairobi",
        "Africa/Ndjamena",
        "Africa/Niamey",
        "Africa/Nouakchott",
        "Africa/Ouagadougou",
        "Africa/Porto-Novo",
        "Africa/Sao_Tome",
        "Africa/Tripoli",
        "Africa/Tunis",
        "Africa/Windhoek",
        "America/Adak",
        "America/Anchorage",
        "America/Anguilla",
        "America/Antigua",
        "America/Araguaina",
        "America/Argentina/Buenos_Aires",
        "America/Argentina/Catamarca",
        "America/Argentina/Cordoba",
        "America/Argentina/Jujuy",
        "America/Argentina/La_Rioja",
        "America/Argentina/Mendoza",
        "America/Argentina/Rio_Gallegos",
        "America/Argentina/Salta",
        "America/Argentina/San_Juan",
        "America/Argentina/San_Luis",
        "America/Argentina/Tucuman",
        "America/Argentina/Ushuaia",
        "America/Aruba",
        "America/Asuncion",
        "America/Atikokan",
        "America/Bahia",
        "America/Bahia_Banderas",
        "America/Barbados",
        "America/Belem",
        "America/Belize",
        "America/Blanc-Sablon",
        "America/Boa_Vista",
        "America/Bogota",
        "America/Boise",
        "America/Cambridge_Bay",
        "America/Campo_Grande",
        "America/Cancun",
        "America/Caracas",
        "America/Cayenne",
        "America/Cayman",
        "America/Chicago",
        "America/Chihuahua",
        "America/Costa_Rica",
        "America/Creston",
        "America/Cuiaba",
        "America/Curacao",
        "America/Danmarkshavn",
        "America/Dawson",
        "America/Dawson_Creek",
        "America/Denver",
        "America/Detroit",
        "America/Dominica",
        "America/Edmonton",
        "America/Eirunepe",
        "America/El_Salvador",
        "America/Fortaleza",
        "America/Glace_Bay",
        "America/Godthab",
        "America/Goose_Bay",
        "America/Grand_Turk",
        "America/Grenada",
        "America/Guadeloupe",
        "America/Guatemala",
        "America/Guayaquil",
        "America/Guyana",
        "America/Halifax",
        "America/Havana",
        "America/Hermosillo",
        "America/Indiana/Indianapolis",
        "America/Indiana/Knox",
        "America/Indiana/Marengo",
        "America/Indiana/Petersburg",
        "America/Indiana/Tell_City",
        "America/Indiana/Vevay",
        "America/Indiana/Vincennes",
        "America/Indiana/Winamac",
        "America/Inuvik",
        "America/Iqaluit",
        "America/Jamaica",
        "America/Juneau",
        "America/Kentucky/Louisville",
        "America/Kentucky/Monticello",
        "America/Kralendijk",
        "America/La_Paz",
        "America/Lima",
        "America/Los_Angeles",
        "America/Lower_Princes",
        "America/Maceio",
        "America/Managua",
        "America/Manaus",
        "America/Marigot",
        "America/Martinique",
        "America/Matamoros",
        "America/Mazatlan",
        "America/Menominee",
        "America/Merida",
        "America/Metlakatla",
        "America/Mexico_City",
        "America/Miquelon",
        "America/Moncton",
        "America/Monterrey",
        "America/Montevideo",
        "America/Montreal",
        "America/Montserrat",
        "America/Nassau",
        "America/New_York",
        "America/Nipigon",
        "America/Nome",
        "America/Noronha",
        "America/North_Dakota/Beulah",
        "America/North_Dakota/Center",
        "America/North_Dakota/New_Salem",
        "America/Ojinaga",
        "America/Panama",
        "America/Pangnirtung",
        "America/Paramaribo",
        "America/Phoenix",
        "America/Port-au-Prince",
        "America/Port_of_Spain",
        "America/Porto_Velho",
        "America/Puerto_Rico",
        "America/Rainy_River",
        "America/Rankin_Inlet",
        "America/Recife",
        "America/Regina",
        "America/Resolute",
        "America/Rio_Branco",
        "America/Santa_Isabel",
        "America/Santarem",
        "America/Santiago",
        "America/Santo_Domingo",
        "America/Sao_Paulo",
        "America/Scoresbysund",
        "America/Sitka",
        "America/St_Barthelemy",
        "America/St_Johns",
        "America/St_Kitts",
        "America/St_Lucia",
        "America/St_Thomas",
        "America/St_Vincent",
        "America/Swift_Current",
        "America/Tegucigalpa",
        "America/Thule",
        "America/Thunder_Bay",
        "America/Tijuana",
        "America/Toronto",
        "America/Tortola",
        "America/Vancouver",
        "America/Whitehorse",
        "America/Winnipeg",
        "America/Yakutat",
        "America/Yellowknife",
        "Antarctica/Casey",
        "Antarctica/Davis",
        "Antarctica/DumontDUrville",
        "Antarctica/Macquarie",
        "Antarctica/Mawson",
        "Antarctica/McMurdo",
        "Antarctica/Palmer",
        "Antarctica/Rothera",
        "Antarctica/Syowa",
        "Antarctica/Vostok",
        "Arctic/Longyearbyen",
        "Asia/Aden",
        "Asia/Almaty",
        "Asia/Amman",
        "Asia/Anadyr",
        "Asia/Aqtau",
        "Asia/Aqtobe",
        "Asia/Ashgabat",
        "Asia/Baghdad",
        "Asia/Bahrain",
        "Asia/Baku",
        "Asia/Bangkok",
        "Asia/Beirut",
        "Asia/Bishkek",
        "Asia/Brunei",
        "Asia/Choibalsan",
        "Asia/Chongqing",
        "Asia/Colombo",
        "Asia/Damascus",
        "Asia/Dhaka",
        "Asia/Dili",
        "Asia/Dubai",
        "Asia/Dushanbe",
        "Asia/Gaza",
        "Asia/Harbin",
        "Asia/Hebron",
        "Asia/Ho_Chi_Minh",
        "Asia/Hong_Kong",
        "Asia/Hovd",
        "Asia/Irkutsk",
        "Asia/Jakarta",
        "Asia/Jayapura",
        "Asia/Jerusalem",
        "Asia/Kabul",
        "Asia/Kamchatka",
        "Asia/Karachi",
        "Asia/Kashgar",
        "Asia/Kathmandu",
        "Asia/Khandyga",
        "Asia/Kolkata",
        "Asia/Krasnoyarsk",
        "Asia/Kuala_Lumpur",
        "Asia/Kuching",
        "Asia/Kuwait",
        "Asia/Macau",
        "Asia/Magadan",
        "Asia/Makassar",
        "Asia/Manila",
        "Asia/Muscat",
        "Asia/Nicosia",
        "Asia/Novokuznetsk",
        "Asia/Novosibirsk",
        "Asia/Omsk",
        "Asia/Oral",
        "Asia/Phnom_Penh",
        "Asia/Pontianak",
        "Asia/Pyongyang",
        "Asia/Qatar",
        "Asia/Qyzylorda",
        "Asia/Rangoon",
        "Asia/Riyadh",
        "Asia/Sakhalin",
        "Asia/Samarkand",
        "Asia/Seoul",
        "Asia/Shanghai",
        "Asia/Singapore",
        "Asia/Taipei",
        "Asia/Tashkent",
        "Asia/Tbilisi",
        "Asia/Tehran",
        "Asia/Thimphu",
        "Asia/Tokyo",
        "Asia/Ulaanbaatar",
        "Asia/Urumqi",
        "Asia/Ust-Nera",
        "Asia/Vientiane",
        "Asia/Vladivostok",
        "Asia/Yakutsk",
        "Asia/Yekaterinburg",
        "Asia/Yerevan",
        "Atlantic/Azores",
        "Atlantic/Bermuda",
        "Atlantic/Canary",
        "Atlantic/Cape_Verde",
        "Atlantic/Faroe",
        "Atlantic/Madeira",
        "Atlantic/Reykjavik",
        "Atlantic/South_Georgia",
        "Atlantic/St_Helena",
        "Atlantic/Stanley",
        "Australia/Adelaide",
        "Australia/Brisbane",
        "Australia/Broken_Hill",
        "Australia/Currie",
        "Australia/Darwin",
        "Australia/Eucla",
        "Australia/Hobart",
        "Australia/Lindeman",
        "Australia/Lord_Howe",
        "Australia/Melbourne",
        "Australia/Perth",
        "Australia/Sydney",
        "Canada/Atlantic",
        "Canada/Central",
        "Canada/Eastern",
        "Canada/Mountain",
        "Canada/Newfoundland",
        "Canada/Pacific",
        "Europe/Amsterdam",
        "Europe/Andorra",
        "Europe/Athens",
        "Europe/Belgrade",
        "Europe/Berlin",
        "Europe/Bratislava",
        "Europe/Brussels",
        "Europe/Bucharest",
        "Europe/Budapest",
        "Europe/Busingen",
        "Europe/Chisinau",
        "Europe/Copenhagen",
        "Europe/Dublin",
        "Europe/Gibraltar",
        "Europe/Guernsey",
        "Europe/Helsinki",
        "Europe/Isle_of_Man",
        "Europe/Istanbul",
        "Europe/Jersey",
        "Europe/Kaliningrad",
        "Europe/Kiev",
        "Europe/Lisbon",
        "Europe/Ljubljana",
        "Europe/London",
        "Europe/Luxembourg",
        "Europe/Madrid",
        "Europe/Malta",
        "Europe/Mariehamn",
        "Europe/Minsk",
        "Europe/Monaco",
        "Europe/Moscow",
        "Europe/Oslo",
        "Europe/Paris",
        "Europe/Podgorica",
        "Europe/Prague",
        "Europe/Riga",
        "Europe/Rome",
        "Europe/Samara",
        "Europe/San_Marino",
        "Europe/Sarajevo",
        "Europe/Simferopol",
        "Europe/Skopje",
        "Europe/Sofia",
        "Europe/Stockholm",
        "Europe/Tallinn",
        "Europe/Tirane",
        "Europe/Uzhgorod",
        "Europe/Vaduz",
        "Europe/Vatican",
        "Europe/Vienna",
        "Europe/Vilnius",
        "Europe/Volgograd",
        "Europe/Warsaw",
        "Europe/Zagreb",
        "Europe/Zaporozhye",
        "Europe/Zurich",
        "GMT",
        "Indian/Antananarivo",
        "Indian/Chagos",
        "Indian/Christmas",
        "Indian/Cocos",
        "Indian/Comoro",
        "Indian/Kerguelen",
        "Indian/Mahe",
        "Indian/Maldives",
        "Indian/Mauritius",
        "Indian/Mayotte",
        "Indian/Reunion",
        "Pacific/Apia",
        "Pacific/Auckland",
        "Pacific/Chatham",
        "Pacific/Chuuk",
        "Pacific/Easter",
        "Pacific/Efate",
        "Pacific/Enderbury",
        "Pacific/Fakaofo",
        "Pacific/Fiji",
        "Pacific/Funafuti",
        "Pacific/Galapagos",
        "Pacific/Gambier",
        "Pacific/Guadalcanal",
        "Pacific/Guam",
        "Pacific/Honolulu",
        "Pacific/Johnston",
        "Pacific/Kiritimati",
        "Pacific/Kosrae",
        "Pacific/Kwajalein",
        "Pacific/Majuro",
        "Pacific/Marquesas",
        "Pacific/Midway",
        "Pacific/Nauru",
        "Pacific/Niue",
        "Pacific/Norfolk",
        "Pacific/Noumea",
        "Pacific/Pago_Pago",
        "Pacific/Palau",
        "Pacific/Pitcairn",
        "Pacific/Pohnpei",
        "Pacific/Port_Moresby",
        "Pacific/Rarotonga",
        "Pacific/Saipan",
        "Pacific/Tahiti",
        "Pacific/Tarawa",
        "Pacific/Tongatapu",
        "Pacific/Wake",
        "Pacific/Wallis",
        "US/Alaska",
        "US/Arizona",
        "US/Central",
        "US/Eastern",
        "US/Hawaii",
        "US/Mountain",
        "US/Pacific",
        "UTC"]
    })

    const regions = new cdk.CfnParameter(this, 'Regions', {
      type: 'CommaDelimitedList',
      description: 'List of regions in which instances are scheduled, leave blank for current region only.'
    })

    const crossAccountRoles = new cdk.CfnParameter(this, 'CrossAccountRoles', {
      type: 'CommaDelimitedList',
      description: 'Comma separated list of ARN\'s for cross account access roles. These roles must be created in all checked accounts the scheduler to start and stop instances.'
    })

    const startedTags = new cdk.CfnParameter(this, 'StartedTags', {
      type: 'String',
      description: 'Comma separated list of tagname and values on the formt name=value,name=value,.. that are set on started instances'
    })

    const stoppedTags = new cdk.CfnParameter(this, 'StoppedTags', {
      type: 'String',
      description: 'Comma separated list of tagname and values on the formt name=value,name=value,.. that are set on stopped instances'
    })

    const schedulerFrequency = new cdk.CfnParameter(this, 'SchedulerFrequency', {
      type: 'String',
      description: 'Scheduler running frequency in minutes.',
      allowedValues: [
        "1",
        "2",
        "5",
        "10",
        "15",
        "30",
        "60"
      ],
      default: "5"
    })

    const scheduleLambdaAccount = new cdk.CfnParameter(this, 'ScheduleLambdaAccount', {
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "Yes",
      description: "Schedule instances in this account."
    })

    const sendAnonymousData = new cdk.CfnParameter(this, 'SendAnonymousData', {
      type: "String",
      allowedValues: ["Yes", "No"],
      default: "Yes",
      description: "Send Anonymous Metrics Data."
    })

    //End CFN parameters for instance scheduler.

    //Start Mappings for instance scheduler. 

    const mappings = new cdk.CfnMapping(this, "mappings")
    mappings.setValue("TrueFalse", "Yes", "True")
    mappings.setValue("TrueFalse", "No", "False")
    mappings.setValue("EnabledDisabled", "Yes", "ENABLED")
    mappings.setValue("EnabledDisabled", "No", "DISABLED")
    mappings.setValue("Services", "EC2", "ec2")
    mappings.setValue("Services", "RDS", "rds")
    mappings.setValue("Services", "Both", "ec2,rds")
    mappings.setValue("Timeouts", "1", "cron(0/1 * * * ? *)")
    mappings.setValue("Timeouts", "2", "cron(0/2 * * * ? *)")
    mappings.setValue("Timeouts", "5", "cron(0/5 * * * ? *)")
    mappings.setValue("Timeouts", "10", "cron(0/10 * * * ? *)")
    mappings.setValue("Timeouts", "15", "cron(0/15 * * * ? *)")
    mappings.setValue("Timeouts", "30", "cron(0/30 * * * ? *)")
    mappings.setValue("Timeouts", "60", "cron(0/1 * * ? *)")
    mappings.setValue("Settings", "MetricsUrl", "https://metrics.awssolutionsbuilder.com/generic")
    mappings.setValue("Settings", "MetricsSolutionId", "S00030")

    //End Mappings for instance scheduler.

    /*
    * Instance Scheduler solutions bucket reference.  
    */
    const solutionsBucket = s3.Bucket.fromBucketAttributes(this, 'SolutionsBucket', {
      bucketName: props["solutionBucket"] + '-' + this.region
    });

    /*
    * Instance Scheduler solutions log group reference.
    */
    const schedulerLogGroup = new logs.LogGroup(this, 'SchedulerLogGroup', {
      logGroupName: Aws.STACK_NAME + '-logs',
      removalPolicy: RemovalPolicy.DESTROY
    });

    const schedulerLogGroup_ref = schedulerLogGroup.node.defaultChild as logs.CfnLogGroup
    schedulerLogGroup_ref.addPropertyOverride('RetentionInDays', logRetention.valueAsNumber)

    //Start instance scheduler scheduler role reference and related references of principle, policy statement, and policy document.
    const compositePrincipal = new iam.CompositePrincipal(new iam.ServicePrincipal('events.amazonaws.com'), new iam.ServicePrincipal('lambda.amazonaws.com'))

    const schedulerRole = new iam.Role(this, "SchedulerRole", {
      assumedBy: compositePrincipal,
      path: '/'
    })

    //End instance scheduler scheduler role reference

    //Start instance scheduler encryption key and encryption key alias.
    const instanceSchedulerEncryptionKey = new kms.Key(this, "InstanceSchedulerEncryptionKey", {
      description: 'Key for SNS',
      enabled: true,
      enableKeyRotation: true,
      policy: new iam.PolicyDocument({
        statements: [
          new iam.PolicyStatement({
            actions: ["kms:*"],
            effect: Effect.ALLOW,
            resources: ['*'],
            principals: [new ArnPrincipal("arn:" + this.partition + ":iam::" + this.account + ":root")],
            sid: 'default'
          }),
          new iam.PolicyStatement({
            sid: 'Allows use of key',
            effect: Effect.ALLOW,
            actions: [
              'kms:GenerateDataKey*',
              'kms:Decrypt'
            ],
            resources: ['*'],
            principals: [new ArnPrincipal(schedulerRole.roleArn)]
          })
        ]
      }),
      removalPolicy: RemovalPolicy.DESTROY
    })

    const keyAlias = new kms.Alias(this, "InstanceSchedulerEncryptionKeyAlias", {
      aliasName: "alias/instance-scheduler-encryption-key",
      targetKey: instanceSchedulerEncryptionKey
    })
    //End instance scheduler encryption key and encryption key alias.

    /*
    * Instance scheduler SNS Topic reference. 
    */
    const snsTopic = new sns.Topic(this, 'InstanceSchedulerSnsTopic', {
      displayName: Aws.STACK_NAME,
      masterKey: instanceSchedulerEncryptionKey
    });

    //Instance scheduler, AWS Event scheduler rule name.
    const schedulerRuleName: string = props["solutionName"] + 'scheduling_rule'

    //Start instance scheduler aws-lambda-dynamoDB construct reference. 
    const lambdaToDynamoDBProps: LambdaToDynamoDBProps = {
      lambdaFunctionProps: {
        functionName: Aws.STACK_NAME + '-InstanceSchedulerMain',
        description: 'EC2 and RDS instance scheduler, version ' + props["solutionVersion"],
        code: lambda.Code.fromBucket(solutionsBucket, props["solutionTradeMarkName"] + '/' + props["solutionVersion"] + '/instance-scheduler.zip'),
        runtime: lambda.Runtime.PYTHON_3_7,
        handler: 'main.lambda_handler',
        role: schedulerRole,
        memorySize: memorySize.valueAsNumber,
        timeout: cdk.Duration.seconds(300),
        environment: {
          SCHEDULER_FREQUENCY: schedulerFrequency.valueAsString,
          TAG_NAME: tagName.valueAsString,
          LOG_GROUP: schedulerLogGroup.logGroupName,
          ACCOUNT: this.account,
          ISSUES_TOPIC_ARN: snsTopic.topicArn,
          STACK_NAME: Aws.STACK_NAME,
          BOTO_RETRY: '5,10,30,0.25',
          ENV_BOTO_RETRY_LOGGING: "FALSE",
          SEND_METRICS: mappings.findInMap('TrueFalse', sendAnonymousData.valueAsString),
          SOLUTION_ID: mappings.findInMap('Settings', 'MetricsSolutionId'),
          TRACE: mappings.findInMap('TrueFalse', trace.valueAsString),
          USER_AGENT: 'InstanceScheduler-' + Aws.STACK_NAME + '-' + props["solutionVersion"],
          METRICS_URL: mappings.findInMap('Settings', 'MetricsUrl'),
          SCHEDULER_RULE: schedulerRuleName
        }
      },
      dynamoTableProps: {
        partitionKey: {
          name: 'service',
          type: dynamodb.AttributeType.STRING
        },
        sortKey: {
          name: 'account-region',
          type: dynamodb.AttributeType.STRING
        },
        billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
        removalPolicy: RemovalPolicy.DESTROY
      },
      tablePermissions: "ReadWrite",

    };

    const lambdaToDynamoDb = new LambdaToDynamoDB(this, 'instance-scheduler-lambda', lambdaToDynamoDBProps);

    const cfnStateTable = lambdaToDynamoDb.dynamoTable.node.defaultChild as dynamodb.CfnTable
    cfnStateTable.overrideLogicalId('StateTable')
    cfnStateTable.addPropertyOverride("SSESpecification", {
      "KMSMasterKeyId": { "Ref": "InstanceSchedulerEncryptionKey" },
      "SSEEnabled": true,
      "SSEType": 'KMS'
    })

    //End instance scheduler aws-lambda-dynamoDB construct reference. 

    //Start instance scheduler configuration table dynamoDB Table reference.

    const configTable = new dynamodb.Table(this, 'ConfigTable', {
      sortKey: {
        name: 'name',
        type: dynamodb.AttributeType.STRING
      },
      partitionKey: {
        name: 'type',
        type: dynamodb.AttributeType.STRING
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY
    })

    const cfnConfigTable = configTable.node.defaultChild as dynamodb.CfnTable
    cfnConfigTable.overrideLogicalId('ConfigTable')
    cfnConfigTable.addPropertyOverride("SSESpecification", {
      "KMSMasterKeyId": { "Ref": "InstanceSchedulerEncryptionKey" },
      "SSEEnabled": true,
      "SSEType": 'KMS'
    })

    //End instance scheduler configuration table dynamoDB Table reference.


    //Start instance scheduler maintenance window table dynamoDB Table reference.

    const maintenanceWindowTable = new dynamodb.Table(this, 'MaintenanceWindowTable', {
      partitionKey: {
        name: 'Name',
        type: dynamodb.AttributeType.STRING
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY
    })

    const cfnMaintenanceWindowTable = maintenanceWindowTable.node.defaultChild as dynamodb.CfnTable
    cfnMaintenanceWindowTable.overrideLogicalId('MaintenanceWindowTable')
    cfnMaintenanceWindowTable.addPropertyOverride("SSESpecification", {
      "KMSMasterKeyId": { "Ref": "InstanceSchedulerEncryptionKey" },
      "SSEEnabled": true,
      "SSEType": 'KMS'
    })
    //End instance scheduler maintenance window table dynamoDB Table reference.

    //Adding all the dynamo DB references to the lambda environment variables.
    lambdaToDynamoDb.lambdaFunction.addEnvironment('CONFIG_TABLE', cfnConfigTable.ref)
    lambdaToDynamoDb.lambdaFunction.addEnvironment('MAINTENANCE_WINDOW_TABLE', cfnMaintenanceWindowTable.ref)
    lambdaToDynamoDb.lambdaFunction.addEnvironment('STATE_TABLE', cfnStateTable.ref)

    //Start instance scheduler database policy statement for lambda.

    const dynamodbPolicy = new PolicyStatement({
      actions: [
        'dynamodb:DeleteItem',
        'dynamodb:GetItem',
        'dynamodb:PutItem',
        'dynamodb:Query',
        'dynamodb:Scan',
        'dynamodb:BatchWriteItem'
      ],
      effect: Effect.ALLOW,
      resources: [
        cfnConfigTable.attrArn,
        cfnMaintenanceWindowTable.attrArn
      ]
    })

    lambdaToDynamoDb.lambdaFunction.addToRolePolicy(dynamodbPolicy)

    //End instance scheduler database policy statement for lambda.


    //Start instance scheduler aws-event-lambda construct reference.
    let eventlambdaConstruct = new EventlambdaConstruct.EventsRuleToLambda(this, 'EventlambdaConstruct', {
      eventRuleProps: {
        description: 'Instance Scheduler - Rule to trigger instance for scheduler function version ' + props["solutionVersion"],
        schedule: events.Schedule.expression(mappings.findInMap('Timeouts', schedulerFrequency.valueAsString)),
        ruleName: schedulerRuleName
      },
      existingLambdaObj: lambdaToDynamoDb.lambdaFunction
    })

    const eventRule_cfn_ref = eventlambdaConstruct.eventsRule.node.defaultChild as events.CfnRule
    eventRule_cfn_ref.addPropertyOverride('State', mappings.findInMap('EnabledDisabled', schedulingActive.valueAsString));
    //End instance scheduler aws-event-lambda construct reference.


    /*
    * Instance scheduler custom resource reference.
    */
    let customService = new cdk.CustomResource(this, 'ServiceSetup', {
      serviceToken: lambdaToDynamoDb.lambdaFunction.functionArn,
      resourceType: 'Custom::ServiceSetup',
      properties: {
        timeout: 120,
        config_table: cfnConfigTable.ref,
        tagname: tagName,
        default_timezone: defaultTimezone,
        use_metrics: mappings.findInMap('TrueFalse', useCloudWatchMetrics.valueAsString),
        scheduled_services: cdk.Fn.split(",", mappings.findInMap('Services', scheduledServices.valueAsString)),
        schedule_clusters: mappings.findInMap('TrueFalse', scheduleRdsClusters.valueAsString),
        create_rds_snapshot: mappings.findInMap('TrueFalse', createRdsSnapshot.valueAsString),
        regions: regions,
        cross_account_roles: crossAccountRoles,
        schedule_lambda_account: mappings.findInMap('TrueFalse', scheduleLambdaAccount.valueAsString),
        trace: mappings.findInMap('TrueFalse', trace.valueAsString),
        log_retention_days: logRetention.valueAsNumber,
        started_tags: startedTags.valueAsString,
        stopped_tags: stoppedTags.valueAsString,
        stack_version: props["solutionVersion"]
      }
    })

    const customServiceCfn = customService.node.defaultChild as cdk.CfnCustomResource
    customServiceCfn.addDependsOn(schedulerLogGroup_ref)

    //Instance scheduler Cloudformation Output references.
    new cdk.CfnOutput(this, 'AccountId', {
      value: this.account,
      description: 'Account to give access to when creating cross-account access role fro cross account scenario '
    })

    new cdk.CfnOutput(this, 'ConfigurationTable', {
      value: cfnConfigTable.attrArn,
      description: 'Name of the DynamoDB configuration table'
    })

    new cdk.CfnOutput(this, 'IssueSnsTopicArn', {
      value: snsTopic.topicArn,
      description: 'Topic to subscribe to for notifications of errors and warnings'
    })

    new cdk.CfnOutput(this, 'SchedulerRoleArn', {
      value: schedulerRole.roleArn,
      description: 'Role for the instance scheduler lambda function'
    })

    new cdk.CfnOutput(this, 'ServiceInstanceScheduleServiceToken', {
      value: lambdaToDynamoDb.lambdaFunction.functionArn,
      description: 'Arn to use as ServiceToken property for custom resource type Custom::ServiceInstanceSchedule'
    })

    //Instance scheduler ec2 policy statement, policy documents and role references.
    const ec2PolicyStatementForLogs = new PolicyStatement({
      actions: [
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents',
        'logs:PutRetentionPolicy'],
      resources: [
        'arn:aws:logs:' + this.region + ':' + this.account + ':log-group:/aws/lambda/*',
        schedulerLogGroup.logGroupArn
      ],
      effect: Effect.ALLOW
    })

    const ec2PolicyStatementforMisc = new PolicyStatement({
      actions: [
        'logs:DescribeLogStreams',
        'rds:DescribeDBClusters',
        'rds:DescribeDBInstances',
        'ec2:DescribeInstances',
        'ec2:DescribeRegions',
        'ec2:ModifyInstanceAttribute',
        'cloudwatch:PutMetricData',
        'ssm:DescribeMaintenanceWindows',
        'tag:GetResources'],
      effect: Effect.ALLOW,
      resources: ['*']
    })

    const ec2PolicyAssumeRoleStatement = new PolicyStatement({
      actions: ['sts:AssumeRole'],
      resources: ['arn:aws:iam::*:role/*EC2SchedulerCross*'],
      effect: Effect.ALLOW
    })

    const ec2PolicySSMStatement = new PolicyStatement({
      actions: [
        'ssm:GetParameter',
        'ssm:GetParameters'
      ],
      resources: ['arn:aws:ssm:*:' + this.account + ':parameter/*'],
      effect: Effect.ALLOW
    })

    const ec2DynamoDBPolicy = new iam.Policy(this, "EC2DynamoDBPolicy", {
      roles: [schedulerRole],
      policyName: 'EC2DynamoDBPolicy',
      statements: [ec2PolicyAssumeRoleStatement, ec2PolicySSMStatement, ec2PolicyStatementforMisc, ec2PolicyStatementForLogs
      ]
    })

    //Instance scheduler, scheduling policy statement, policy documents and role references.
    const schedulerPolicyStatement1 = new PolicyStatement({
      actions: [
        'rds:DeleteDBSnapshot',
        'rds:DescribeDBSnapshots',
        'rds:StopDBInstance'],
      effect: Effect.ALLOW,
      resources: ['arn:aws:rds:*:' + this.account + ':snapshot:*']
    })

    const schedulerPolicyStatement2 = new PolicyStatement({
      actions: [
        'rds:AddTagsToResource',
        'rds:RemoveTagsFromResource',
        'rds:DescribeDBSnapshots',
        'rds:StartDBInstance',
        'rds:StopDBInstance'],
      effect: Effect.ALLOW,
      resources: ['arn:aws:rds:*:' + this.account + ':db:*']
    })

    const schedulerPolicyStatement3 = new PolicyStatement({
      actions: [
        'ec2:StartInstances',
        'ec2:StopInstances',
        'ec2:CreateTags',
        'ec2:DeleteTags'],
      effect: Effect.ALLOW,
      resources: ['arn:aws:ec2:*:' + this.account + ':instance/*']
    })

    const schedulerPolicyStatement4 = new PolicyStatement({
      actions: ['sns:Publish'],
      effect: Effect.ALLOW,
      resources: [snsTopic.topicArn]
    })

    const schedulerPolicyStatement5 = new PolicyStatement({
      actions: ['lambda:InvokeFunction'],
      effect: Effect.ALLOW,
      resources: ['arn:aws:lambda:' + this.region + ':' + this.account + ':function:' + Aws.STACK_NAME + '-InstanceSchedulerMain']
    })

    const schedulerPolicyStatement6 = new PolicyStatement({
      actions: [
        'kms:GenerateDataKey*',
        'kms:Decrypt'
      ],
      effect: Effect.ALLOW,
      resources: [instanceSchedulerEncryptionKey.keyArn]
    })

    const schedulerPolicyStatement7 = new PolicyStatement({
      actions: [
        'rds:AddTagsToResource',
        'rds:RemoveTagsFromResource',
        'rds:StartDBCluster',
        'rds:StopDBCluster'
      ],
      effect: Effect.ALLOW,
      resources: ['arn:aws:rds:*:' + this.account + ':cluster:*']
    })

    const schedulerPolicy = new iam.Policy(this, "SchedulerPolicy", {
      roles: [schedulerRole],
      policyName: 'SchedulerPolicy',
      statements: [schedulerPolicyStatement1, schedulerPolicyStatement2, schedulerPolicyStatement3, schedulerPolicyStatement4, schedulerPolicyStatement5, schedulerPolicyStatement6, schedulerPolicyStatement7]
    })

    //Adding the EC2 and scheduling policy dependencies to the lambda. 
    const lambdaFunction = lambdaToDynamoDb.lambdaFunction.node.defaultChild as lambda.CfnFunction
    lambdaFunction.addDependsOn(ec2DynamoDBPolicy.node.defaultChild as iam.CfnPolicy)
    lambdaFunction.addDependsOn(schedulerPolicy.node.defaultChild as iam.CfnPolicy)

    //Cloud Formation cfn references for ensuring the resource names are similar to earlier releases, and additional metadata for the cfn nag rules.
    const instanceSchedulerEncryptionKey_cfn_ref = instanceSchedulerEncryptionKey.node.defaultChild as kms.CfnKey
    instanceSchedulerEncryptionKey_cfn_ref.overrideLogicalId('InstanceSchedulerEncryptionKey')

    const keyAlias_cfn_ref = keyAlias.node.defaultChild as kms.CfnAlias
    keyAlias_cfn_ref.overrideLogicalId('InstanceSchedulerEncryptionKeyAlias')

    const ec2DynamoDBPolicy_cfn_ref = ec2DynamoDBPolicy.node.defaultChild as iam.CfnPolicy
    ec2DynamoDBPolicy_cfn_ref.overrideLogicalId('EC2DynamoDBPolicy')

    ec2DynamoDBPolicy_cfn_ref.cfnOptions.metadata = {
      "cfn_nag": {
        "rules_to_suppress": [
          {
            "id": "W12",
            "reason": "All policies have been scoped to be as restrictive as possible. This solution needs to access ec2/rds resources across all regions."
          }
        ]
      }
    }

    const schedulerPolicy_cfn_Ref = schedulerPolicy.node.defaultChild as iam.CfnPolicy
    schedulerPolicy_cfn_Ref.overrideLogicalId('SchedulerPolicy')

    const schedulerRole_cfn_ref = schedulerRole.node.defaultChild as iam.CfnRole
    schedulerRole_cfn_ref.overrideLogicalId('SchedulerRole')

    schedulerLogGroup_ref.overrideLogicalId('SchedulerLogGroup')

    const snsTopic_cfn_ref = snsTopic.node.defaultChild as sns.CfnTopic
    snsTopic_cfn_ref.overrideLogicalId('InstanceSchedulerSnsTopic')

    lambdaFunction.overrideLogicalId('Main')

    const rule_cfn_ref = eventlambdaConstruct.eventsRule.node.defaultChild as events.CfnRule
    rule_cfn_ref.overrideLogicalId('SchedulerRule')

    customServiceCfn.overrideLogicalId('SchedulerConfigHelper')

    const stack = cdk.Stack.of(this);

    stack.templateOptions.metadata =
    {
      "AWS::CloudFormation::Interface": {
        "ParameterGroups": [
          {
            "Label": {
              "default": "Scheduler (version " + props['solutionVersion'] + ")"
            },
            "Parameters": [
              "TagName",
              "ScheduledServices",
              "ScheduleRdsClusters",
              "CreateRdsSnapshot",
              "SchedulingActive",
              "Regions",
              "DefaultTimezone",
              "CrossAccountRoles",
              "ScheduleLambdaAccount",
              "SchedulerFrequency",
              "MemorySize"
            ]
          },
          {
            "Label": {
              "default": "Options"
            },
            "Parameters": [
              "UseCloudWatchMetrics",
              "SendAnonymousData",
              "Trace"
            ]
          },
          {
            "Label": {
              "default": "Other parameters"
            },
            "Parameters": [
              "LogRetentionDays",
              "StartedTags",
              "StoppedTags"
            ]
          }
        ],
        "ParameterLabels": {
          "LogRetentionDays": {
            "default": "Log retention days"
          },
          "StartedTags": {
            "default": "Started tags"
          },
          "StoppedTags": {
            "default": "Stopped tags"
          },
          "SchedulingActive": {
            "default": "Scheduling enabled"
          },
          "CrossAccountRoles": {
            "default": "Cross-account roles"
          },
          "ScheduleLambdaAccount": {
            "default": "This account"
          },
          "UseCloudWatchMetrics": {
            "default": "Enable CloudWatch Metrics"
          },
          "Trace": {
            "default": "Enable CloudWatch Logs"
          },
          "TagName": {
            "default": "Instance Scheduler tag name"
          },
          "ScheduledServices": {
            "default": "Service(s) to schedule"
          },
          "ScheduleRdsClusters": {
            "default": "Schedule Aurora Clusters"
          },
          "CreateRdsSnapshot": {
            "default": "Create RDS instance snapshot"
          },
          "DefaultTimezone": {
            "default": "Default time zone"
          },
          "SchedulerFrequency": {
            "default": "Frequency"
          },
          "Regions": {
            "default": "Region(s)"
          },
          "MemorySize": {
            "default": "Memory size"
          },
          "SendAnonymousData": {
            "default": "Send anonymous usage data"
          }
        }
      }
    }
    stack.templateOptions.templateFormatVersion = "2010-09-09"

  }
}