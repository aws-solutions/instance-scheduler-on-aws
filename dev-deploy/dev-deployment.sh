#!/bin/bash
#=======================================================================================================================
# This script can be used to locally build, test, and deploy the AWS Instance Scheduler code outside of a bamboo pipeline.
# It follows the steps describd in AWS' README.md file as well as basic deployment steps from the corresponding
# Implementation Guide (https://s3.amazonaws.com/solutions-reference/aws-instance-scheduler/latest/instance-scheduler.pdf).
#
# IMPORTANT:
# 1. Run your API Key Retriever before executing this script
# 2. This script currently uses a single KMS::Key resource which prevents you from deploying multiple stacks simultaneously.
#
# Authors: Stratus
#=======================================================================================================================

### Overview
# Set script params
# Build
# Test
# Upload files to S3 for CF Deployment
# Deploy via CF

## Set parameters/inputs for S3 Buckets and Version
globalBucketName="a0050155-instance-scheduler-poc"
regionalBucketName="a0050155-instance-scheduler-poc-us-east-1"
instanceSchedulerName="stratus-scheduler-poc"
version="00007"
stackName="stratus-scheduler-poc-stack"

runStackAction() { 
  stackAction=${1}
  aws cloudformation ${stackAction} --stack-name ${stackName} \
  --template-url https://${globalBucketName}.s3.amazonaws.com/${instanceSchedulerName}/${version}/instance-scheduler.template \
  --parameter \
  ParameterKey=TagName,ParameterValue=stratus-scheduler-poc \
  ParameterKey=ScheduledServices,ParameterValue=All \
  ParameterKey=CreateRdsSnapshot,ParameterValue=Yes \
  ParameterKey=Regions,ParameterValue=us-east-1 \
  ParameterKey=StartedTags,ParameterValue=started_by_stratus_scheduler_service=true \
  ParameterKey=StoppedTags,ParameterValue=stopped_by_stratus_scheduler_service=true \
  ParameterKey=CrossAccountRoles,ParameterValue=n \
  ParameterKey=ScheduleRdsClusters,ParameterValue=Yes \
  --tags Key=Name,Value=stratus-scheduler-poc Key=deployment_guid,Value=c8ca23fc-841f-4f26-bc65-51e0205e7a45 Key=lm_app,Value=stratus-scheduler-poc \
  --profile saml \
  --capabilities CAPABILITY_IAM
}

### BUILD
## Execute build script
cd ../deployment
##./build-s3-dist.sh <bucketname> aws-instance-scheduler <version>
./build-s3-dist.sh ${globalBucketName} ${instanceSchedulerName} ${version}

## TEST
## Run Unit Tests script (from deployment directory)
./run-unit-tests.sh
if [ $? == 0 ]; then
  echo "Unit Tests Succeeded"
else
  echo "Failure exit status: $?"
  exit $?
fi

## UPLOAD
echo "Uploading to S3 Buckets"
aws s3 cp global-s3-assets/aws-instance-scheduler-remote.template s3://${globalBucketName}/${instanceSchedulerName}/${version}/instance-scheduler-remote.template --profile saml
aws s3 cp global-s3-assets/aws-instance-scheduler.template s3://${globalBucketName}/${instanceSchedulerName}/${version}/instance-scheduler.template --profile saml
aws s3 cp regional-s3-assets/instance-scheduler.zip s3://${regionalBucketName}/${instanceSchedulerName}/${version}/instance-scheduler.zip --profile saml

#### DEPLOY
echo "Stack status check:"
aws cloudformation describe-stacks --stack-name ${stackName} --profile saml --query "Stacks[0].StackStatus" --output text > /dev/null 2>&1
if [ $? == 0 ]; then # This check relies on the describe-stacks command above
  echo "Stack already exists. Updating..."
  runStackAction "update-stack"
  # wait for stack to update
  aws cloudformation wait stack-update-complete --stack-name ${stackName} --profile saml
else 
  echo "Stack does not exist. Creating..."
  runStackAction "create-stack"
  # wait for stack to create
  aws cloudformation wait stack-create-complete --stack-name ${stackName} --profile saml
fi