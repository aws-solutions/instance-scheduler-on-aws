#!/bin/bash

set -e && [[ "$DEBUG" == 'true' ]] && set -x

RED="\033[0;31m"
NC="\033[00m"

empty_files_found=""

for file in "$@"
do
  if [[ -f "$file" && ! -s "$file" ]]; then
    empty_files_found="yes"
    printf "%b%s is empty!\n%b" "$RED" "$file" "$NC"
  fi
done

if [[ $empty_files_found == "yes" ]]; then
  exit 1;
fi

exit 0
