#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4 encoding=utf-8

# arch: pacman -S python-pyserial
# debian/ubuntu: apt-get install python-serial
import serial
import re
import errors

class DeviceWrapper(object):
    
    def __init__(self, logger, *args, **kwargs):
        self.device = serial.Serial(*args, **kwargs)
        self.logger = logger

    def isOpen(self):
        return self.device.isOpen()

    def close(self):
        self.device.close()
    
    def write(self, str):
        self.device.write(str)
            
    def _read(self, read_term=None, read_timeout=None):
        """Read from the modem (blocking) until _terminator_ is hit,
           (defaults to \r\n, which reads a single "line"), and return."""
        
        buffer = []

        # if a different timeout was requested just
        # for _this_ read, store and override the
        # current device setting (not thread safe!)
        if read_timeout is not None:
            old_timeout = self.device.timeout
            self.device.timeout = read_timeout

        def __reset_timeout():
            """restore the device's previous timeout
               setting, if we overrode it earlier."""
            if read_timeout is not None:
                self.device.timeout =\
                    old_timeout

        # the default terminator reads
        # until a newline is hit
        if read_term is None:
            read_term = "\r\n"

        while(True):
            buf = self.device.read()
            buffer.append(buf)            
            # if a timeout was hit, raise an exception including the raw data that
            # we've already read (in case the calling func was _expecting_ a timeout
            # (wouldn't it be nice if serial.Serial.read returned None for this?)
            if buf == '':
                __reset_timeout()
                raise(errors.GsmReadTimeoutError(buffer))

            # if last n characters of the buffer match the read
            # terminator, return what we've received so far
            if ''.join(buffer[-len(read_term):]) == read_term:
                buf_str = ''.join(buffer)
                __reset_timeout()

                self._log(repr(buf_str), 'read')
                return buf_str


    def read_lines(self, read_term=None, read_timeout=None):
        """Read from the modem (blocking) one line at a time until a response
           terminator ("OK", "ERROR", or "CMx ERROR...") is hit, then return
           a list containing the lines."""
        buffer = []

        # keep on looping until a command terminator
        # is encountered. these are NOT the same as the
        # "read_term" argument - only OK or ERROR is valid
        while(True):
            buf = self._read(
                read_term=read_term,
                read_timeout=read_timeout)

            buf = buf.strip()
            buffer.append(buf)

            # most commands return OK for success, but there
            # are some exceptions. we're not checking those
            # here (unlike RubyGSM), because they should be
            # handled when they're _expected_
            if buf == "OK":
                return buffer

            # some errors contain useful error codes, so raise a
            # proper error with a description from pygsm/errors.py
            m = re.match(r"^\+(CM[ES]) ERROR: (\d+)$", buf)
            if m is not None:
                type, code = m.groups()
                raise(errors.GsmModemError(type, int(code)))

            # ...some errors are not so useful
            # (at+cmee=1 should enable error codes)
            if buf == "ERROR":
                raise(errors.GsmModemError)

    def _log(self, str, type="debug"):
        if hasattr(self, "logger"):
            self.logger(self, str, type)    