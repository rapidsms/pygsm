#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 encoding=utf-8

import re

ERR_MSG = "Must use one of concrete subclasses:PduSmsHandler or TextSmsHandler"

class SmsHandler(object):
    
    def __init__(self,modem):
        self.modem = modem
        self.multipart = {}

    def send_sms(self, recipient, text):
        raise Exception(ERR_MSG)
    
    def get_mode_cmd(self):
        raise Exception(ERR_MSG)
    
    # returns a list of messages
    def parse_stored_messages(self, lines):
        raise Exception(ERR_MSG)

    # returns a single message   
    def parse_incoming_message(self, header_line, line):
        raise Exception(ERR_MSG)