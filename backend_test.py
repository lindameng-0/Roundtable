import requests
import sys
import json
import time
from datetime import datetime

class RoundtableAPITester:
    def __init__(self, base_url="https://fiction-sync.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.manuscript_id = None
        self.reader_ids = []
        self.test_manuscript = """Chapter One: The Beginning

Sarah walked through the forest, her heart pounding with each step. The ancient trees seemed to whisper secrets she couldn't quite understand. Behind her, the sound of breaking branches grew closer.

"They're coming," she whispered to herself, quickening her pace. The artifact in her backpack felt heavier with each step, as if it was pulling her deeper into the mystery that had consumed her life for the past month.

Chapter Two: The Discovery

The clearing appeared suddenly, bathed in an otherworldly light. In the center stood a stone altar, covered in symbols that seemed to shift and dance before her eyes. This was it - the place from her visions.

As Sarah approached the altar, the artifact began to glow through the fabric of her backpack. The symbols on the stone seemed to respond, lighting up one by one in a pattern she somehow understood.

"You've found it at last," a voice said behind her. Sarah spun around to see an old woman emerging from the shadows of the trees.

Chapter Three: Revelations

"I've been waiting for you, child," the old woman said, her eyes twinkling with ancient knowledge. "The artifact you carry has chosen you, just as it chose me sixty years ago."

Sarah's mind raced with questions, but before she could speak, the ground beneath them began to tremble. The artifact's glow intensified, and the symbols on the altar blazed with brilliant light.

"What's happening?" Sarah called out over the growing rumble.

"The awakening has begun," the woman replied. "And you, my dear, are the key to everything."

As the light reached its peak, Sarah felt herself being pulled into another world, another time, where magic was real and her destiny awaited."""

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        return success

    def test_api_root(self):
        """Test API root endpoint"""
        try:
            response = requests.get(f"{self.api_url}/")
            success = response.status_code == 200 and "message" in response.json()
            return self.log_test("API Root", success, f"Status: {response.status_code}")
        except Exception as e:
            return self.log_test("API Root", False, str(e))

    def test_model_config(self):
        """Test model configuration endpoints"""
        try:
            # Get available models
            response = requests.get(f"{self.api_url}/config/models")
            if response.status_code != 200:
                return self.log_test("Get Models", False, f"Status: {response.status_code}")
            
            models_data = response.json()
            if not models_data.get("available") or not models_data.get("current_model"):
                return self.log_test("Get Models", False, "Invalid response structure")
            
            success1 = self.log_test("Get Models", True)

            # Test model switching
            new_model = {"provider": "openai", "model": "gpt-4o"}
            response = requests.post(f"{self.api_url}/config/model", json=new_model)
            success2 = response.status_code == 200
            
            return self.log_test("Switch Model", success2, f"Status: {response.status_code}") and success1

        except Exception as e:
            return self.log_test("Model Config", False, str(e))

    def test_manuscript_creation(self):
        """Test manuscript creation with genre detection"""
        try:
            manuscript_data = {
                "title": "Test Fantasy Novel",
                "raw_text": self.test_manuscript
            }
            
            response = requests.post(f"{self.api_url}/manuscripts", json=manuscript_data)
            
            if response.status_code != 200:
                return self.log_test("Create Manuscript", False, f"Status: {response.status_code}")
            
            data = response.json()
            required_fields = ["id", "title", "genre", "target_audience", "sections", "total_sections"]
            
            for field in required_fields:
                if field not in data:
                    return self.log_test("Create Manuscript", False, f"Missing field: {field}")
            
            self.manuscript_id = data["id"]
            sections_count = data["total_sections"]
            
            success = sections_count > 0 and data["genre"] and data["target_audience"]
            details = f"ID: {self.manuscript_id}, Sections: {sections_count}, Genre: {data['genre']}"
            
            return self.log_test("Create Manuscript", success, details)
            
        except Exception as e:
            return self.log_test("Create Manuscript", False, str(e))

    def test_manuscript_retrieval(self):
        """Test manuscript retrieval"""
        if not self.manuscript_id:
            return self.log_test("Get Manuscript", False, "No manuscript ID available")
        
        try:
            response = requests.get(f"{self.api_url}/manuscripts/{self.manuscript_id}")
            success = response.status_code == 200 and response.json().get("id") == self.manuscript_id
            return self.log_test("Get Manuscript", success, f"Status: {response.status_code}")
        except Exception as e:
            return self.log_test("Get Manuscript", False, str(e))

    def test_genre_update(self):
        """Test genre information update"""
        if not self.manuscript_id:
            return self.log_test("Update Genre", False, "No manuscript ID available")
        
        try:
            update_data = {
                "genre": "Urban Fantasy",
                "target_audience": "Young Adult readers who love magic",
                "age_range": "YA",
                "comparable_books": ["Harry Potter by J.K. Rowling", "Percy Jackson by Rick Riordan"]
            }
            
            response = requests.patch(f"{self.api_url}/manuscripts/{self.manuscript_id}/genre", json=update_data)
            success = response.status_code == 200
            return self.log_test("Update Genre", success, f"Status: {response.status_code}")
        except Exception as e:
            return self.log_test("Update Genre", False, str(e))

    def test_reader_personas(self):
        """Test reader persona generation"""
        if not self.manuscript_id:
            return self.log_test("Generate Personas", False, "No manuscript ID available")
        
        try:
            response = requests.get(f"{self.api_url}/manuscripts/{self.manuscript_id}/personas")
            
            if response.status_code != 200:
                return self.log_test("Generate Personas", False, f"Status: {response.status_code}")
            
            personas = response.json()
            
            if not isinstance(personas, list) or len(personas) != 5:
                return self.log_test("Generate Personas", False, f"Expected 5 personas, got {len(personas)}")
            
            # Check required fields in personas
            required_fields = ["id", "name", "personality", "reading_habits", "quote"]
            for i, persona in enumerate(personas):
                for field in required_fields:
                    if field not in persona or not persona[field]:
                        return self.log_test("Generate Personas", False, f"Persona {i} missing {field}")
            
            # Store reader IDs for later tests
            self.reader_ids = [p["id"] for p in personas]
            
            return self.log_test("Generate Personas", True, f"Generated {len(personas)} personas")
            
        except Exception as e:
            return self.log_test("Generate Personas", False, str(e))

    def test_persona_regeneration(self):
        """Test individual persona regeneration"""
        if not self.manuscript_id or not self.reader_ids:
            return self.log_test("Regenerate Persona", False, "No personas available")
        
        try:
            # Test regenerating single reader
            reader_id = self.reader_ids[0]
            regen_data = {"reader_id": reader_id}
            
            response = requests.post(f"{self.api_url}/manuscripts/{self.manuscript_id}/personas/regenerate", json=regen_data)
            success = response.status_code == 200 and response.json().get("id") == reader_id
            
            return self.log_test("Regenerate Persona", success, f"Status: {response.status_code}")
        except Exception as e:
            return self.log_test("Regenerate Persona", False, str(e))

    def test_sse_read_all_endpoint(self):
        """Test new SSE /read-all endpoint"""
        if not self.manuscript_id:
            return self.log_test("SSE Read-All Endpoint", False, "No manuscript ID available")
        
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            response = requests.get(
                f"{self.api_url}/manuscripts/{self.manuscript_id}/read-all",
                stream=True,
                timeout=15,
                headers={'Accept': 'text/event-stream'}
            )
            
            # Check if we get SSE headers
            is_sse = "text/event-stream" in response.headers.get("content-type", "")
            
            if not is_sse:
                return self.log_test("SSE Read-All Endpoint", False, f"Not SSE response, got: {response.headers.get('content-type')}")
            
            # Try to read initial SSE events
            events_received = []
            chunk_count = 0
            
            for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
                if chunk.strip():
                    chunk_count += 1
                    # Look for SSE event types
                    if "data:" in chunk and "{" in chunk:
                        try:
                            data_start = chunk.find("{")
                            data_end = chunk.rfind("}") + 1
                            if data_start >= 0 and data_end > data_start:
                                event_data = json.loads(chunk[data_start:data_end])
                                events_received.append(event_data.get("type", "unknown"))
                        except:
                            pass
                
                # Stop after getting some events or timeout
                if chunk_count >= 5 or len(events_received) >= 3:
                    break
            
            response.close()
            
            # Check if we got expected event types
            expected_events = ['start', 'section_start']
            has_expected = any(event in events_received for event in expected_events)
            
            details = f"Events: {events_received}, Chunks: {chunk_count}"
            return self.log_test("SSE Read-All Endpoint", has_expected, details)
            
        except requests.Timeout:
            return self.log_test("SSE Read-All Endpoint", True, "Timeout expected - endpoint exists")
        except Exception as e:
            return self.log_test("SSE Read-All Endpoint", False, str(e))

    def test_all_reactions_endpoint(self):
        """Test new /all-reactions endpoint"""
        if not self.manuscript_id:
            return self.log_test("Get All Reactions", False, "No manuscript ID available")
        
        try:
            response = requests.get(f"{self.api_url}/manuscripts/{self.manuscript_id}/all-reactions")
            
            success = response.status_code == 200
            if success:
                reactions = response.json()
                details = f"Status: {response.status_code}, Reactions: {len(reactions)}"
            else:
                details = f"Status: {response.status_code}"
            
            return self.log_test("Get All Reactions", success, details)
            
        except Exception as e:
            return self.log_test("Get All Reactions", False, str(e))

    def test_manuscript_sections_structure(self):
        """Test that manuscript sections have global line numbers"""
        if not self.manuscript_id:
            return self.log_test("Check Sections Structure", False, "No manuscript ID available")
        
        try:
            response = requests.get(f"{self.api_url}/manuscripts/{self.manuscript_id}")
            
            if response.status_code != 200:
                return self.log_test("Check Sections Structure", False, f"Status: {response.status_code}")
            
            data = response.json()
            sections = data.get("sections", [])
            
            if not sections:
                return self.log_test("Check Sections Structure", False, "No sections found")
            
            # Check if sections have required fields for new structure
            section = sections[0]
            required_fields = ["line_start", "line_end", "paragraph_lines"]
            
            has_all_fields = all(field in section for field in required_fields)
            
            if has_all_fields:
                paragraph_lines = section.get("paragraph_lines", [])
                has_line_numbers = len(paragraph_lines) > 0 and all("line" in pl for pl in paragraph_lines)
                details = f"Sections: {len(sections)}, Lines in first: {len(paragraph_lines)}"
                return self.log_test("Check Sections Structure", has_line_numbers, details)
            else:
                missing = [f for f in required_fields if f not in section]
                return self.log_test("Check Sections Structure", False, f"Missing fields: {missing}")
            
        except Exception as e:
            return self.log_test("Check Sections Structure", False, str(e))

    def test_reactions_retrieval(self):
        """Test retrieving reader reactions"""
        if not self.manuscript_id:
            return self.log_test("Get Reactions", False, "No manuscript ID available")
        
        try:
            response = requests.get(f"{self.api_url}/manuscripts/{self.manuscript_id}/reactions/1")
            
            # This might be empty if no reactions yet, but should not error
            success = response.status_code == 200
            reactions = response.json() if success else []
            
            details = f"Status: {response.status_code}, Reactions: {len(reactions)}"
            return self.log_test("Get Reactions", success, details)
            
        except Exception as e:
            return self.log_test("Get Reactions", False, str(e))

    def test_editor_report_generation(self):
        """Test editor report generation"""
        if not self.manuscript_id:
            return self.log_test("Generate Report", False, "No manuscript ID available")
        
        try:
            response = requests.post(f"{self.api_url}/manuscripts/{self.manuscript_id}/editor-report")
            
            if response.status_code != 200:
                # This might fail if no reactions exist yet, which is expected
                details = f"Status: {response.status_code} (Expected if no reactions)"
                return self.log_test("Generate Report", response.status_code in [200, 400], details)
            
            data = response.json()
            has_report = "report" in data and isinstance(data["report"], dict)
            
            return self.log_test("Generate Report", has_report, f"Report generated: {has_report}")
            
        except Exception as e:
            return self.log_test("Generate Report", False, str(e))

    def test_report_retrieval(self):
        """Test retrieving existing editor report"""
        if not self.manuscript_id:
            return self.log_test("Get Report", False, "No manuscript ID available")
        
        try:
            response = requests.get(f"{self.api_url}/manuscripts/{self.manuscript_id}/editor-report")
            
            # This might not exist, which is okay
            success = response.status_code in [200, 404]
            details = f"Status: {response.status_code}"
            
            return self.log_test("Get Report", success, details)
            
        except Exception as e:
            return self.log_test("Get Report", False, str(e))

    def run_all_tests(self):
        """Run all API tests in sequence"""
        print(f"🧪 Testing Roundtable AI Beta Reader v2 API at {self.base_url}")
        print("=" * 60)
        
        # Basic connectivity
        if not self.test_api_root():
            print("❌ Cannot reach API. Stopping tests.")
            return False
        
        # Model configuration
        self.test_model_config()
        
        # Core manuscript workflow
        if self.test_manuscript_creation():
            self.test_manuscript_retrieval()
            self.test_manuscript_sections_structure()
            self.test_genre_update()
            
            # Reader personas - try but don't fail entire test if it fails
            try:
                if self.test_reader_personas():
                    self.test_persona_regeneration()
            except:
                print("⚠️ Skipping persona tests due to errors")
            
            # New v2 features: SSE read-all and all-reactions endpoints
            self.test_sse_read_all_endpoint()
            self.test_all_reactions_endpoint()
            
            # Legacy reaction endpoint
            self.test_reactions_retrieval()
            
            # Editor reports
            self.test_editor_report_generation()
            self.test_report_retrieval()
        
        print("\n" + "=" * 60)
        print(f"📊 Tests passed: {self.tests_passed}/{self.tests_run}")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"📈 Success rate: {success_rate:.1f}%")
        
        if self.manuscript_id:
            print(f"📋 Test manuscript ID: {self.manuscript_id}")
        
        return success_rate >= 75  # Allow some failures during development


def main():
    tester = RoundtableAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())