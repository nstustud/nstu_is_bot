kill -9 $(ps -ax | grep -e r.py | awk 'NR==1{print $1}')
