#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Replace Emergent-managed Google Auth with the user's own Google OAuth 2.0 credentials (Authorization Code Flow). Client ID and Secret provided. Redirect URIs registered: http://roundtable.works/api/auth/google/callback and http://localhost:8000/api/auth/google/callback."

backend:
  - task: "Native Google OAuth - /api/auth/google/login endpoint"
    implemented: true
    working: "NA"
    file: "backend/routers/auth.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Implemented GET /api/auth/google/login - generates state token, builds Google OAuth URL with GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI from env, returns 302 redirect to Google."

  - task: "Native Google OAuth - /api/auth/google/callback endpoint"
    implemented: true
    working: "NA"
    file: "backend/routers/auth.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Implemented GET /api/auth/google/callback - exchanges code for tokens via Google, fetches userinfo, upserts user in DB, creates session_token, redirects browser to FRONTEND_URL/auth/callback?session_token=<token>."

  - task: "Google OAuth env vars in config.py"
    implemented: true
    working: "NA"
    file: "backend/config.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Added GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, FRONTEND_URL to config.py loaded from .env. Created backend/.env with the provided Google credentials."

frontend:
  - task: "LoginPage - use backend Google login URL instead of Emergent URL"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/LoginPage.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Changed href from hardcoded Emergent URL to getApiBase()+'/api/auth/google/login' (uses REACT_APP_BACKEND_URL)."

  - task: "AuthCallback - read session_token from query params instead of session_id from hash"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/AuthCallback.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Rewrote AuthCallback to read ?session_token= from URL search params, store in localStorage, call /api/auth/me to get user, then navigate to /setup."

  - task: "AuthContext - fix loading-skip logic for new callback format"
    implemented: true
    working: "NA"
    file: "frontend/src/context/AuthContext.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Changed hash check (session_id=) to query-param check (session_token= on /auth/callback path)."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 0
  run_ui: false

test_plan:
  current_focus:
    - "Native Google OAuth - /api/auth/google/login endpoint"
    - "Native Google OAuth - /api/auth/google/callback endpoint"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Replaced Emergent Google Auth with native Google OAuth 2.0. Backend has two new endpoints: /api/auth/google/login (redirects to Google) and /api/auth/google/callback (exchanges code, creates session, redirects to frontend). Frontend LoginPage now points to the backend login URL; AuthCallback reads session_token from query params. NOTE: Full OAuth flow requires Supabase credentials in backend/.env and the correct GOOGLE_REDIRECT_URI matching what's registered in Google Cloud Console. The redirect URI http://roundtable.works/api/auth/google/callback is registered and configured."