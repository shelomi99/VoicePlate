#!/usr/bin/env python3
"""
Test Unified Realtime Setup
Validates the VoicePlate Unified Realtime Server setup.
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

class UnifiedSetupTester:
    """Test suite for Unified Realtime Server setup."""
    
    def __init__(self):
        self.server_url = f"http://{settings.host}:{settings.port}"
        self.websocket_url = f"ws://{settings.host}:{settings.port}"
        self.test_results = {}
        
    def run_all_tests(self):
        """Run all validation tests."""
        logger.info("🧪 Starting VoicePlate Unified Server Tests")
        logger.info("=" * 60)
        
        # Configuration tests
        self.test_configuration()
        
        # Server connectivity tests
        asyncio.run(self.test_server_connectivity())
        
        # Endpoint tests
        self.test_all_endpoints()
        
        # WebSocket tests
        asyncio.run(self.test_websocket_connection())
        
        # Integration tests
        self.test_webhook_integration()
        
        # Print summary
        self.print_test_summary()
        
        return all(self.test_results.values())

    def test_configuration(self):
        """Test configuration validity for unified server."""
        logger.info("🔧 Testing Unified Server Configuration...")
        
        config_tests = {
            'openai_api_key': bool(settings.openai_api_key),
            'twilio_credentials': bool(settings.twilio_account_sid and settings.twilio_auth_token),
            'realtime_enabled': settings.use_realtime_api,
            'realtime_model': bool(settings.openai_realtime_model),
            'audio_format': settings.realtime_input_audio_format == 'g711_ulaw',
            'single_port': True,  # Unified server uses single port
            'fastapi_only': True  # No Flask dependency
        }
        
        for test_name, result in config_tests.items():
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"   {test_name}: {status}")
            self.test_results[f"config_{test_name}"] = result
        
        logger.info("✅ Configuration tests completed\n")

    async def test_server_connectivity(self):
        """Test unified server connectivity."""
        logger.info("🌐 Testing Unified Server Connectivity...")
        
        # Test root endpoint
        root_reachable = self._test_root_endpoint()
        self.test_results['root_reachable'] = root_reachable
        
        # Test health endpoint
        health_reachable = self._test_health_endpoint()
        self.test_results['health_reachable'] = health_reachable
        
        # Test status endpoint
        status_reachable = self._test_status_endpoint()
        self.test_results['status_reachable'] = status_reachable
        
        logger.info("✅ Server connectivity tests completed\n")

    def _test_root_endpoint(self):
        """Test root endpoint of unified server."""
        try:
            response = requests.get(f"{self.server_url}/", timeout=5)
            if response.status_code == 200:
                data = response.json()
                service = data.get('service', '')
                architecture = data.get('architecture', '')
                
                if 'Unified' in service and 'no Flask' in architecture:
                    logger.info(f"   🏠 Root Endpoint: ✅ PASS (Unified architecture confirmed)")
                    return True
                else:
                    logger.info(f"   🏠 Root Endpoint: ❌ FAIL (Not unified architecture)")
                    return False
            else:
                logger.info(f"   🏠 Root Endpoint: ❌ FAIL (Status: {response.status_code})")
                return False
        except Exception as e:
            logger.info(f"   🏠 Root Endpoint: ❌ FAIL ({str(e)})")
            return False

    def _test_health_endpoint(self):
        """Test health endpoint of unified server."""
        try:
            response = requests.get(f"{self.server_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                service = data.get('service', '')
                version = data.get('version', '')
                
                if 'Unified' in service or version == '2.0.0':
                    logger.info(f"   🔧 Health Endpoint: ✅ PASS ({data.get('status', 'unknown')})")
                    return True
                else:
                    logger.info(f"   🔧 Health Endpoint: ❌ FAIL (Not unified server)")
                    return False
            else:
                logger.info(f"   🔧 Health Endpoint: ❌ FAIL (Status: {response.status_code})")
                return False
        except Exception as e:
            logger.info(f"   🔧 Health Endpoint: ❌ FAIL ({str(e)})")
            return False

    def _test_status_endpoint(self):
        """Test status endpoint of unified server."""
        try:
            response = requests.get(f"{self.server_url}/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                endpoints = data.get('endpoints', {})
                
                # Check if all expected endpoints are present
                expected_endpoints = ['voice_webhook', 'websocket', 'health', 'status', 'docs']
                if all(endpoint in endpoints for endpoint in expected_endpoints):
                    logger.info(f"   📊 Status Endpoint: ✅ PASS (All endpoints present)")
                    return True
                else:
                    logger.info(f"   📊 Status Endpoint: ❌ FAIL (Missing endpoints)")
                    return False
            else:
                logger.info(f"   📊 Status Endpoint: ❌ FAIL (Status: {response.status_code})")
                return False
        except Exception as e:
            logger.info(f"   📊 Status Endpoint: ❌ FAIL ({str(e)})")
            return False

    def test_all_endpoints(self):
        """Test all endpoints are accessible."""
        logger.info("🔗 Testing All Endpoints...")
        
        endpoints_to_test = {
            '/': 'GET',
            '/health': 'GET',
            '/status': 'GET',
            '/docs': 'GET',
            '/docs-info': 'GET'
        }
        
        all_passed = True
        
        for endpoint, method in endpoints_to_test.items():
            try:
                if method == 'GET':
                    response = requests.get(f"{self.server_url}{endpoint}", timeout=5)
                    
                if response.status_code == 200:
                    logger.info(f"   {method} {endpoint}: ✅ PASS")
                else:
                    logger.info(f"   {method} {endpoint}: ❌ FAIL (Status: {response.status_code})")
                    all_passed = False
                    
            except Exception as e:
                logger.info(f"   {method} {endpoint}: ❌ FAIL ({str(e)})")
                all_passed = False
        
        self.test_results['all_endpoints'] = all_passed
        logger.info("✅ Endpoint tests completed\n")

    async def test_websocket_connection(self):
        """Test WebSocket connection on the same server."""
        logger.info("🔌 Testing Unified WebSocket Connection...")
        
        websocket_url = f"{self.websocket_url}/ws/media"
        
        try:
            # Test connection establishment
            async with websockets.connect(websocket_url, timeout=5) as websocket:
                logger.info("   🎧 WebSocket Connection: ✅ PASS (Connected successfully)")
                
                # Test message sending
                test_message = {
                    "event": "start",
                    "callSid": "test_unified_call",
                    "streamSid": "test_unified_stream",
                    "accountSid": "test_account"
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
        """Test webhook TwiML generation on unified server."""
        logger.info("📞 Testing Unified Webhook Integration...")
        
        # Simulate Twilio webhook call
        test_data = {
            'CallSid': 'test_unified_call_123',
            'From': '+1234567890',
            'To': '+0987654321',
            'CallStatus': 'in-progress'
        }
        
        try:
            response = requests.post(
                f"{self.server_url}/voice",
                data=test_data,
                timeout=5
            )
            
            if response.status_code == 200:
                # Check if response contains valid TwiML
                twiml_content = response.text
                
                # Validate TwiML structure
                if '<Response>' in twiml_content and '<Connect>' in twiml_content:
                    logger.info("   📞 TwiML Generation: ✅ PASS (Valid TwiML returned)")
                    
                    # Check for WebSocket URL pointing to same server
                    if f'ws://' in twiml_content and f':{settings.port}' in twiml_content:
                        logger.info("   🎧 Same-Server WebSocket: ✅ PASS (WebSocket on same server)")
                        self.test_results['webhook_integration'] = True
                    else:
                        logger.info("   🎧 Same-Server WebSocket: ❌ FAIL (WebSocket not on same server)")
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
        logger.info("📊 UNIFIED SERVER TEST SUMMARY")
        logger.info("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result)
        failed_tests = total_tests - passed_tests
        
        logger.info(f"   Total Tests: {total_tests}")
        logger.info(f"   Passed: {passed_tests}")
        logger.info(f"   Failed: {failed_tests}")
        logger.info(f"   Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests == 0:
            logger.info("\n🎉 ALL TESTS PASSED! Your unified server is ready.")
            self._print_next_steps()
        else:
            logger.info("\n⚠️  SOME TESTS FAILED. Please review the issues above.")
            self._print_troubleshooting()
        
        logger.info("=" * 60)

    def _print_next_steps(self):
        """Print next steps for successful unified setup."""
        logger.info("\n🚀 NEXT STEPS:")
        logger.info("   1. Start unified server: python run_unified_server.py")
        logger.info("   2. Expose with ngrok: ngrok http 5001")
        logger.info("   3. Update Twilio webhook URL")
        logger.info("   4. Enjoy your streamlined realtime AI assistant!")

    def _print_troubleshooting(self):
        """Print troubleshooting information."""
        logger.info("\n🔧 TROUBLESHOOTING:")
        
        if not self.test_results.get('root_reachable', True):
            logger.info("   • Server not reachable - start the unified server")
        
        if not self.test_results.get('websocket_connection', True):
            logger.info("   • WebSocket connection failed - check server logs")
        
        if not self.test_results.get('config_openai_api_key', True):
            logger.info("   • Missing OpenAI API key - set OPENAI_API_KEY")
        
        if not self.test_results.get('config_twilio_credentials', True):
            logger.info("   • Missing Twilio credentials - set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")

def main():
    """Run the unified test suite."""
    print("🧪 VoicePlate Unified Server Test Suite")
    print("=" * 60)
    
    tester = UnifiedSetupTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n✅ Unified server validation completed successfully!")
        print("🎉 Your streamlined realtime setup is ready to go!")
        sys.exit(0)
    else:
        print("\n❌ Unified server validation failed. Please review the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main() 