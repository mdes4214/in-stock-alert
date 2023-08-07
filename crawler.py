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

            content.attach(MIMEText(msg_content['content'].encode('utf8'), 'plain'))
            smtp.sendmail(email_info['sender'], receiver, content.as_string())
            print('[Mail]\tMessage has been sent to %s.' % (receiver))

# send notified mail once a day.


def check_date_change(current_date, site_titles):
    global items
    global is_in_stocks
    global start_date
    threshold_date = start_date + timedelta(days=1)

    # if date changed, send mail to notify the service is still working
    if current_date > threshold_date:
        start_date = current_date

        item_status_msg = 'Item Status:\n'
        for i in range(len(items)):
            item_status_msg += '%s - id[%s]: %s\n' % (
                site_titles[i], items[i], 'In Stock!' if is_in_stocks[i] else 'Sold Out.')

        msg_content = {}
        msg_content['subject'] = '[In Stock Alert] Service is working'
        msg_content['content'] = 'In Stock Alert is still working until %s !\n\n%s' % (
            current_date.strftime('%Y-%m-%d %H:%M:%S'), item_status_msg)
        send_email(msg_content)


def get_item_status(url, item_id, selector, site):

    # set random user agent prevent banning
    params = {}
    if site == 'AmazonJP':
        url += item_id
    elif site == 'PokemonCenter':
        params['p_cd'] = item_id
    r = requests.get(url,
                     params = params,
                     headers = {
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
        if site == 'AmazonJP':
            product_name = product_name_result[0].text.strip()
        elif site == 'PokemonCenter':
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
        msg_content['subject'] = '[In Stock Alert] Service has be BANNED by %s' % (site)
        msg_content['content'] = 'In Stock Alert has be banned by %s at %s !' % (
            site, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
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

    # get config by site
    sites = config['sites']
    base_urls = []
    xpath_selectors = []
    site_titles = []
    for i in range(len(sites)):
        if sites[i] in config:            
            items_site = config[sites[i]]['item-to-parse']
            items.extend(items_site)
            for j in range(len(items_site)):
                base_urls.append(config[sites[i]]['base_url'])
                xpath_selectors.append(config[sites[i]]['xpath_selector'])
                site_titles.append(sites[i])
                is_in_stocks.append(False)

    while True and len(items):
        current_date = datetime.now()
        current_date_Str = current_date.strftime('%Y-%m-%d %H:%M:%S')
        print ('[%s] Start Checking' % (current_date_Str))

        # send mail everyday to notify service is working
        check_date_change(current_date, site_titles)

        # Aggregate all change in one mail
        msg_content = {}
        msg_content['subject'] = '[In Stock Alert] Status CHANGE! '
        msg_content['content'] = '[%s]' % (current_date_Str)
        is_send_mail = False
        
        # check items
        for i in range(len(items)):
            # url to parse
            print('[#%02d] Checking Item Status of %s - [%s]' %
                  (i, site_titles[i], items[i]))

            # get Item Status and Product Name
            is_in_stock, product_name, item_url = get_item_status(
                base_urls[i], items[i], xpath_selectors[i], site_titles[i])
            encode_product_name = product_name

            # Check if Item Status changed            
            if is_in_stock is None:
                continue
            elif is_in_stock != is_in_stocks[i]:
                old_item_status = 'In Stock' if is_in_stocks[i] else 'Sold Out'
                current_item_status = 'In Stock' if is_in_stock else 'Sold Out'
                print('[#%02d][%s][%s]: Item Status CHANGE from [%s] to [%s]!! Trying to send email.' %
                      (i, site_titles[i], encode_product_name, old_item_status, current_item_status))
                msg_content['subject'] += '[%s]' % (site_titles[i])
                msg_content['content'] += '\n\n[%s][%s]\nItem Status CHANGE from [%s] to [%s]!!\nURL to salepage: %s' % (
                    site_titles[i], encode_product_name, old_item_status, current_item_status, item_url)

                is_send_mail = True
                is_in_stocks[i] = is_in_stock
            else:
                old_item_status = 'In Stock' if is_in_stock else 'Sold Out'
                print('[#%02d][%s][%s]: Item Status no change (still is [%s]). Ignoring...' %
                      (i, site_titles[i], encode_product_name, old_item_status))
        
        # send summary mail
        if is_send_mail:
            msg_content['content'] = msg_content['content'].encode(
                encoding="utf-8", errors="strict")
            send_email(msg_content)

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
