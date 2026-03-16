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

user_problem_statement: "Frontend update to match new backend reader response schema. Backend now returns: checking_in, reading_journal, what_i_think_the_writer_is_doing, moments (paragraph+type+comment), questions_for_writer instead of inline_comments/section_reflection. Editor report format also changed to: did_it_land, engagement_drop, what_readers_disagree_about, open_questions, strongest_moments."

backend:
  - task: "Backend reader schema already updated (no changes needed)"
    implemented: true
    working: true
    file: "backend/services/readers.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Backend already emits new schema via SSE: checking_in, reading_journal, what_i_think_the_writer_is_doing, moments, questions_for_writer. editor.py also already generates new 5-section report."

frontend:
  - task: "useReadingStream - consume new reader_complete event schema"
    implemented: true
    working: "NA"
    file: "frontend/src/hooks/useReadingStream.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Updated to read moments (paragraph->line mapping), reading_journal, what_i_think_the_writer_is_doing, questions_for_writer, checking_in from SSE events. Updated loadExistingReactions to use response_json fields with legacy fallbacks. Reflections state now carries full per-section journal data."

  - task: "ReaderSidebar - new literary reader card design with journal as primary content"
    implemented: true
    working: "NA"
    file: "frontend/src/components/ReaderSidebar.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Redesigned ReaderPanel: reading_journal is primary (italic serif), what_i_think_the_writer_is_doing secondary, questions_for_writer visually highlighted with clay left-border, checking_in collapsible. New COMMENT_TYPE_COLORS for reaction/confusion/question/craft/callback. Added AggregatedQuestions panel at top of sidebar. Filter bar uses new types only."

  - task: "ManuscriptView - update comment type colors for new types"
    implemented: true
    working: "NA"
    file: "frontend/src/components/ManuscriptView.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Updated COMMENT_TYPE_COLORS to new set. Changed 'annotations' label to 'moments marked'. Popover header shows paragraph symbol."

  - task: "CommentPopover - update type colors for new schema"
    implemented: true
    working: "NA"
    file: "frontend/src/components/CommentPopover.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Updated TYPE_COLORS to new set (reaction/confusion/question/craft/callback) with legacy fallbacks."

  - task: "ReportPage - new 5-section editor report replacing old 6 sections"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/ReportPage.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Replaced Executive Summary/Engagement Heatmap/Consensus/Character/Prediction/Recommendations with: Did it land? (did_it_land), Where did engagement drop? (engagement_drop), What readers disagree about (what_readers_disagree_about), Open questions (open_questions, multiple-reader questions highlighted), Strongest moments (strongest_moments). Literary calm aesthetic maintained."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus:
    - "useReadingStream - consume new reader_complete event schema"
    - "ReaderSidebar - new literary reader card design with journal as primary content"
    - "ReportPage - new 5-section editor report replacing old 6 sections"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "Updated 5 frontend files to match new backend reader schema. Key changes: (1) useReadingStream.js now reads moments (paragraph->line) instead of inline_comments, and reflections state carries rich per-section journal data. (2) ReaderSidebar redesigned: journals as primary content, questions highlighted, checking_in collapsible, new type system. (3) ManuscriptView/CommentPopover updated to new type colors. (4) ReportPage completely rewritten with 5 new sections: did_it_land, engagement_drop, what_readers_disagree_about, open_questions, strongest_moments. Frontend compiles cleanly (lint passes). Backend was already updated - no backend changes needed."