#!/bin/bash
cd ..
echo 'pip install -r source/lambda/testing_requirements.txt'
pip install -r source/lambda/testing_requirements.txt
echo 'cd source/lambda && pytest tests && cd ../deployment'
cd source/lambda && pytest ./tests && cd ../../deployment