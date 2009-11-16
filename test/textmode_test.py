#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4


import unittest
import datetime

from pygsm import errors
from test_base import TestBase

class SendSmsTextModeTest(TestBase):  
    def get_mode(self):
        return 'TEXT'
        
    def testSendSmsTextMode(self):
        """Checks that the GsmModem in Text mode accepts outgoing SMS,
           when the text is within ASCII chars 22 - 126."""        

        self.mockDevice.write("AT+CMGS=\"1234\"\r").AndRaise(self.read_time_out)
        self.mockDevice.write("Test Message\x1a")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        self.mocker.ReplayAll()
        self.gsm.send_sms("1234", "Test Message")

        self.mocker.VerifyAll()
 
    """    
    def testSendSmsTextModeWithHexUTF16Encoding(self):
        #Checks that the GsmModem in Text mode accepts outgoing SMS,
        #  when the text has Non-ASCII
        
        csmp_response_lines = []
        csmp_response_lines.append("+CSMP:1,2,3,4")
        csmp_response_lines.append("OK")
        err = errors.GsmReadTimeoutError(">")
        when(self.mockDevice).read_lines().thenReturn(csmp_response_lines).thenReturn(self.oklines).thenReturn(self.oklines).thenRaise(err).thenReturn(self.oklines)
        self.gsm.send_sms("1234", u'La Pe\xf1a')
        
        verify(self.mockDevice, times=1).write("AT+CSMP?\r")
        verify(self.mockDevice, times=1).write("AT+CSCS=\"HEX\"\r")
        verify(self.mockDevice, times=1).write("AT+CSMP=1,2,3,8\r")
        
        # must see command with recipient
        verify(self.mockDevice, times=1).write("AT+CMGS=\"1234\"\r")
        # must see command with encoded text and terminating char
        verify(self.mockDevice, times=1).write("fffe4c006100200050006500f1006100\x1a")
        # command to set mode back 
        verify(self.mockDevice, times=1).write("AT+CSMP=1,2,3,4\r")
        verify(self.mockDevice, times=1).write("AT+CSCS=\"GSM\"\r")
        # allow any number of reads
        verify(self.mockDevice, atleast=1).read_lines()
        verifyNoMoreInteractions(self.mockDevice)
    """
        
    def testShouldReturnStoredMessage(self):
        lines = [
                 '+CMGL: 1,"status","14153773715",,"09/09/11,10:10:10"',
                 'Yo'
                 ] + self.ok
        self.mockDevice.write('AT+CMGL="REC UNREAD"\r')        
        self.mockDevice.read_lines(**self.rl_args).AndReturn(lines)
        self.mocker.ReplayAll()
        
        msg = self.gsm.next_message(ping=False)
        self.assertEquals("Yo", msg.text);
        self.assertEquals("14153773715", msg.sender)
        self.assertEquals(datetime.datetime(2009, 9, 11, 10, 10, 10), msg.sent)
        # verify command to fetch_stored_messages
       
        self.mocker.VerifyAll()

    """
    def testShouldReturnHexUTF16EncodedStoredMessage(self):
        lines = []
        lines.append("+CMGL: 1,\"status\",\"14153773715\",,\"09/09/11,10:10:10\"")
        lines.append("Yo".encode("utf-16").encode("hex"))
        when(self.mockDevice).read_lines().thenReturn(lines)
        msg = self.gsm.next_message(ping=False)
        self.assertEquals("Yo", msg.text);
        self.assertEquals("14153773715", msg.sender)
        self.assertEquals(datetime.datetime(2009, 9, 11, 10, 10, 10), msg.sent)
        # verify command to fetch_stored_messages
        verify(self.mockDevice,times=2).write("AT+CMGL=\"REC UNREAD\"\r")
        # allow any number of reads
        verify(self.mockDevice, atleast=1).read_lines()
        
        verifyNoMoreInteractions(self.mockDevice)
    """
    
    def testShouldParseIncomingSms(self):
        lines = [
                 '+CMT: "14153773715",,"09/09/11,10:10:10"',
                 'Yo'
                ] + self.ok

        self.mockDevice.write("AT\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(lines)
        self.mockDevice.write("AT+CNMA\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        self.mocker.ReplayAll()
        
        msg = self.gsm.next_message(ping=True,fetch=False)        
        self.assertEquals("Yo", msg.text);
        self.assertEquals("14153773715", msg.sender);
        self.assertEquals(datetime.datetime(2009, 9, 11, 10, 10, 10), msg.sent);
       
        self.mocker.VerifyAll()
    
    def testShouldParseIncomingSmsWithMangledHeader(self):
        lines = [
                 '+CMT: "14153773715",',
                 'Yo'
                ] + self.ok
 
        self.mockDevice.write("AT\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(lines)
        self.mockDevice.write("AT+CNMA\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        self.mocker.ReplayAll()
        
        msg = self.gsm.next_message(ping=True,fetch=False) 

        self.assertEquals("Yo", msg.text);
        self.assertEquals("", msg.sender);
        self.assertEquals(None, msg.sent);
        
        self.mocker.VerifyAll()
    
    
    def testShouldParseIncomingMultipartSms(self):
        header = '+CMT: "14153773715",,"09/09/11,10:10:10"'
                 
        # first part of multi-part msg
        lines = [header]
        lines.append(chr(130) + "@" + "ignorfirstpartofmultipart")
        # second part of multi-part msg
        lines.append(header)
        lines.append(chr(130) + "@" + "345" + chr(173) + "7secondpartofmultipart")
        lines.append(self.ok)
        self.mockDevice.write("AT\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(lines)
        self.mockDevice.write("AT+CNMA\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        self.mockDevice.write("AT+CNMA\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        self.mocker.ReplayAll()
        
        msg = self.gsm.next_message(ping=True,fetch=False)
       
        self.assertEquals("firstpartofmultipartsecondpartofmultipart", msg.text);
        self.assertEquals("14153773715", msg.sender);
        self.assertEquals(datetime.datetime(2009, 9, 11, 10, 10, 10), msg.sent);
       
        self.mocker.VerifyAll()
        

if __name__ == "__main__":
    unittest.main()