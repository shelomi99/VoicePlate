#!/usr/bin/env python3
"""
Test Realtime Setup
Validates the VoicePlate Realtime API integration setup.
"""

import asyncio
import logging
import requests
import websockets
import json
import time
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class RealtimeSetupTester:
    """Test suite for Realtime API setup."""
    
    def __init__(self):
        self.webhook_url = f"http://{settings.host}:{settings.port}"
        self.websocket_url = f"ws://{settings.host}:{settings.port + 1000}"
        self.test_results = {}
        
    def run_all_tests(self):
        """Run all validation tests."""
        logger.info("🧪 Starting VoicePlate Realtime Setup Tests")
        logger.info("=" * 60)
        
        # Configuration tests
        self.test_configuration()
        
        # Server connectivity tests
        asyncio.run(self.test_server_connectivity())
        
        # WebSocket tests
        asyncio.run(self.test_websocket_connection())
        
        # Integration tests
        self.test_webhook_integration()
        
        # Print summary
        self.print_test_summary()
        
        return all(self.test_results.values())

    def test_configuration(self):
        """Test configuration validity."""
        logger.info("🔧 Testing Configuration...")
        
        config_tests = {
            'openai_api_key': bool(settings.openai_api_key),
            'twilio_credentials': bool(settings.twilio_account_sid and settings.twilio_auth_token),
            'realtime_enabled': settings.use_realtime_api,
            'realtime_model': bool(settings.openai_realtime_model),
            'audio_format': settings.realtime_input_audio_format == 'g711_ulaw',
            'webhook_url': bool(getattr(settings, 'base_webhook_url', None))
        }
        
        for test_name, result in config_tests.items():
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"   {test_name}: {status}")
            self.test_results[f"config_{test_name}"] = result
        
        logger.info("✅ Configuration tests completed\n")

    async def test_server_connectivity(self):
        """Test server connectivity."""
        logger.info("🌐 Testing Server Connectivity...")
        
        # Test webhook server
        webhook_reachable = await self._test_webhook_health()
        self.test_results['webhook_reachable'] = webhook_reachable
        
        # Test WebSocket server
        websocket_reachable = await self._test_websocket_health()
        self.test_results['websocket_reachable'] = websocket_reachable
        
        logger.info("✅ Server connectivity tests completed\n")

    async def _test_webhook_health(self):
        """Test webhook server health endpoint."""
        try:
            response = requests.get(f"{self.webhook_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"   📞 Webhook Health: ✅ PASS ({data.get('status', 'unknown')})")
                return True
            else:
                logger.info(f"   📞 Webhook Health: ❌ FAIL (Status: {response.status_code})")
                return False
        except Exception as e:
            logger.info(f"   📞 Webhook Health: ❌ FAIL ({str(e)})")
            return False

    async def _test_websocket_health(self):
        """Test WebSocket server health endpoint."""
        try:
            response = requests.get(f"http://{settings.host}:{settings.port + 1000}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"   🎧 WebSocket Health: ✅ PASS ({data.get('status', 'unknown')})")
                return True
            else:
                logger.info(f"   🎧 WebSocket Health: ❌ FAIL (Status: {response.status_code})")
                return False
        except Exception as e:
            logger.info(f"   🎧 WebSocket Health: ❌ FAIL ({str(e)})")
            return False

    async def test_websocket_connection(self):
        """Test WebSocket connection capability."""
        logger.info("🔌 Testing WebSocket Connection...")
        
        websocket_url = f"{self.websocket_url}/ws/media"
        
        try:
            # Test connection establishment
            async with websockets.connect(websocket_url, timeout=5) as websocket:
                logger.info("   🎧 WebSocket Connection: ✅ PASS (Connected successfully)")
                
                # Test message sending
                test_message = {
                    "event": "start",
                    "callSid": "test_call_sid",
                    "streamSid": "test_stream_sid",
                    "accountSid": "test_account_sid"
                }
                
                await websocket.send(json.dumps(test_message))
                logger.info("   📤 Message Send: ✅ PASS (Test message sent)")
                
                # Wait for potential response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2)
                    logger.info("   📥 Message Receive: ✅ PASS (Response received)")
                except asyncio.TimeoutError:
                    logger.info("   📥 Message Receive: ⚠️  TIMEOUT (No response within 2s)")
                
                self.test_results['websocket_connection'] = True
                
        except Exception as e:
            logger.info(f"   🎧 WebSocket Connection: ❌ FAIL ({str(e)})")
            self.test_results['websocket_connection'] = False
        
        logger.info("✅ WebSocket connection tests completed\n")

    def test_webhook_integration(self):
        """Test webhook TwiML generation."""
        logger.info("📞 Testing Webhook Integration...")
        
        # Simulate Twilio webhook call
        test_data = {
            'CallSid': 'test_call_sid_123',
            'From': '+1234567890',
            'To': '+0987654321',
            'CallStatus': 'in-progress'
        }
        
        try:
            response = requests.post(
                f"{self.webhook_url}/voice",
                data=test_data,
                timeout=5
            )
            
            if response.status_code == 200:
                # Check if response contains valid TwiML
                twiml_content = response.text
                
                # Validate TwiML structure
                if '<Response>' in twiml_content and '<Connect>' in twiml_content:
                    logger.info("   📞 TwiML Generation: ✅ PASS (Valid TwiML returned)")
                    
                    # Check for Media Stream configuration
                    if 'Stream' in twiml_content and 'ws://' in twiml_content:
                        logger.info("   🎧 Media Stream Config: ✅ PASS (WebSocket URL included)")
                        self.test_results['webhook_integration'] = True
                    else:
                        logger.info("   🎧 Media Stream Config: ❌ FAIL (No WebSocket configuration)")
                        self.test_results['webhook_integration'] = False
                else:
                    logger.info("   📞 TwiML Generation: ❌ FAIL (Invalid TwiML structure)")
                    self.test_results['webhook_integration'] = False
            else:
                logger.info(f"   📞 Webhook Response: ❌ FAIL (Status: {response.status_code})")
                self.test_results['webhook_integration'] = False
                
        except Exception as e:
            logger.info(f"   📞 Webhook Integration: ❌ FAIL ({str(e)})")
            self.test_results['webhook_integration'] = False
        
        logger.info("✅ Webhook integration tests completed\n")

    def print_test_summary(self):
        """Print test results summary."""
        logger.info("📊 TEST SUMMARY")
        logger.info("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result)
        failed_tests = total_tests - passed_tests
        
        logger.info(f"   Total Tests: {total_tests}")
        logger.info(f"   Passed: {passed_tests}")
        logger.info(f"   Failed: {failed_tests}")
        logger.info(f"   Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests == 0:
            logger.info("\n🎉 ALL TESTS PASSED! Your realtime setup is ready.")
            self._print_next_steps()
        else:
            logger.info("\n⚠️  SOME TESTS FAILED. Please review the issues above.")
            self._print_troubleshooting()
        
        logger.info("=" * 60)

    def _print_next_steps(self):
        """Print next steps for successful setup."""
        logger.info("\n🚀 NEXT STEPS:")
        logger.info("   1. Start servers: python run_realtime_server.py")
        logger.info("   2. Expose with ngrok: ngrok http 5001")
        logger.info("   3. Update Twilio webhook URL")
        logger.info("   4. Make a test call!")

    def _print_troubleshooting(self):
        """Print troubleshooting information."""
        logger.info("\n🔧 TROUBLESHOOTING:")
        
        if not self.test_results.get('webhook_reachable', True):
            logger.info("   • Webhook server not reachable - start the realtime server")
        
        if not self.test_results.get('websocket_reachable', True):
            logger.info("   • WebSocket server not reachable - check FastAPI server")
        
        if not self.test_results.get('config_openai_api_key', True):
            logger.info("   • Missing OpenAI API key - set OPENAI_API_KEY")
        
        if not self.test_results.get('config_twilio_credentials', True):
            logger.info("   • Missing Twilio credentials - set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")

def main():
    """Run the test suite."""
    print("🧪 VoicePlate Realtime Setup Test Suite")
    print("=" * 60)
    
    tester = RealtimeSetupTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n✅ Setup validation completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Setup validation failed. Please review the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main() 