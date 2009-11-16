#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4


import unittest
from test_base import TestBase

class PduModeTest(TestBase):
  
    def get_mode(self):
        return 'PDU'
    
    def testSendSmsPduMode(self):
        """Checks that the GsmModem in PDU mode accepts outgoing SMS,
           when the text is within ASCII chars 22 - 126."""
        
        # setup expectation to raise a timeout error with prompt
        self.mockDevice.write("AT+CMGS=21\r").AndRaise(self.read_time_out)
        self.mockDevice.write("00110004A821430000AA0CD4F29C0E6A96E7F3F0B90C\x1a")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        self.mocker.ReplayAll()
        self.gsm.send_sms("1234", "Test Message")
       
        self.mocker.VerifyAll()
      
    def testSendSmsPduModeError(self):
        """
        Checks that the GsmModem in PDU mode does not send message if error,
        when the text is within ASCII chars 22 - 126.
        
        """

        # setup expectation to raise a non-timeout error with prompt
        self.mockDevice.write("AT+CMGS=21\r").AndRaise(Exception("not timeout"))
        # must see command to break out of command prompt
        self.mockDevice.write("\x1b")
        self.mocker.ReplayAll()
        self.gsm.send_sms("1234", "Test Message")
       
        # must NOT see command (or anything else) with text and terminating char
        self.mocker.VerifyAll()
        
    def testShouldParseIncomingSms(self):
        # verify that ping command AT is issued
        self.mockDevice.write("AT\r")   

        lines = [
                 "+CMT:",
                 "07912180958729F6040B814151733717F500009070102230438A02D937",
                 ] + self.ok
        
        self.mockDevice.read_lines(**self.rl_args).AndReturn(lines)
        # verify that command is issued for read receipt
        self.mockDevice.write("AT+CNMA\r")
        # allow any number of reads
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)

        self.mocker.ReplayAll()
        pdu = self.gsm.next_message(ping=True,fetch=False)
        self.assertEquals("Yo", pdu.text);
        self.assertEquals("14153773715", pdu.sender);
        self.mocker.VerifyAll()
    
    def testShouldParseIncomingSmsHelloInChinese(self): 
        lines = [
                "+CMT:",
                "07912180958729F8040B814151733717F500089090035194358A044F60597D",
                ] + self.ok
        self.mockDevice.write("AT\r")  
        self.mockDevice.read_lines(**self.rl_args).AndReturn(lines)
        
        # verify that command is issued for read receipt
        self.mockDevice.write("AT+CNMA\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        

        self.mocker.ReplayAll()
        pdu = self.gsm.next_message(ping=True,fetch=False)

        self.assertEquals(u'\u4f60\u597d', pdu.text);
        self.assertEquals("14153773715", pdu.sender);
        self.mocker.VerifyAll()
        
    def testShouldReturnEmptyIfNoStoredMessages(self):
        self.mockDevice.write("AT+CMGL=0\r") 
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        self.mocker.ReplayAll()
        self.assertEquals(None, self.gsm.next_message(ping=False, fetch=True));
        self.mocker.VerifyAll()
        
    def testShouldReturnStoredMessage(self):
        lines = [
                 "+CMGL:",
                 "07912180958729F6040B814151733717F500009070102230438A02D937",
                 ] + self.ok
        self.mockDevice.write("AT+CMGL=0\r") 
        self.mockDevice.read_lines(**self.rl_args).AndReturn(lines)
        self.mocker.ReplayAll()
        pdu = self.gsm.next_message(ping=False,fetch=True)
        self.assertEquals("Yo", pdu.text);
        self.assertEquals("14153773715", pdu.sender);
        # allow any number of reads
        self.mocker.VerifyAll()

    def testShouldHandleMultipartCSMPdus(self):
        lines = [
                 "+CMGL:",
                 "0791448720003023440C91449703529096000050015132532240A00500037A020190E9339A9D3EA3E920FA1B1466B341E472193E079DD3EE73D85DA7EB41E7B41C1407C1CBF43228CC26E3416137390F3AABCFEAB3FAAC3EABCFEAB3FAAC3EABCFEAB3FAAC3EABCFEAB3FADC3EB7CFED73FBDC3EBF5D4416D9457411596457137D87B7E16438194E86BBCF6D16D9055D429548A28BE822BA882E6370196C2A8950E291E822BA88",
                 "0791448720003023440C91449703529096000050015132537240310500037A02025C4417D1D52422894EE5B17824BA8EC423F1483C129BC725315464118FCDE011247C4A8B44"
                 ] + self.ok
        self.mockDevice.write("AT+CMGL=0\r") 
        self.mockDevice.read_lines(**self.rl_args).AndReturn(lines)
        self.mocker.ReplayAll()
        pdu = self.gsm.next_message(ping=False,fetch=True)
        self.assertEquals("Highlight to all deeps ginganutz gir q pete aldx andy gjgjgjgjgjgjgjgjgjgjgjgjgjgjgjgmgmgmgmgmgo.D,d.D.D,d.Mhwpmpdpdpdpngm,d.PKPJHD.D.D.D.FAKAMJDPDGD.D.D.D.D.MDHDNJGEGD.GDGDGDGDMGKD!E,DGMAG BORED", pdu.text);
      
        self.mocker.VerifyAll()

    def testShouldNotCreateMessageIfAllPartsOfCsmPduAreNotReceived(self):
        lines = [
                 "+CMGL:",
                 "07912180958729F6400B814151733717F500009070208044148AA0050003160201986FF719C47EBBCF20F6DB7D06B1DFEE3388FD769F41ECB7FB0C62BFDD6710FBED3E83D8ECB73B0D62BFDD67109BFD76A741613719C47EBBCF20F6DB7D06BCF61BC466BF41ECF719C47EBBCF20F6D"
                ] + self.ok
        self.mockDevice.write("AT+CMGL=0\r") 
        self.mockDevice.read_lines(**self.rl_args).AndReturn(lines)
        self.mocker.ReplayAll()
        pdu = self.gsm.next_message(ping=False,fetch=True)
        self.assertEquals(None, pdu)
      
        self.mocker.VerifyAll()
        
if __name__ == "__main__":
    unittest.main()
    