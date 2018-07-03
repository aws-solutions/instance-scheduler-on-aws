#!/usr/bin/env bash
echo "Staring to build distribution"
echo "make build"
echo "Pipeline type ${1}"
export BUCKET_PREFIX=solutions
if [ $1 = "mainline" ]; then
    export BUCKET_PREFIX=solutions-test
fi
export OBJECT_PREFIX='aws-instance-scheduler/latest/'
echo "Bucket prefix for distribution '${BUCKET_PREFIX}/${OBJECT_PREFIX}'"
cd ../source/code
echo "make bucket=${BUCKET_PREFIX} prefix=${OBJECT_PREFIX}"
make bucket=$BUCKET_PREFIX prefix="${OBJECT_PREFIX}"
cd ../../deployment
echo "mkdir -p dist"
mkdir -p dist

mv instance-scheduler-latest.template dist/instance-scheduler.template
mv scheduler-cli-latest.zip dist/scheduler-cli.zip
mv instance-scheduler-`cat ../source/code/version.txt`.zip dist
rm instance-scheduler-`cat ../source/code/version.txt`.template
rm instance-scheduler-remote-`cat ../source/code/version.txt`.template
rm scheduler-cli-`cat ../source/code/version.txt`.zip


echo "Completed building distribution"
