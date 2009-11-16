#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 encoding=utf-8

import gsmpdu
import traceback
import errors, message
import re
from smshandler import SmsHandler

MAX_MESSAGES =255

class PduSmsHandler(SmsHandler):
    CMGL_MATCHER =re.compile(r'^\+CMGL:.*?$')
    CMGL_STATUS="0"
    
    def __init__(self, modem):
        SmsHandler.__init__(self, modem)
    
    def get_mode_cmd(self):
        return "AT+CMGF=0"

    def send_sms(self, recipient, text):
        pdus = gsmpdu.get_outbound_pdus(text, recipient)
        if len(pdus) > MAX_MESSAGES:
            raise ValueError(
                'Max_message is %d and text requires %d messages' %
                (MAX_MESSAGES, len(pdus))
                )

        for pdu in pdus:
            self._send_pdu(pdu)
            
    def _send_pdu(self, pdu):
        # outer try to catch any error and make sure to
        # get the modem out of 'waiting for data' mode
        try:
            # accesing the property causes the pdu_string
            # to be generated, so do once and cache
            pdu_string = pdu.pdu_string

            # try to catch write timeouts
            try:
                # content length is in bytes, so half PDU minus
                # the first blank '00' byte
                self.modem.command( 
                'AT+CMGS=%d' % (len(pdu_string)/2 - 1), 
                read_timeout=1
                )

                # if no error is raised within the timeout period,
                # and the text-mode prompt WAS received, send the
                # sms text, wait until it is accepted or rejected
                # (text-mode messages are terminated with ascii char 26
                # "SUBSTITUTE" (ctrl+z)), and return True (message sent)
            except errors.GsmReadTimeoutError, err:
                if err.pending_data[0] == ">":
                    self.modem.command(pdu_string, write_term=chr(26))
                    return True

                    # a timeout was raised, but no prompt nor
                    # error was received. i have no idea what
                    # is going on, so allow the error to propagate
                else:
                    raise

            finally:
                pass

        # for all other errors...
        # (likely CMS or CME from device)
        except Exception:
            traceback.print_exc()
            # whatever went wrong, break out of the
            # message prompt. if this is missed, all
            # subsequent writes will go into the message!
            self.modem.break_out_of_prompt()

            # rule of thumb: pyGSM is meant to be embedded,
            # so DO NOT EVER allow exceptions to propagate
            # (obviously, this sucks. there should be an
            # option, at least, but i'm being cautious)
            return None
    
    def parse_incoming_message(self, header_line, line):
        pdu = None
        try:
            pdu = gsmpdu.ReceivedGsmPdu(line)
        except Exception, ex:
            traceback.print_exc(ex)
            self.modem._log('Error parsing PDU: %s' % line) 

        return self._process_incoming_pdu(pdu)   
    
    def parse_stored_messages(self, lines):
        # loop through all the lines attempting to match CMGL lines (the header)
        # and then match NOT CMGL lines (the content)
        # need to seed the loop first 'cause Python no like 'until' loops
        pdu_lines=[]
        messages = []
        m = None
        if len(lines)>0:
            m=self.CMGL_MATCHER.match(lines[0])

        while len(lines)>0:
            if m is None:
                # couldn't match OR no text data following match
                raise(errors.GsmReadError())

            # if here, we have a match AND text
            # start by popping the header (which we have stored in the 'm'
            # matcher object already)
            lines.pop(0)

            # now loop through, popping content until we get
            # the next CMGL or out of lines
            while len(lines)>0:
                m=self.CMGL_MATCHER.match(lines[0])
                if m is not None:
                    # got another header, get out
                    break
                else:
                    # HACK: For some reason on the multitechs the first
                    # PDU line has the second '+CMGL' response tacked on
                    # this may be a multitech bug or our bug in 
                    # reading the responses. For now, split the response
                    # on +CMGL
                    line = lines.pop(0)
                    line, cmgl, rest = line.partition('+CMGL')
                    if len(cmgl)>0:
                        lines.insert(0,'%s%s' % (cmgl,rest))
                    pdu_lines.append(line)

            # now create and process PDUs
            for pl in pdu_lines:
                try:
                    pdu = gsmpdu.ReceivedGsmPdu(pl)
                    msg = self._process_incoming_pdu(pdu)
                    if msg is not None:
                        messages.append(msg)

                except Exception, ex:
                    traceback.print_exc(ex)
                    self.modem._log('Error parsing PDU: %s' % pl) # TODO log

        return messages
        
    def _incoming_pdu_to_msg(self, pdu):
        if pdu.text is None or len(pdu.text)==0:
            self.modem._log('Blank inbound text, ignoring')
            return
        
        msg = message.IncomingMessage(self,
                                      pdu.address,
                                      pdu.sent_ts,
                                      pdu.text)
        return msg

    def _process_incoming_pdu(self, pdu):
        if pdu is None:
            return None

        # is this a multi-part (concatenated short message, csm)?
        if pdu.is_csm:
            # process pdu will either
            # return a 'super' pdu with the entire
            # message (if this is the last segment)
            # or None if there are more segments coming
            pdu = self._process_csm(pdu)
 
        if pdu is not None:
            return self._incoming_pdu_to_msg(pdu)
        return None

    def _process_csm(self, pdu):
        if not pdu.is_csm:
            return pdu

        # self.multipart is a dict of dicts of dicts
        # holding all parts of messages by sender
        # e.g. { '4155551212' : { 0: { seq1: pdu1, seq2: pdu2{ } }
        #
        if pdu.address not in self.multipart:
            self.multipart[pdu.address]={}

        sender_msgs=self.multipart[pdu.address]
        if pdu.csm_ref not in sender_msgs:
            sender_msgs[pdu.csm_ref]={}

        # these are all the pdus in this 
        # sequence we've recived
        received = sender_msgs[pdu.csm_ref]
        received[pdu.csm_seq]=pdu
        
        # do we have them all?
        if len(received)==pdu.csm_total:
            pdus=received.values()
            pdus.sort(key=lambda x: x.csm_seq)
            text = ''.join([p.text for p in pdus])
            
            # now make 'super-pdu' out of the first one
            # to hold the full text
            super_pdu = pdus[0]
            super_pdu.csm_seq = 0
            super_pdu.csm_total = 0
            super_pdu.pdu_string = None
            super_pdu.text = text
            super_pdu.encoding = None
        
            del sender_msgs[pdu.csm_ref]
            
            return super_pdu
        else:
            return None
