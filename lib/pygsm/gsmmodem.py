#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 encoding=utf-8


from __future__ import with_statement

# debian/ubuntu: apt-get install python-tz

import re
import datetime
import time
import errors
import threading
import gsmcodecs
from devicewrapper import DeviceWrapper
from pdusmshandler import PduSmsHandler
from textsmshandler import TextSmsHandler

class GsmModem(object):
    """pyGSM is a Python module which uses pySerial to provide a nifty
       interface to send and receive SMS via a GSM Modem. It was ported
       from RubyGSM, and provides (almost) all of the same features. It's
       easy to get started:

          # create a GsmModem object:
          >>> import pygsm
          >>> modem = pygsm.GsmModem(port="/dev/ttyUSB0")

          # harass Evan over SMS:
          # (try to do this before 11AM)
          >>> modem.send_sms("+13364130840", "Hey, wake up!")

          # check for incoming SMS:
          >>> print modem.next_message()
          <pygsm.IncomingMessage from +13364130840: "Leave me alone!">


       There are various ways of polling for incoming messages -- a choice
       which has been deliberately left to the application author (unlike
       RubyGSM). Execute `python -m pygsm.gsmmodem` to run this example:

          # connect to the modem
          modem = pygsm.GsmModem(port=sys.argv[1])

          # check for new messages every two
          # seconds for the rest of forever
          while True:
              msg = modem.next_message()

              # we got a message! respond with
              # something useless, as an example
              if msg is not None:
                  msg.respond("Thanks for those %d characters!" %
                      len(msg.text))

              # no messages? wait a couple
              # of seconds and try again
              else: time.sleep(2)


       pyGSM is distributed via GitHub:
       http://github.com/adammck/pygsm

       Bugs reports (especially for
       unsupported devices) are welcome:
       http://github.com/adammck/pygsm/issues"""


    # override these after init, and
    # before boot. they're not sanity
    # checked, so go crazy.
    cmd_delay = 0.1
    retry_delay = 2
    max_retries = 10
    modem_lock = threading.RLock()
    
    
    def __init__(self, *args, **kwargs):
        """Creates, connects to, and boots a GSM Modem. All of the arguments
           are optional (although "port=" should almost always be provided),
           and passed along to serial.Serial.__init__ verbatim. For all of
           the possible configration options, see:

           http://pyserial.wiki.sourceforge.net/pySerial#tocpySerial10

           Alternatively, a single "device" kwarg can be passed, which overrides
           the default proxy-args-to-pySerial behavior. This is useful when testing,
           or wrapping the serial connection with some custom logic."""

        if "logger" in kwargs:
            self.logger = kwargs.pop("logger")
        
        mode = "PDU"
        if "mode" in kwargs:
            mode = kwargs.pop("mode")
        
        # if a ready-made device was provided, store it -- self.connect
        # will see that we're already connected, and do nothing. we'll
        # just assume it quacks like a serial port
        if "device" in kwargs:
            self.device = kwargs.pop("device")

            # if a device is given, the other args are never
            # used, so were probably included by mistake.
            if len(args) or len(kwargs):
                raise(TypeError("__init__() does not accept other arguments when a 'device' is given"))

        # for regular serial connections, store the connection args, since
        # we might need to recreate the serial connection again later
        else:
            self.device_args = args
            self.device_kwargs = kwargs

        # to cache parts of multi-part messages
        # until the last part is delivered
        self.multipart = {}

        # to store unhandled incoming messages
        self.incoming_queue = []
        
        if mode.lower() == "text":
            self.smshandler = TextSmsHandler(self)
        else:
            self.smshandler = PduSmsHandler(self)
        # boot the device on init, to fail as
        # early as possible if it can't be opened
        self.boot()
    
    
    LOG_LEVELS = {
        "traffic": 4,
        "read":    4,
        "write":   4,
        "debug":   3,
        "warn":    2,
        "error":   1 }
    
    
    def _log(self, str_, type_="debug"):
        """Proxies a log message to this Modem's logger, if one has been set.
           This is useful for applications embedding pyGSM that wish to show
           or log what's going on inside.

           The *logger* should be a function with three arguments:
             modem:   a reference to this GsmModem instance
             message: the log message (a unicode string)
             type:    a string contaning one of the keys
                      of GsmModem.LOG_LEVELS, indicating
                      the importance of this message.

           GsmModem.__init__ accepts an optional "logger" kwarg, and a minimal
           (dump to STDOUT) logger is available at GsmModem.logger:

           >>> GsmModem("/dev/ttyUSB0", logger=GsmModem.logger)"""
        
        if hasattr(self, "logger"):
            self.logger(self, str_, type_)
    
    
    @staticmethod
    def logger(_modem, message_, type_):
        print "%8s %s" % (type_, message_)
    
    
    def connect(self, reconnect=False):
        """Creates the connection to the modem via pySerial, optionally
           killing and re-creating any existing connection."""
           
        self._log("Connecting")
        
        # if no connection exists, create it
        # the reconnect flag is irrelevant
        if not hasattr(self, "device") or (self.device is None):
            with self.modem_lock:
                self.device = DeviceWrapper(
                    self.logger, *self.device_args,
                    **self.device_kwargs)
                
        # the port already exists, but if we're
        # reconnecting, then kill it and recurse
        # to recreate it. this is useful when the
        # connection has died, but nobody noticed
        elif reconnect:
            
            self.disconnect()
            self.connect(False)

        return self.device


    def disconnect(self):
        """Disconnects from the modem."""
        
        self._log("Disconnecting")
        
        # attempt to close and destroy the device
        if hasattr(self, "device") and (self.device is None):
            with self.modem_lock:
                if self.device.isOpen():
                    self.device.close()
                    self.device = None
                    return True
        
        # for some reason, the device
        # couldn't be closed. it probably
        # just isn't open yet
        return False


    def set_modem_config(self):
        """initialize the modem configuration with settings needed to process
           commands and send/receive SMS.
        """
        
        # set some sensible defaults, to make
        # the various modems more consistant
        self.command("ATE0",      raise_errors=False) # echo off
        self.command("AT+CMEE=1", raise_errors=False) # useful error messages
        self.command("AT+WIND=0", raise_errors=False) # disable notifications
        self.command("AT+CSMS=1", raise_errors=False) # set SMS mode to phase 2+
        self.command(self.smshandler.get_mode_cmd()      ) # make sure in PDU mode

        # enable new message notification
        self.command(
            "AT+CNMI=2,2,0,0,0",
            raise_errors=False)


    def boot(self, reboot=False):
        """Initializes the modem. Must be called after init and connect,
           but before doing anything that expects the modem to be ready."""
        
        self._log("Booting")
        
        if reboot:
            # If reboot==True, force a reconnection and full modem reset. SLOW
            self.connect(reconnect=True)
            self.command("AT+CFUN=1")
        else:
            # else just verify connection
            self.connect()

        # In both cases, reset the modem's config
        self.set_modem_config()        

        # And check for any waiting messages PRIOR to setting
        # the CNMI call--this is not supported by all modems--
        # in which case we catch the exception and plow onward
        try:
            self._fetch_stored_messages()
        except errors.GsmError:
            pass


    def reboot(self):
        """Forces a reconnect to the serial port and then a full modem reset to factory
           and reconnect to GSM network. SLOW.
        """
        self.boot(reboot=True)


    def _write(self, str):
        """Write a string to the modem."""
        
        self._log(repr(str), "write")

        try:
            self.device.write(str)

        # if the device couldn't be written to,
        # wrap the error in something that can
        # sensibly be caught at a higher level
        except OSError, err:
            raise(errors.GsmWriteError)

    def _parse_incoming_sms(self, lines):
        """Parse a list of lines (the output of GsmModem._wait), to extract any
           incoming SMS and append them to GsmModem.incoming_queue. Returns the
           same lines with the incoming SMS removed. Other unsolicited data may
           remain, which must be cropped separately."""

        output_lines = []
        n = 0

        # iterate the lines like it's 1984
        # (because we're patching the array,
        # which is hard work for iterators)
        while n < len(lines):

            # not a CMT string? add it back into the
            # output (since we're not interested in it)
            # and move on to the next
            if lines[n][0:5] != "+CMT:":
                output_lines.append(lines[n])
                n += 1
                continue

            msg_line = lines[n+1].strip()

            # notify the network that we accepted
            # the incoming message (for read receipt)
            # BEFORE pushing it to the incoming queue
            # (to avoid really ugly race condition if
            # the message is grabbed from the queue
            # and responded to quickly, before we get
            # a chance to issue at+cnma)
            try:
                self.command("AT+CNMA")

            # Some networks don't handle notification, in which case this
            # fails. Not a big deal, so ignore.
            except errors.GsmError:
                #self.log("Receipt acknowledgement (CNMA) was rejected")
                # TODO: also log this!
                pass

            msg = self.smshandler.parse_incoming_message(lines[n], msg_line)
            if msg is not None:
                self.incoming_queue.append(msg)

            # jump over the CMT line, and the
            # pdu line, and continue iterating
            n += 2
 
        # return the lines that we weren't
        # interested in (almost all of them!)
        return output_lines
        
    def command(self, cmd, read_term=None, read_timeout=None, write_term="\r", raise_errors=True):
        """Issue a single AT command to the modem, and return the sanitized
           response. Sanitization removes status notifications, command echo,
           and incoming messages, (hopefully) leaving only the actual response
           from the command.
           
           If Error 515 (init or command in progress) is returned, the command
           is automatically retried up to _GsmModem.max_retries_ times."""

        # keep looping until the command
        # succeeds or we hit the limit
        retries = 0
        while retries < self.max_retries:
            try:

                # issue the command, and wait for the
                # response
                with self.modem_lock:
                    self._write(cmd + write_term)
                    lines = self.device.read_lines(
                        read_term=read_term,
                        read_timeout=read_timeout)
                    
                # no exception was raised, so break
                # out of the enclosing WHILE loop
                break

            # Outer handler: if the command caused an error,
            # maybe wrap it and return None
            except errors.GsmError, err:
                # if GSM Error 515 (init or command in progress) was raised,
                # lock the thread for a short while, and retry. don't lock
                # the modem while we're waiting, because most commands WILL
                # work during the init period - just not _cmd_
                if getattr(err, "code", None) == 515:
                    time.sleep(self.retry_delay)
                    retries += 1
                    continue

                # if raise_errors is disabled, it doesn't matter
                # *what* went wrong - we'll just ignore it
                if not raise_errors:
                    return None

                # otherwise, allow errors to propagate upwards,
                # and hope someone is waiting to catch them
                else: 
                    raise(err)

        # if the first line of the response echoes the cmd
        # (it shouldn't, if ATE0 worked), silently drop it
        if lines[0] == cmd:
            lines.pop(0)

        # remove all blank lines and unsolicited
        # status messages. i can't seem to figure
        # out how to reliably disable them, and
        # AT+WIND=0 doesn't work on this modem
        lines = [
            line
            for line in lines
            if line      != "" or\
               line[0:6] == "+WIND:" or\
               line[0:6] == "+CREG:" or\
               line[0:7] == "+CGRED:"]

        # parse out any incoming sms that were bundled
        # with this data (to be fetched later by an app)
        lines = self._parse_incoming_sms(lines)

        # rest up for a bit (modems are
        # slow, and get confused easily)
        time.sleep(self.cmd_delay)

        return lines


    def query(self, cmd, prefix=None):
        """Issues a single AT command to the modem, and returns the relevant
           part of the response. This only works for commands that return a
           single line followed by "OK", but conveniently, this covers almost
           all AT commands that I've ever needed to use.

           For all other commands, returns None."""

        # issue the command, which might return incoming
        # messages, but we'll leave them in the queue
        out = self.command(cmd)

        # the only valid response to a "query" is a
        # single line followed by "OK". if all looks
        # well, return just the single line
        if(len(out) == 2) and (out[-1] == "OK"):
            if prefix is None:
                return out[0].strip()

            # if a prefix was provided, check that the
            # response starts with it, and return the
            # cropped remainder
            else:
                if out[0][:len(prefix)] == prefix:
                    return out[0][len(prefix):].strip()

        # something went wrong, so return the very
        # ambiguous None. it's better than blowing up
        return None


    def send_sms(self, recipient, text):
        """
        Sends an SMS to _recipient_ containing _text_. 

        Method will automatically split long 'text' into
        multiple SMSs up to max_messages.

        To enforce only a single SMS, set max_messages=1

        Raises 'ValueError' if text will not fit in max_messages

        """
        with self.modem_lock:
            self.smshandler.send_sms(recipient, text)

    def break_out_of_prompt(self):
        self._write(chr(27))

    def hardware(self):
        """Returns a dict of containing information about the physical
           modem. The contents of each value are entirely manufacturer
           dependant, and vary wildly between devices."""

        return {
            "manufacturer": self.query("AT+CGMI"),
            "model":        self.query("AT+CGMM"),
            "revision":     self.query("AT+CGMR"),
            "serial":       self.query("AT+CGSN") }


    def signal_strength(self):
        """Returns an integer between 1 and 99, representing the current
           signal strength of the GSM network, False if we don't know, or
           None if the modem can't report it."""

        data = self.query("AT+CSQ")
        md = re.match(r"^\+CSQ: (\d+),", data)

        # 99 represents "not known or not detectable". we'll
        # return False for that (so we can test it for boolean
        # equality), or an integer of the signal strength.
        if md is not None:
            csq = int(md.group(1))
            return csq if csq < 99 else False

        # the response from AT+CSQ couldn't be parsed. return
        # None, so we can test it in the same way as False, but
        # check the type without raising an exception
        return None


    def wait_for_network(self):
        """Blocks until the signal strength indicates that the
           device is active on the GSM network. It's a good idea
           to call this before trying to send or receive anything."""

        while True:
            csq = self.signal_strength()
            if csq: return csq
            time.sleep(1)


    def ping(self):
        """Sends the "AT" command to the device, and returns true
           if it is acknowledged. Since incoming notifications and
           messages are intercepted automatically, this is a good
           way to poll for new messages without using a worker
           thread like RubyGSM."""

        try:
            self.command("AT")
            return True

        except errors.GsmError:
            return None


    def _strip_ok(self,lines):
        """Strip 'OK' from end of command response"""
        if lines is not None and len(lines)>0 and \
                lines[-1]=='OK':
            lines=lines[:-1] # strip last entry
        return lines


    def _fetch_stored_messages(self):
        """
        Fetch stored messages with CMGL and add to incoming queue
        Return number fetched
        
        """    
        lines = self.command('AT+CMGL=%s' % self.smshandler.CMGL_STATUS)
        lines = self._strip_ok(lines)
        messages = self.smshandler.parse_stored_messages(lines)
        for msg in messages:
            self.incoming_queue.append(msg)

    def next_message(self, ping=True, fetch=True):
        """Returns the next waiting IncomingMessage object, or None if the
           queue is empty. The optional _ping_ and _fetch_ parameters control
           whether the modem is pinged (to allow new messages to be delivered
           instantly, on those modems which support it) and queried for unread
           messages in storage, which can both be disabled in case you're
           already polling in a separate thread."""

        # optionally ping the modem, to give it a
        # chance to deliver any waiting messages
        if ping:
            self.ping()

        # optionally check the storage for unread messages.
        # we must do this just as often as ping, because most
        # handsets don't support CNMI-style delivery
        if fetch:
            self._fetch_stored_messages()

        # abort if there are no messages waiting
        if not self.incoming_queue:
            return None

        # remove the message that has been waiting
        # longest from the queue, and return it
        return self.incoming_queue.pop(0)


if __name__ == "__main__":

    import sys
    if len(sys.argv) >= 2:

        # the first argument is SERIAL PORT
        # (required, since we have no autodetect yet)
        port = sys.argv[1]

        # all subsequent options are parsed as key=value
        # pairs, to be passed on to GsmModem.__init__ as
        # kwargs, to configure the serial connection
        conf = dict([
            arg.split("=", 1)
            for arg in sys.argv[2:]
            if arg.find("=") > -1
        ])

        # dump the connection settings
        print "pyGSM Demo App"
        print "  Port: %s" % (port)
        print "  Config: %r" % (conf)
        print

        # connect to the modem (this might hang
        # if the connection settings are wrong)
        print "Connecting to GSM Modem..."
        modem = GsmModem(port=port, **conf)
        print "Waiting for incoming messages..."

        # check for new messages every two
        # seconds for the rest of forever
        while True:
            msg = modem.next_message()

            # we got a message! respond with
            # something useless, as an example
            if msg is not None:
                print "Got Message: %r" % msg
                msg.respond("Received: %d characters '%s'" %
                    (len(msg.text),msg.text))

            # no messages? wait a couple
            # of seconds and try again
            else: 
                time.sleep(2)

    # the serial port must be provided
    # we're not auto-detecting, yet
    else:
        print "Usage: python -m pygsm.gsmmodem PORT [OPTIONS]"
