import * as cdk from '@aws-cdk/core';
import * as ssm from '@aws-cdk/aws-ssm'
import * as path from 'path'
import * as yml from 'js-yaml'
import * as fs from 'fs'

export interface InstanceSchedulerSSMDocProps {
  ec2StartSSMDocName: string;
  ec2StopSSMDocName: string;
  rdsTaggedInstancesStartSSMDocName: string;
  rdsTaggedInstancesStopSSMDocName: string;
  rdsTaggedClustersStartSSMDocName: string;
  rdsTaggedClustersStopSSMDocName: string;
}
export class InstanceSchedulerSSMDocuments extends cdk.Construct {

  constructor(scope: cdk.Stack, id: string, props: InstanceSchedulerSSMDocProps) {
    super(scope, id);

    const ec2StartSSMDocumentPath = path.join(__dirname, '../runbooks/Scheduler-StartTaggedEC2Instances.yaml')
    const ec2StopSSMDocumentPath = path.join(__dirname, '../runbooks/Scheduler-StopTaggedEC2Instances.yaml')
    const rdsTaggedInstancesStartSSMDocumentPath = path.join(__dirname, '../runbooks/Scheduler-StartTaggedRDSInstances.yaml')
    const rdsTaggedInstancesStopSSMDocumentPath = path.join(__dirname, '../runbooks/Scheduler-StopTaggedRDSInstances.yaml')
    const rdsTaggedClustersStartSSMDocumentPath = path.join(__dirname, '../runbooks/Scheduler-StartTaggedRDSClusters.yaml')
    const rdsTaggedClustersStopSSMDocumentPath = path.join(__dirname, '../runbooks/Scheduler-StopTaggedRDSClusters.yaml')

    new ssm.CfnDocument(this, "EC2StartSSMDocument", {
      name: props.ec2StartSSMDocName,
      documentType: 'Automation',
      content: yml.load(fs.readFileSync(ec2StartSSMDocumentPath, 'utf8'))
    })

    new ssm.CfnDocument(this, "EC2StopSSMDocument", {
      name: props.ec2StopSSMDocName,
      documentType: 'Automation',
      content: yml.load(fs.readFileSync(ec2StopSSMDocumentPath, 'utf8'))
    })

    new ssm.CfnDocument(this, "RDSTaggedInstancesStartSSMDocument", {
      name: props.rdsTaggedInstancesStartSSMDocName,
      documentType: 'Automation',
      content: yml.load(fs.readFileSync(rdsTaggedInstancesStartSSMDocumentPath, 'utf8'))
    })

    new ssm.CfnDocument(this, "RDSTaggedInstancesStopSSMDocument", {
      name: props.rdsTaggedInstancesStopSSMDocName,
      documentType: 'Automation',
      content: yml.load(fs.readFileSync(rdsTaggedInstancesStopSSMDocumentPath, 'utf8'))
    })

    new ssm.CfnDocument(this, "RDSTaggedClustersStartSSMDocument", {
      name: props.rdsTaggedClustersStartSSMDocName,
      documentType: 'Automation',
      content: yml.load(fs.readFileSync(rdsTaggedClustersStartSSMDocumentPath, 'utf8'))
    })

    new ssm.CfnDocument(this, "RDSTaggedClustersStopSSMDocument", {
      name: props.rdsTaggedClustersStopSSMDocName,
      documentType: 'Automation',
      content: yml.load(fs.readFileSync(rdsTaggedClustersStopSSMDocumentPath, 'utf8'))
    })
  }
  
}
