import {START_STOP_TEST_INSTANCE_ID_OUT_PATH} from "./basic-ec2-start-stop.test.resources";

test('Print Environment', ()=> {
  console.log(process.env)
})

test('attempt ec2 id print', ()=> {
  console.log(process.env[START_STOP_TEST_INSTANCE_ID_OUT_PATH])
})
