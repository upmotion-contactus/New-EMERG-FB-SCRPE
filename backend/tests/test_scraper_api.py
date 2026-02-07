"""
Backend API tests for Facebook Group Lead Scraper
Tests housekeeping features: cookie status/expiration, industries, scrapes listing, job history
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://scraper-rebuild.preview.emergentagent.com').rstrip('/')

class TestCookieStatusEndpoint:
    """Test /api/scraper/cookies/status endpoint for expiration awareness"""
    
    def test_cookie_status_returns_configured_field(self):
        """GET /api/scraper/cookies/status should return configured field"""
        response = requests.get(f"{BASE_URL}/api/scraper/cookies/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert 'configured' in data, "Response should have 'configured' field"
        print(f"✓ Cookie status endpoint returns configured={data['configured']}")
        
    def test_cookie_status_returns_expiration_info_when_configured(self):
        """GET /api/scraper/cookies/status should return expiration info if configured"""
        response = requests.get(f"{BASE_URL}/api/scraper/cookies/status")
        assert response.status_code == 200
        
        data = response.json()
        if data.get('configured'):
            # When cookies are configured, we should have these fields
            assert 'valid' in data, "Should have 'valid' field when configured"
            assert 'message' in data, "Should have 'message' field when configured"
            print(f"✓ Cookie status with expiration: valid={data['valid']}, message={data['message']}")
            
            if 'expiring_soon' in data:
                print(f"  - Expiring soon: {data['expiring_soon']}")
        else:
            # When not configured, just verify the response structure
            assert 'message' in data, "Should have message field"
            print(f"✓ Cookie status: not configured - {data.get('message')}")


class TestIndustriesEndpoint:
    """Test /api/scraper/industries endpoint"""
    
    def test_industries_returns_list(self):
        """GET /api/scraper/industries should return list of industries"""
        response = requests.get(f"{BASE_URL}/api/scraper/industries")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'industries' in data, "Response should have 'industries' field"
        assert isinstance(data['industries'], list), "Industries should be a list"
        assert len(data['industries']) > 0, "Should have at least one industry"
        
        print(f"✓ Industries endpoint returns {len(data['industries'])} industries: {data['industries']}")
        
    def test_industries_contains_expected_values(self):
        """Industries list should contain expected home service industries"""
        response = requests.get(f"{BASE_URL}/api/scraper/industries")
        data = response.json()
        
        expected_industries = ['plumbing', 'hvac', 'electrical']
        for industry in expected_industries:
            assert industry in data['industries'], f"Expected '{industry}' in industries list"
        
        print(f"✓ Industries list contains expected values: {expected_industries}")


class TestScrapesEndpoint:
    """Test /api/scrapes endpoint for CSV file listing"""
    
    def test_scrapes_returns_files_list(self):
        """GET /api/scrapes should return files with metadata"""
        response = requests.get(f"{BASE_URL}/api/scrapes")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'files' in data, "Response should have 'files' field"
        assert isinstance(data['files'], list), "Files should be a list"
        assert 'total_files' in data, "Response should have 'total_files' field"
        assert 'total_records' in data, "Response should have 'total_records' field"
        
        print(f"✓ Scrapes endpoint: {data['total_files']} files, {data['total_records']} total records")
        
        # Verify file metadata structure if files exist
        if data['files']:
            file = data['files'][0]
            assert 'name' in file, "File should have 'name'"
            assert 'size' in file, "File should have 'size'"
            assert 'records' in file, "File should have 'records'"
            assert 'uploaded_at' in file, "File should have 'uploaded_at'"
            print(f"  - First file: {file['name']} ({file['records']} records)")


class TestScrapesDownloadEndpoint:
    """Test /api/scrapes/download/{filename} endpoint"""
    
    def test_download_returns_404_for_nonexistent(self):
        """GET /api/scrapes/download/nonexistent.csv should return 404"""
        response = requests.get(f"{BASE_URL}/api/scrapes/download/nonexistent_file_xyz.csv")
        assert response.status_code == 404, f"Expected 404 for nonexistent file, got {response.status_code}"
        print("✓ Download endpoint returns 404 for nonexistent file")
        
    def test_download_works_for_existing_file(self):
        """GET /api/scrapes/download/{filename} should work for existing files"""
        # First get list of files
        list_response = requests.get(f"{BASE_URL}/api/scrapes")
        if list_response.status_code != 200:
            pytest.skip("Could not get file list")
            
        files = list_response.json().get('files', [])
        if not files:
            pytest.skip("No files available to test download")
            
        # Try to download first file
        filename = files[0]['name']
        response = requests.get(f"{BASE_URL}/api/scrapes/download/{filename}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert len(response.content) > 0, "Downloaded file should have content"
        
        print(f"✓ Download works for existing file: {filename}")


class TestJobsEndpoint:
    """Test /api/scraper/jobs endpoint"""
    
    def test_jobs_returns_list(self):
        """GET /api/scraper/jobs should return job history"""
        response = requests.get(f"{BASE_URL}/api/scraper/jobs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'jobs' in data, "Response should have 'jobs' field"
        assert isinstance(data['jobs'], list), "Jobs should be a list"
        
        print(f"✓ Jobs endpoint returns {len(data['jobs'])} jobs")
        
        # If jobs exist, verify structure
        if data['jobs']:
            job = data['jobs'][0]
            # Check for expected job fields
            expected_fields = ['job_id', 'status', 'started_at']
            for field in expected_fields:
                assert field in job, f"Job should have '{field}' field"
            print(f"  - Latest job: {job['job_id']} - {job['status']}")


class TestScraperStartEndpoint:
    """Test /api/scraper/start endpoint error handling"""
    
    def test_start_requires_cookies_configured(self):
        """POST /api/scraper/start should return error when no cookies"""
        # First check if cookies are NOT configured
        status_response = requests.get(f"{BASE_URL}/api/scraper/cookies/status")
        if status_response.status_code == 200:
            status_data = status_response.json()
            if status_data.get('configured'):
                pytest.skip("Cookies are configured, cannot test no-cookie scenario")
        
        # Try to start scraper without cookies
        response = requests.post(
            f"{BASE_URL}/api/scraper/start",
            json={"urls": ["https://facebook.com/groups/test"], "industry": "plumbing"},
            headers={"Content-Type": "application/json"}
        )
        
        # Should get 400 error for no cookies
        assert response.status_code == 400, f"Expected 400 when no cookies, got {response.status_code}"
        data = response.json()
        assert 'detail' in data, "Error response should have 'detail'"
        assert 'cookie' in data['detail'].lower(), f"Error should mention cookies: {data['detail']}"
        
        print(f"✓ Scraper start correctly returns error when no cookies: {data['detail']}")
        
    def test_start_validates_urls(self):
        """POST /api/scraper/start should validate URLs are provided"""
        response = requests.post(
            f"{BASE_URL}/api/scraper/start",
            json={"urls": [], "industry": "plumbing"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 400, f"Expected 400 for empty URLs, got {response.status_code}"
        print("✓ Scraper start validates that URLs are provided")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
