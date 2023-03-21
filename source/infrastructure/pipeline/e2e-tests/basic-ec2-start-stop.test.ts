import {RESOURCES} from "./basic-ec2-start-stop.test.resources";
import {DescribeInstanceStatusCommand, EC2Client} from "@aws-sdk/client-ec2";


const instanceID = RESOURCES.EC2InstanceID.get();

test('instanceID is accessible', ()=> {
  expect(instanceID).not.toBeNull()
})

test('attempt ec2 id print', async ()=> {
  const client = new EC2Client({})

  const result = await client.send(
    new DescribeInstanceStatusCommand({
      InstanceIds: [RESOURCES.EC2InstanceID.get()!],
    })
  )

  console.log(result)
})
