# Moneypenny

Moneypenny is a simple webhook for [Envoy](https://signwithenvoy.com/) that
will post visitors name and photos to
[reddit](https://github.com/reddit/reddit).

# Required libraries
* [flask](http://flask.pocoo.org/)
* [requests](http://docs.python-requests.org/)
* [PRAW](https://praw.readthedocs.org)
* [pytz](http://pytz.sourceforge.net/)
* [boto (>=2.6.0)](http://boto.cloudhackers.com/)
* [babel](http://babel.pocoo.org/)

# Configuration
```ini
[envoy]
api_key = 

[reddit]
username =
password =
subreddit =
# Formating replacements:
#  ${location}
#  ${visitor_name}
#  ${date}
link_format = ${visitor_name} on ${date}

[aws]
s3_bucket = 

[locations]
# short_code = Long Name, timezone
sfo = San Francisco, America/Los_Angeles

[moneypenny]
# Should getting the image from envoy fail, we'll use this URL instead
default_image_url =
```
