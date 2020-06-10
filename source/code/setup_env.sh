pip install -r requirements.txt
[ -d ./tmp/pytz ] && rm -r ./tmp/pytz
[ -d ./tmp/requests ] && rm -r ./tmp/requests
pip install pytz -t ./tmp/pytz && pip install requests -t ./tmp/requests
for pkg in certifi chardet idna requests urllib3; do
    [ ! -d ./$pkg ] && mv ./tmp/requests/$pkg ./$pkg
done
[ ! -d ./pytz ] && mv ./tmp/pytz ./pytz
rm -r ./tmp