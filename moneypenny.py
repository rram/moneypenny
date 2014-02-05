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

app = Flask(__name__)
app.debug = True
config = RawConfigParser()
config.read("moneypenny.ini")

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
for short, info in config.items("locations"):
    location_db[short] = map(string.strip, info.split(","))

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
        keyname = "{}/{}.jpg".format(location, entry["id"])
        bucket = s3.get_bucket(s3_bucket)
        key = bucket.new_key(keyname)
        key.set_contents_from_file(
            r.raw,
            headers={
                "Content-Type": "image/jpeg",
            },
            policy="public-read"
        )
        img_url = "http://s3.amazonaws.com/{}".format(keyname)
    else:
        app.logger.debug("Got status code of %i, not using image",
                r.status_code)
        img_url = None

    title = link_format.format(
                d=date,
                location=loc_info[0],
                visitor_name=visitor_name
            )

    # NOTE: I've modified praw to treat text == '' as a self post with no text
    text = '' if img_url is None else None
    s = sr.submit(title, text=text, url=img_url, raise_captcha_exception=True)
    if isinstance(s, basestring):
        return s
    else:
        return s.short_link


if __name__ == "__main__":
    app.run()
