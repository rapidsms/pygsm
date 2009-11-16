#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 encoding=utf-8

import errors, traceback, message
import re, datetime, time
import StringIO
import pytz
from smshandler import SmsHandler

class TextSmsHandler(SmsHandler):
    SCTS_FMT = "%y/%m/%d,%H:%M:%S"
    CMGL_MATCHER=re.compile(r'^\+CMGL: (\d+),"(.+?)","(.+?)",*?,"(.+?)".*?$')
    CMGL_STATUS='"REC UNREAD"'
    
    def __init__(self, modem):
        SmsHandler.__init__(self, modem)
    
    def get_mode_cmd(self):
        return "AT+CMGF=1"
        
    def send_sms(self, recipient, text):
        """Sends an SMS to _recipient_ containing _text_. Some networks
           will automatically chunk long messages into multiple parts,
           and reassembled them upon delivery, but some will silently
           drop them. At the moment, pyGSM does nothing to avoid this,
           so try to keep _text_ under 160 characters."""

        old_mode = None
        try:
            try:
                # cast the text to a string, to check that
                # it doesn't contain non-ascii characters
                try:
                    text = str(text)

                # uh-oh. unicode ahoy
                except UnicodeEncodeError:

                    # fetch and store the current mode (so we can
                    # restore it later), and override it with UCS2
                    csmp = self.modem.query("AT+CSMP?", "+CSMP:")
                    if csmp is not None:
                        old_mode = csmp.split(",")
                        mode = old_mode[:]
                        mode[3] = "8"

                        # enable hex mode, and set the encoding
                        # to UCS2 for the full character set
                        self.modem.command('AT+CSCS="HEX"')
                        self.modem.command("AT+CSMP=%s" % ",".join(mode))
                        text = text.encode("utf-16").encode("hex")

                # initiate the sms, and give the device a second
                # to raise an error. unfortunately, we can't just
                # wait for the "> " prompt, because some modems
                # will echo it FOLLOWED BY a CMS error
                result = self.modem.command(
                        'AT+CMGS=\"%s\"' % (recipient),
                        read_timeout=1)

            # if no error is raised within the timeout period,
            # and the text-mode prompt WAS received, send the
            # sms text, wait until it is accepted or rejected
            # (text-mode messages are terminated with ascii char 26
            # "SUBSTITUTE" (ctrl+z)), and return True (message sent)
            except errors.GsmReadTimeoutError, err:
                if err.pending_data[0] == ">":
                    self.modem.command(text, write_term=chr(26))
                    return True

                # a timeout was raised, but no prompt nor
                # error was received. i have no idea what
                # is going on, so allow the error to propagate
                else:
                    raise

        # for all other errors...
        # (likely CMS or CME from device)
        except Exception, err:
            traceback.print_exc(err)
            # whatever went wrong, break out of the
            # message prompt. if this is missed, all
            # subsequent writes will go into the message!
            self.modem.break_out_of_prompt()

            # rule of thumb: pyGSM is meant to be embedded,
            # so DO NOT EVER allow exceptions to propagate
            # (obviously, this sucks. there should be an
            # option, at least, but i'm being cautious)
            return None

        finally:

            # if the mode was overridden above, (if this
            # message contained unicode), switch it back
            if old_mode is not None:
                self.modem.command("AT+CSMP=%s" % ",".join(old_mode))
                self.modem.command('AT+CSCS="GSM"')

    # returns a list of messages
    def parse_stored_messages(self, lines):
        # loop through all the lines attempting to match CMGL lines (the header)
        # and then match NOT CMGL lines (the content)
        # need to seed the loop first
        messages = []
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

            # now put the captures into independent vars
            index, status, sender, timestamp = m.groups()

            # now loop through, popping content until we get
            # the next CMGL or out of lines
            msg_buf=StringIO.StringIO()
            while len(lines)>0:
                m=self.CMGL_MATCHER.match(lines[0])
                if m is not None:
                    # got another header, get out
                    break
                else:
                    msg_buf.write(lines.pop(0))

            # get msg text
            msg_text=msg_buf.getvalue().strip()

            # now create message
            messages.append(self._incoming_to_msg(timestamp,sender,msg_text))
        return messages

    # returns a single message   
    def parse_incoming_message(self, header_line, text):
        # since this line IS a CMT string (an incoming
        # SMS), parse it and store it to deal with later
        m = re.match(r'^\+CMT: "(.+?)",.*?,"(.+?)".*?$', header_line)
        sender = ""
        timestamp = None
        if m is not None:

            # extract the meta-info from the CMT line,
            # and the message from the FOLLOWING line
            sender, timestamp = m.groups()

        # multi-part messages begin with ASCII 130 followed
        # by "@" (ASCII 64). TODO: more docs on this, i wrote
        # this via reverse engineering and lost my notes
        if (ord(text[0]) == 130) and (text[1] == "@"):
            part_text = text[7:]
            
            # ensure we have a place for the incoming
            # message part to live as they are delivered
            if sender not in self.multipart:
                self.multipart[sender] = []

            # append THIS PART
            self.multipart[sender].append(part_text)

            # abort if this is not the last part
            if ord(text[5]) != 173:
                return None
            
            # last part, so switch out the received
            # part with the whole message, to be processed
            # below (the sender and timestamp are the same
            # for all parts, so no change needed there)
            text = "".join(self.multipart[sender])
            del self.multipart[sender]

        return self._incoming_to_msg(timestamp, sender, text)
            
    def _incoming_to_msg(self, timestamp, sender, text):

        # since neither message notifications nor messages
        # fetched from storage give any indication of their
        # encoding, we're going to have to guess. if the
        # text has a multiple-of-four length and starts
        # with a UTF-16 Byte Order Mark, try to decode it
        # into a unicode string
        try:
            if (len(text) % 4 == 0) and (len(text) > 0):
                bom = text[:4].lower()
                if bom == "fffe"\
                or bom == "feff":
                    
                    # decode the text into a unicode string,
                    # so developers embedding pyGSM need never
                    # experience this confusion and pain
                    text = text.decode("hex").decode("utf-16")

        # oh dear. it looked like hex-encoded utf-16,
        # but wasn't. who sends a message like that?!
        except:
            pass

        # create and store the IncomingMessage object
        time_sent = None
        if timestamp is not None:
            time_sent = self._parse_incoming_timestamp(timestamp)
        return message.IncomingMessage(self, sender, time_sent, text)
         
    def _parse_incoming_timestamp(self, timestamp):
        """Parse a Service Center Time Stamp (SCTS) string into a Python datetime
           object, or None if the timestamp couldn't be parsed. The SCTS format does
           not seem to be standardized, but looks something like: YY/MM/DD,HH:MM:SS."""

        # timestamps usually have trailing timezones, measured
        # in 15-minute intervals (?!), which is not handled by
        # python's datetime lib. if _this_ timezone does, chop
        # it off, and note the actual offset in minutes
        tz_pattern = r"([-+])(\d+)$"
        m = re.search(tz_pattern, timestamp)
        if m is not None:
            timestamp = re.sub(tz_pattern, "", timestamp)
            tz_offset = datetime.timedelta(minutes=int(m.group(2)) * 15)
            if m.group(1)=='-':
                tz_offset = -tz_offset

        # we won't be modifying the output, but
        # still need an empty timedelta to subtract
        else: 
            tz_offset = datetime.timedelta()

        # attempt to parse the (maybe modified) timestamp into
        # a time_struct, and convert it into a datetime object
        try:
            time_struct = time.strptime(timestamp, self.SCTS_FMT)
            dt = datetime.datetime(*time_struct[:6])
            dt.replace(tzinfo=pytz.utc)
           
            # patch the time to represent UTC, since
            dt-=tz_offset
            return dt

        # if the timestamp couldn't be parsed, we've encountered
        # a format the pyGSM doesn't support. this sucks, but isn't
        # important enough to explode like RubyGSM does
        except ValueError:
            traceback.print_exc()
            return None
