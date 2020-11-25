#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import re
import json
import time
import requests
import smtplib
import argparse
import urlparse
import random
import user_agent

from copy import copy
from lxml import html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, datetime, timedelta

user = user_agent.UserAgent()
interval_check_time = 0
start_date = datetime.now()
email_info = {}
is_in_stocks = []
items = []


# msg_content format
# msg_content['Subject'] = 'Subject'
# msg_content['Content'] = 'This is a content'
def send_email(msg_content):
    global email_info

    try:
        # Try to login smtp server
        smtp = smtplib.SMTP("smtp.gmail.com:587")
        smtp.ehlo()
        smtp.starttls()
        # use application password TODO
        smtp.login(email_info['sender'], email_info['sender-password'])
    except smtplib.SMTPAuthenticationError:
        # Log in failed
        print smtplib.SMTPAuthenticationError
        print('[Mail]\tFailed to login')
    else:
        # Log in successfully
        print('[Mail]\tLogged in! Composing message..')

        for receiver in email_info['receivers']:

            content = MIMEMultipart('alternative')
            content['subject'] = msg_content['subject']
            content['from'] = email_info['sender']
            content['to'] = receiver

            content.attach(MIMEText(msg_content['content'], 'plain'))
            smtp.sendmail(email_info['sender'], receiver, content.as_string())
            print('[Mail]\tMessage has been sent to %s.' % (receiver))

# send notified mail once a day.


def check_date_change(current_date):
    global items
    global is_in_stocks
    global start_date
    threshold_date = start_date + timedelta(days=1)

    # if date changed, send mail to notify the service is still working
    if current_date > threshold_date:
        start_date = current_date

        item_status_msg = 'Item Status:\n'
        for i in range(len(items)):
            item_status_msg += 'id[%s]: %s\n' % (
                items[i], 'In Stock!' if is_in_stocks[i] else 'Sold Out.')

        msg_content = {}
        msg_content['subject'] = '[Pokemon Center Alert] Service is working'
        msg_content['content'] = 'Pokemon Center Alert is still working until %s !\n\n%s' % (
            current_date.strftime('%Y-%m-%d %H:%M:%S'), item_status_msg)
        send_email(msg_content)


def get_item_status(url, item_id, selector):

    # set random user agent prevent banning
    r = requests.get(url,
                     params={
                         'p_cd': item_id
                     },
                     headers={
                         'User-Agent':
                         user.random(),
                         'Accept-Language':    'zh-tw',
                         'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                         'Connection': 'keep-alive',
                         'Accept-Encoding': 'gzip, deflate'
                     })
    r.raise_for_status()
    tree = html.fromstring(r.text)

    # find product name
    product_name = ""
    product_name_result = tree.xpath(selector['productName'])
    if product_name_result is None:
        print('Didn\'t find the \'Product Name\' element.')
    else:
        product_name = product_name_result[0].strip()

    # find Item Status
    try:
        item_status = tree.xpath(
            selector['itemStatus'])
        is_in_stock = False if (
            item_status is None or len(item_status) == 0) else True
        return is_in_stock, product_name, r.url

    except IndexError:
        print('Error in finding the \'Item Status\' element, trying again later...')

        # be banned, send mail then shut down
        # send mail notifying server shutdown
        msg_content = {}
        msg_content['subject'] = '[Pokemon Center Alert] Service has be BANNED'
        msg_content['content'] = 'Pokemon Center Alert has be banned at %s !' % (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        send_email(msg_content)
        return None, product_name, r.url


# read config json from path
def get_config(config):
    with open(config, 'r') as f:
        # handle '// ' to json string
        input_str = re.sub(r'// .*\n', '\n', f.read())
        return json.loads(input_str)

# add some arguments


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config',
                        default='%s/config.json' % os.path.dirname(
                            os.path.realpath(__file__)),
                        help='Add your config.json path')
    parser.add_argument('-t', '--poll-interval', type=int, default=780,
                        help='Time(second) between checking, default is 780 s.')

    return parser.parse_args()


def main():
    # set up arguments
    args = parse_args()
    interval_check_time = args.poll_interval
    global start_date
    global email_info
    global items

    start_date = datetime.now()

    # get config from path
    config = get_config(args.config)
    email_info = config['email']
    interval_check_time = config['default-internal-time']
    base_url = config['base_url']
    xpath_selector = config['xpath_selector']

    # get all items to parse
    items = config['item-to-parse']

    # get initial item status for compare
    item_status_msg = 'Item Status:\n'
    for i in range(len(items)):
        is_in_stock, product_name, item_url = get_item_status(
            base_url, items[i], xpath_selector)
        is_in_stocks.append(is_in_stock)
        item_status_msg += 'id[%s]: %s\n' % (
            items[i], 'In Stock!' if is_in_stock else 'Sold Out.')
    msg_content = {}
    msg_content['subject'] = '[Pokemon Center Alert] Service is working'
    msg_content['content'] = 'Pokemon Center Alert is still working until %s !\n\n%s' % (
        start_date.strftime('%Y-%m-%d %H:%M:%S'), item_status_msg)
    send_email(msg_content)

    while True and len(items):
        current_date = datetime.now()
        current_date_Str = current_date.strftime('%Y-%m-%d %H:%M:%S')
        print ('[%s] Start Checking' % (current_date_Str))

        # send mail everyday to notify service is working
        check_date_change(current_date)

        for i in range(len(items)):
            # url to parse
            print('[#%02d] Checking Item Status of [%s]' %
                  (i, items[i]))

            # get Item Status and Product Name
            is_in_stock, product_name, item_url = get_item_status(
                base_url, items[i], xpath_selector)
            encode_product_name = product_name.encode(encoding="utf-8", errors="strict")

            # Check if Item Status changed
            if is_in_stock is None:
                continue
            elif is_in_stock != is_in_stocks[i]:
                old_item_status = 'In Stock' if is_in_stock else 'Sold Out'
                current_item_status = 'In Stock' if is_in_stocks[i] else 'Sold Out'
                print('[#%02d][%s]: Item Status CHANGE from [%s] to [%s]!! Trying to send email.' %
                      (i, encode_product_name, old_item_status, current_item_status))
                msg_content = {}
                msg_content['subject'] = '[Pokemon Center Alert] [%s] Status CHANGE to [%s]' % (
                    encode_product_name, current_item_status)
                msg_content['content'] = '[%s]\nItem Status CHANGE from [%s] to [%s]!!\nURL to salepage: %s' % (
                    current_date_Str, old_item_status, current_item_status, item_url)
                send_email(msg_content)
                is_in_stocks[i] = is_in_stock
            else:
                old_item_status = 'In Stock' if is_in_stock else 'Sold Out'
                print('[#%02d][%s]: Item Status no change (still is [%s]). Ignoring...' %
                      (i, encode_product_name, old_item_status))

        # add random number to interval check time for preventing banning
        random_interval_check_time = interval_check_time + \
            random.randint(0, 150)

        # calculate next triggered time
        next_date_time = datetime.now() + timedelta(seconds=random_interval_check_time)
        print('Sleeping for %d seconds, next time start at %s\n' %
              (random_interval_check_time, next_date_time.strftime('%Y-%m-%d %H:%M:%S')))
        time.sleep(random_interval_check_time)


if __name__ == '__main__':
    main()
