# Placeholder
#!/bin/bash
cd ..
echo 'pip3 install -r source/testing_requirements.txt'
pip3 install -r source/code/testing_requirements.txt
echo 'cd source && pytest tests && cd ../deployment'
cd source && pytest code/tests && cd ../deployment