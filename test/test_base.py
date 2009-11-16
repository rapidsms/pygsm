#!/usr/bin/env python
# vim: ai ts=4 sts=4 et sw=4


import unittest
import pygsm
import mox

class TestBase(unittest.TestCase):
    mode_map = { 
                'text': 1,
                'pdu': 0 
                }
    
    cmgl_map = {
                'text': '"REC UNREAD"',
                'pdu':'0'
                }
    
    # Some useful constants for the tests
    read_time_out = pygsm.errors.GsmReadTimeoutError(">") 
    rl_args={'read_timeout': mox.IgnoreArg(),
                      'read_term': mox.IgnoreArg()}
    ok = ["","OK"]
    
    def get_mode(self):
        """
        Subclass overrides this to return 'TEXT' or 'PDU'
        
        """
        return None
    
    def setUp(self):
        self.mocker = mox.Mox()
        self.mockDevice = self.mocker.CreateMock(pygsm.devicewrapper.DeviceWrapper)
        
        # verify the config commands
        self.mockDevice.write("ATE0\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        
        self.mockDevice.write("AT+CMEE=1\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
       
        self.mockDevice.write("AT+WIND=0\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        
        self.mockDevice.write("AT+CSMS=1\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
         
        # must see command to set PDU mode
        mode_int = self.mode_map[self.get_mode().lower()]
        self.mockDevice.write("AT+CMGF=%d\r" % mode_int)
                              
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        
        self.mockDevice.write("AT+CNMI=2,2,0,0,0\r")
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        
        # verify fetch_stored_messages in boot
        cmgl_str = self.cmgl_map[self.get_mode().lower()]
        self.mockDevice.write("AT+CMGL=%s\r" % cmgl_str)
        self.mockDevice.read_lines(**self.rl_args).AndReturn(self.ok)
        
        self.mocker.ReplayAll()
        self.gsm = pygsm.GsmModem(device=self.mockDevice, mode=self.get_mode())
        
#        self.mocker.VerifyAll()
        self.mocker.ResetAll()
        