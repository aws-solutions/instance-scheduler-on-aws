######################################################################################################################
#  Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Amazon Software License (the "License"). You may not use this file except in compliance        #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://aws.amazon.com/asl/                                                                                    #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################

# version number
version=`cat version.txt`

# bucket name to deploy to
ifndef bucket
bucket=instance-scheduler-deploy
endif

# prefix of deployed artifacts in bucket
ifndef prefix
prefix = instance-scheduler/$(version)/
endif

# acl of s3 artifacts
ifndef acl
acl = public-read
endif

ifndef acl_remote
acl_remote = $(acl)
endif

ifndef s3_mirrors
s3_mirrors = true
endif

s3bucket=s3://$(bucket)/

s3http='https:\/\/s3-eu-west-1.amazonaws.com\/$(bucket)'

pydirs= configuration configuration/setbuilders requesthandlers schedulers util boto_retry
py=$(foreach dir, $(pydirs), $(wildcard $(dir)/*.py))

cli_dirs = cli cli/scheduler_cli
pycli=$(foreach d, $(cli_dirs), $(wildcard $(d)/*.py))


# ops automator templates
templates=$(wildcard ../cloudformation/*.template)

deployment=../../deployment
zip = $(deployment)/instance-scheduler-$(version).zip
zip_cli = $(deployment)/scheduler-cli-$(version).zip
pwd=`pwd`

build: lambda scheduler-cli  cfn

######################################################################################################################
# lambda code                                                                                                        #
######################################################################################################################

lambda:$(py) main.py version.txt

	# delete old zip files
	find $(deployment) -maxdepth 1 -type f -name 'instance-scheduler-*.zip' -delete

	mkdir -p $(deployment)
	zip  $(zip) version.txt
	mv version.py version.py.org
	sed s/%version%/$(version)/g version.py.org > version.py
	zip  $(zip) main.py version.py
	rm version.py
	mv version.py.org version.py
	zip -r $(zip)  $(py)  version.txt
	zip -r -q $(zip) pytz
	zip -r $(zip) models

######################################################################################################################
# cli                                                                                                                #
######################################################################################################################

scheduler-cli:$(pycli) version.txt

	# delete old deployments
	find $(deployment) -maxdepth 1 -type f -name 'scheduler-cli-*.zip' -delete

	mkdir -p $(deployment)

	mv cli/scheduler_cli/scheduler_cli.py cli/scheduler_cli/scheduler_cli.org
	sed s/#version#/$(version)/g cli/scheduler_cli/scheduler_cli.org > cli/scheduler_cli/scheduler_cli.py
	cp version.txt cli/version.txt
	cd ./cli && zip -r ../$(zip_cli) scheduler_cli/*.py
	rm cli/scheduler_cli/scheduler_cli.py
	mv cli/scheduler_cli/scheduler_cli.org cli/scheduler_cli/scheduler_cli.py
	mv cli/setup.py cli/setup.org
	sed s/#version#/$(version)/g cli/setup.org > cli/setup.py
	cd ./cli && zip ../$(zip_cli) setup.py instance-scheduler-cli-runner.py
	rm cli/version.txt
	rm cli/setup.py
	mv cli/setup.org cli/setup.py
	cp $(zip_cli) $(deployment)/scheduler-cli-latest.zip

######################################################################################################################
# cloudformation templates                                                                                           #
######################################################################################################################

cfn:version.txt $(templates)
	mkdir -p $(deployment)

	# delete old templates
	find $(deployment) -maxdepth 1 -type f -name 'instance-scheduler-*.template' -delete

	# build main template
	python ./build-instance-scheduler-template.py ../cloudformation/instance-scheduler.template $(version) $(bucket) $(prefix) $(s3_mirrors)> $(deployment)/instance-scheduler-$(version).template
	cp $(deployment)/instance-scheduler-$(version).template  $(deployment)/instance-scheduler-latest.template

	# template for setting cross account role
	python ./build-instance-scheduler-template.py ../cloudformation/instance-scheduler-remote.template $(version) $(bucket) $(prefix) $(s3_mirrors)> $(deployment)/instance-scheduler-remote-$(version).template
	cp  $(deployment)/instance-scheduler-remote-$(version).template $(deployment)/instance-scheduler-remote-latest.template

######################################################################################################################
# Deploy to S3                                                                                                       #
######################################################################################################################

deploy: lambda cfn scheduler-cli
	aws s3 cp $(deployment)/instance-scheduler-$(version).template $(s3bucket)$(prefix) --acl $(acl)
	aws s3 cp $(deployment)/instance-scheduler-latest.template $(s3bucket) --acl $(acl)

	aws s3 cp $(deployment)/instance-scheduler-remote-$(version).template $(s3bucket)$(prefix) --acl $(acl_remote)
	aws s3 cp $(deployment)/instance-scheduler-remote-latest.template $(s3bucket) --acl $(acl_remote)

	aws s3 cp $(zip) $(s3bucket)$/$(prefix) --acl $(acl)
	aws s3 cp $(zip_cli) $(s3bucket)$(prefix) --acl $(acl)
	aws s3 cp $(deployment)/scheduler-cli-latest.zip $(s3bucket) --acl $(acl)

	python update-build-number.py version.txt
