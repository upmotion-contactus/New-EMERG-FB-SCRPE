#!/usr/bin/env python3
"""
Backend API Testing for Multi-Industry Lead Scraper
Tests all scraper-related endpoints and file management APIs
"""

import requests
import sys
import json
from datetime import datetime

class LeadScraperAPITester:
    def __init__(self, base_url="https://scraper-rebuild.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        default_headers = {'Content-Type': 'application/json'}
        if headers:
            default_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   {method} {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=default_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=default_headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=default_headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ PASSED - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict) and len(response_data) <= 5:
                        print(f"   Response: {response_data}")
                    elif isinstance(response_data, dict) and 'industries' in response_data:
                        print(f"   Industries: {response_data.get('industries', [])}")
                    elif isinstance(response_data, dict) and 'files' in response_data:
                        files = response_data.get('files', [])
                        print(f"   Files found: {len(files)}")
                        if files:
                            print(f"   Sample file: {files[0].get('name', 'unknown')}")
                except:
                    print(f"   Response: {response.text[:100]}...")
            else:
                self.tests_passed += 0
                print(f"❌ FAILED - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                self.failed_tests.append({
                    'name': name,
                    'expected': expected_status,
                    'actual': response.status_code,
                    'response': response.text[:200]
                })

            return success, response.json() if response.headers.get('content-type', '').startswith('application/json') else {}

        except Exception as e:
            print(f"❌ FAILED - Error: {str(e)}")
            self.failed_tests.append({
                'name': name,
                'error': str(e)
            })
            return False, {}

    def test_scraper_industries(self):
        """Test GET /api/scraper/industries - should return 6 industries"""
        print("\n" + "="*60)
        print("TESTING SCRAPER INDUSTRIES API")
        print("="*60)
        
        success, response = self.run_test(
            "Get Industries List",
            "GET",
            "scraper/industries",
            200
        )
        
        if success:
            industries = response.get('industries', [])
            expected_industries = ['plumbing', 'hvac', 'electrical', 'remodeling', 'landscaping', 'power_washing']
            
            if len(industries) == 6:
                print(f"✅ Correct number of industries: {len(industries)}")
            else:
                print(f"❌ Expected 6 industries, got {len(industries)}")
                
            missing = set(expected_industries) - set(industries)
            if not missing:
                print("✅ All expected industries present")
            else:
                print(f"❌ Missing industries: {missing}")
        
        return success

    def test_scrapes_api(self):
        """Test GET /api/scrapes - should return files list with test file"""
        print("\n" + "="*60)
        print("TESTING SCRAPES FILE MANAGEMENT API")
        print("="*60)
        
        success, response = self.run_test(
            "List Scrape Files",
            "GET",
            "scrapes",
            200
        )
        
        if success:
            files = response.get('files', [])
            total_records = response.get('total_records', 0)
            
            print(f"📁 Total files: {len(files)}")
            print(f"📊 Total records: {total_records}")
            
            # Check for test file
            test_file_found = any(f.get('name') == 'test_plumbing_leads.csv' for f in files)
            if test_file_found:
                print("✅ Test file 'test_plumbing_leads.csv' found")
            else:
                print("❌ Test file 'test_plumbing_leads.csv' not found")
                print(f"   Available files: {[f.get('name') for f in files]}")
        
        return success

    def test_detect_industry(self):
        """Test POST /api/scraper/detect-industry"""
        print("\n" + "="*60)
        print("TESTING INDUSTRY DETECTION API")
        print("="*60)
        
        test_cases = [
            ("plumbing group", "plumbing"),
            ("hvac contractors", "hvac"),
            ("electrical workers", "electrical"),
            ("random text", "plumbing")  # Should default to plumbing
        ]
        
        all_passed = True
        for text, expected in test_cases:
            success, response = self.run_test(
                f"Detect Industry: '{text}'",
                "POST",
                "scraper/detect-industry",
                200,
                {"text": text}
            )
            
            if success:
                detected = response.get('industry')
                if detected == expected:
                    print(f"✅ Correctly detected '{detected}' for '{text}'")
                else:
                    print(f"⚠️  Expected '{expected}', got '{detected}' for '{text}'")
            else:
                all_passed = False
        
        return all_passed

    def test_cookies_status(self):
        """Test GET /api/scraper/cookies/status"""
        print("\n" + "="*60)
        print("TESTING COOKIES STATUS API")
        print("="*60)
        
        success, response = self.run_test(
            "Get Cookies Status",
            "GET",
            "scraper/cookies/status",
            200
        )
        
        if success:
            configured = response.get('configured', False)
            print(f"🍪 Cookies configured: {configured}")
        
        return success

    def test_download_file(self):
        """Test GET /api/scrapes/download/{filename}"""
        print("\n" + "="*60)
        print("TESTING FILE DOWNLOAD API")
        print("="*60)
        
        # Test downloading the test file
        url = f"{self.api_url}/scrapes/download/test_plumbing_leads.csv"
        print(f"\n🔍 Testing File Download...")
        print(f"   GET {url}")
        
        try:
            response = requests.get(url, timeout=10)
            self.tests_run += 1
            
            if response.status_code == 200:
                self.tests_passed += 1
                print(f"✅ PASSED - Status: {response.status_code}")
                
                # Check content type
                content_type = response.headers.get('content-type', '')
                if 'text/csv' in content_type:
                    print("✅ Correct content type: text/csv")
                else:
                    print(f"⚠️  Content type: {content_type}")
                
                # Check content
                content = response.text
                if 'name,phone,website' in content:
                    print("✅ CSV header found")
                    lines = content.strip().split('\n')
                    print(f"📄 CSV has {len(lines)} lines (including header)")
                else:
                    print("❌ Invalid CSV content")
                
                return True
            else:
                print(f"❌ FAILED - Expected 200, got {response.status_code}")
                self.failed_tests.append({
                    'name': 'File Download',
                    'expected': 200,
                    'actual': response.status_code
                })
                return False
                
        except Exception as e:
            print(f"❌ FAILED - Error: {str(e)}")
            self.failed_tests.append({
                'name': 'File Download',
                'error': str(e)
            })
            return False

    def test_scraper_jobs_api(self):
        """Test scraper jobs endpoints"""
        print("\n" + "="*60)
        print("TESTING SCRAPER JOBS API")
        print("="*60)
        
        # Test listing jobs
        success, response = self.run_test(
            "List Scraper Jobs",
            "GET",
            "scraper/jobs",
            200
        )
        
        if success:
            jobs = response.get('jobs', [])
            print(f"📋 Total jobs in history: {len(jobs)}")
        
        return success

    def run_all_tests(self):
        """Run all backend API tests"""
        print("🚀 Starting Multi-Industry Lead Scraper Backend API Tests")
        print(f"🌐 Testing against: {self.base_url}")
        print("="*80)
        
        # Test all APIs
        self.test_scraper_industries()
        self.test_scrapes_api()
        self.test_detect_industry()
        self.test_cookies_status()
        self.test_download_file()
        self.test_scraper_jobs_api()
        
        # Print summary
        print("\n" + "="*80)
        print("📊 TEST SUMMARY")
        print("="*80)
        print(f"✅ Tests passed: {self.tests_passed}/{self.tests_run}")
        print(f"❌ Tests failed: {len(self.failed_tests)}")
        
        if self.failed_tests:
            print("\n🔍 FAILED TESTS:")
            for i, test in enumerate(self.failed_tests, 1):
                print(f"{i}. {test['name']}")
                if 'error' in test:
                    print(f"   Error: {test['error']}")
                else:
                    print(f"   Expected: {test['expected']}, Got: {test['actual']}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"\n🎯 Success Rate: {success_rate:.1f}%")
        
        return self.tests_passed == self.tests_run

def main():
    """Main test execution"""
    tester = LeadScraperAPITester()
    
    try:
        success = tester.run_all_tests()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())