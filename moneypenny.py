#!/usr/bin/python
"""
A Flask app to post visitor information to reddit.

Requirements:
    * Envoy account (https://signwithenvoy.com/)
    * reddit account (http://www.reddit.com/)
    * PRAW library (https://github.com/praw-dev/praw/)
"""

from ConfigParser import RawConfigParser
from datetime import datetime
from string import Template
import hashlib
import hmac
import json

from flask import Flask, abort, request
import boto
import collections
import praw
import pytz
import requests
import string

CONFIG_FILE="moneypenny.ini"

app = Flask(__name__)
config = RawConfigParser()
config.read(CONFIG_FILE)

# Envoy
api_key = config.get("envoy", "api_key")

# AWS
s3_key_id = None
s3_secret_key = None
if config.has_option("aws", "s3_key_id"):
    s3_key_id = config.get("aws", "s3_key_id")
    s3_secret_key = config.get("aws", "s3_secret_key")
s3_bucket = config.get("aws", "s3_bucket")

# reddit
username = config.get("reddit", "username")
password = config.get("reddit", "password")
subreddit = config.get("reddit", "subreddit")
link_format = config.get("reddit", "link_format")
r = praw.Reddit(user_agent="Mrs. Moneypenny by /u/rram")
r.login(username, password)
sr = r.get_subreddit(subreddit)

# locations
location_db = {}
City = collections.namedtuple("City", ["name", "timezone", "code"])
for short, info in config.items("locations"):
    data = map(string.strip, info.split(","))
    data.append(short)
    location_db[short] = City(*data)

# https://github.com/spladug/wessex
irc_channel = None
message_format = None
try:
    import wessex
    if config.has_section("harold"):
        harold = wessex.connect_harold(["/etc/harold.ini", CONFIG_FILE])
        irc_channel = harold.get_irc_channel(config.get("harold", "channel"))
        message_format = config.get("harold", "message_format")
except ImportError:
    pass

def constant_time_compare(actual, expected):
    """
    Returns True if the two strings are equal, False otherwise

    The time taken is dependent on the number of characters provided
    instead of the number of characters that match.
    """
    actual_len   = len(actual)
    expected_len = len(expected)
    result = actual_len ^ expected_len
    if expected_len > 0:
        for i in xrange(actual_len):
            result |= ord(actual[i]) ^ ord(expected[i % expected_len])
    return result == 0

def verify_message(token, timestamp, signature):
    expected = hmac.new(
                key=api_key,
                msg="{}{}".format(timestamp, token),
                digestmod=hashlib.sha256).hexdigest()
    return constant_time_compare(signature, expected)

@app.route("/")
def health():
    return "Hello, James."

@app.route("/visitor/<location>", methods=["POST"])
def visitor(location):
    loc_info = location_db[location]
    entry = request.form["entry"]
    status = request.form["status"]
    timestamp = request.form["timestamp"]
    token = request.form["token"]
    signature = request.form["signature"]

    if not verify_message(token, timestamp, signature):
        app.logger.warning("Message failed to verify, aborting!")
        abort(400)

    if status != "sign_in":
        app.logger.debug("Ignorning non-sign in: %s", status)
        return ""

    entry = json.loads(entry)

    date = entry.get("signed_in_time_utc")
    date = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
    date = date.replace(tzinfo=pytz.UTC)
    date = date.astimezone(pytz.timezone(loc_info[1]))
    visitor_name = entry.get("your_full_name")

    # Copy the image from Envoy to our own S3 bucket
    r = requests.get(entry['photo_url'], stream=True)
    if r.status_code == 200:
        s3 = boto.connect_s3(s3_key_id, s3_secret_key)
        keyname = "{}/{}.jpg".format(loc_info.code, entry["id"])
        bucket = s3.get_bucket(s3_bucket, validate=False)
        key = bucket.new_key(keyname)
        key.set_contents_from_string(
            r.content,
            headers={
                "Content-Type": "image/jpeg",
            },
            policy="public-read"
        )
        img_url = "http://s3.amazonaws.com/{}/{}".format(s3_bucket, keyname)
    else:
        app.logger.debug("Got status code of %i, not using image",
                r.status_code)
        img_url = None

    title = link_format.format(
                d=date,
                location=loc_info,
                visitor_name=visitor_name
            )

    # NOTE: I've modified praw to treat text == '' as a self post with no text
    text = '' if img_url is None else None
    s = sr.submit(title, text=text, url=img_url, raise_captcha_exception=True)
    link = "Something went wrong here"
    if isinstance(s, basestring):
        app.logger.debug("Posted to %s", s)
        link = s
    else:
        app.logger.debug("Posted to %s", s.short_link)
        link = s.short_link

    if irc_channel:
        message = message_format.format(
            d=date,
            location=loc_info,
            visitor_name=visitor_name,
            link=link,
        )
        irc_channel.message(message)
    return link


if __name__ == "__main__":
    app.run()
