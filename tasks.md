# Task List

## Instructions for AI Agent

This file contains a list of tasks to be completed. Each task is marked with a checkbox:
- `[ ]` = Task is **NOT DONE** (needs to be completed)
- `[x]` = Task is **DONE** (completed)

**Important:** After completing a task, you must log your progress in `progress.txt` (located in the same directory as this file).

**Your workflow:**
1. Read through all tasks in this file
2. Identify which tasks are done (marked with `[x]`) and which are not done (marked with `[ ]`)
3. Find the **first task** that is **NOT DONE** (the first `[ ]` without an `x`)
4. Focus on completing **only that first undone task**
5. Once completed, update the checkbox from `[ ]` to `[x]` to mark it as done
6. **STOP WORKING** - Do not proceed to the next task
7. Write a short sentence in `progress.txt` summarizing what task you tackled and how you completed it
8. **END** - Your work is complete after logging the progress

---

## Tasks

### Task 1: The Investments FAQ agent comments

- [x] **Status: DONE**

**Requirements:**
The ai agent shouldn't appear so much as an agent but as a human. This means, among others:
- Dont provide the 'source' for your answers for example when retrieving info from the Q&A documentation. The agent should answer as if it knows the answer and not as an agent checking for answers vs the available sources
- Dont say that 'the info provided says…' since, again, the agent should act as a human and not as an agent checking for answers vs the database

---

### Task 2: The Scheduling agent comments

- [x] **Status: DONE**

**Requirements:**
The scheduling agent should get a handoff to it whenever we are dealing with a user in trying to set him on call with a representative

This agent should respond with a suggested time for someone to call back the user but in order to do so it needs a tool function in order to get back available time slots according to our policy

The tool function will need to know the day of the week so it doesnt book calls on sundays. It also needs to check what is our availability window and what is the current utc time to know were we are in the window. Our window should be calculated between 11:00 israel time (converted to utc) and 20:00 guatemala time (also converted to utc time). For example the window is 09:00 - 02:00 utc time during some parts of the year which means from 09:00 in the morning to 02:00 the following day - so thats our 17 hour availability window.

Based on this knowledge the function will return a json with fields such as: 'day: sunday', 'customer_service: 'currently_closed'', 'service_opens': 'service will resume at [day/date] 09:00 utc, [x] hours from now' or for example: 'day: tuesday', 'customer_service: 'open', 'service_closes: service will close in the next [x] hours'. 

This response will be fed back to the scheduling agent that called this function so that it will have the context to suggest times with the user

According to this response from the tool function the scheduling agent should prioritse and offer the user first if someone can call him in the next 20 minutes or so, if its not possible it should try to suggest 2 - 4 hours that someone will call back the user, other if not possible by the window or by the user then it should fallback to calnedly mcp to try and book a call for the user at a later date based on our window availability as indicated by the calendly mcp

---

### Task 3: Guardrails comments

- [x] **Status: DONE**

**Requirements:**
Change the instructions from allowing only airline questions so that it allows only questions related to our financing trading bot services and other related questions such as onboarding, account info, broker setups etc. instead of benign focused on airline industry it will switch to finance trading bots and similarly dont allow answering question on unrelated topics

---

### Task 4: General comments

- [x] **Status: DONE**

**Requirements:**
Upon conversation start, instead of showing 'Hi! I'm your airline assistant. How can I help today?' and the three clickable options 'change my seat', 'flight status' and 'missed connection' you will show the following message and buttons instead:

**The new initial message:**
```
Hi!
My name is Perry, Senior Portfolio Manager at Lucentive Club.

I'm confident that very soon you'll realize you've come to the right place.
Let's start with a short conversation.

Do you prefer a call or would you rather we chat here?
```

**The new buttons should be (2 new buttons instead of the current 3):**
- Button I: Chat (clicking it will simply send a message with the text 'chat')
- Button II: Call (clicking it will simply send a message with the text 'call')

---

### Task 5: Lead Information Popup Modal

- [x] **Status: DONE**

**Requirements:**
Create a new popup modal that appears above the chat UI on page load. The modal should:

1. **Randomize and setup new lead info each time the page loads:**
   - Generate random data for: name, email, phone, and country
   - Set a variable `new_lead=true` in the background
   - Each page load should generate fresh lead data for testing purposes

2. **Modal behavior:**
   - Appears above the chat UI section on page load
   - When clicking submit, the popup is removed
   - The randomized lead data gets used by the chat system
   - The chat should function normally otherwise (no other behavioral changes)

3. **Welcome message personalization:**
   - Use the lead's first name in the welcome message
   - Change from "Hi!" to "Hi {firstname}!" in the welcome message
   - Example: "Hi John, my name is Perry, Senior Portfolio Manager at Lucentive Club..."

4. **Display new variables in conversation text section:**
   - Show the new lead variables next to existing ones in the conversation text section
   - Display: `first_name`, `country`, and `new_lead` variables
   - This allows verification that the lead data is being properly set and used

---

### Task 6: Update Context Model for Onboarding State

- [x] **Status: DONE**

**Requirements:**
Update the context model to support onboarding state tracking:

1. **Add onboarding_state field to AirlineAgentContext** (`python-backend/airline/context.py`):
   - Add field: `onboarding_state: dict | None = None`
   - This will track progress through the onboarding flow
   - Structure should support: `completed_steps`, `trading_experience`, `previous_broker`, `trading_type`, `budget_confirmed`, `budget_amount`, `demo_offered`, `instructions_provided`

2. **Ensure the field is included in public_context** (if needed for UI display):
   - Check if onboarding_state should be visible in the UI for debugging
   - Update `public_context()` function if needed

---

### Task 7: Create Onboarding Agent

- [x] **Status: DONE**

**Requirements:**
Create a new Onboarding Agent that proactively guides new leads through the onboarding process:

1. **Create Onboarding Agent** in `python-backend/airline/agents.py`:
   - Agent name: "Onboarding Agent"
   - Model: Use same MODEL as other agents (gpt-5.2)
   - Handoff description: "Guides new leads through onboarding: trading experience, budget, broker setup."

2. **Implement prompt-based instructions** (no tools needed - all data in prompt):
   - Embed country-to-bot mapping directly in the prompt:
     - Australia: Crypto bot only. Available broker: ByBit
     - Canada: Gold, Silver, Forex, Cryptocurrencies, Futures bots. Available broker: PU Prime*
     - Any Other Country: Gold, Silver, Forex, Cryptocurrencies, Futures bots. Available brokers: Vantage, PU Prime*, Ox Securities, ByBit
     - Note: *PU Prime investment in Gold and/or Silver is available only in cents (not dollars) and within 500-10,000 USD investment only
   
   - Embed broker setup links directly in the prompt (2-3 links per broker):
     - Vantage: [Link 1: Account creation], [Link 2: Copy trading setup], [Link 3: Additional instructions]
     - PU Prime: [Link 1: Account creation], [Link 2: Copy trading setup], [Link 3: Additional instructions]
     - Ox Securities: [Link 1: Account creation], [Link 2: Copy trading setup], [Link 3: Additional instructions]
     - ByBit: [Link 1: Account creation], [Link 2: Copy trading setup], [Link 3: Additional instructions]

3. **Implement onboarding flow** (ask ONE question at a time):
   - Step 1: Trading Experience
     - Ask: "Do you have prior trading experience?"
     - If YES: Ask which broker and what type of trading
     - Update context.onboarding_state accordingly
   
   - Step 2: Country-Based Recommendation
     - Use country-to-bot mapping based on context.country
     - Recommend appropriate AI trading bot(s) for their country
   
   - Step 3: Budget Check
     - Ask about investment budget
     - If < $500: Offer demo account for 10 days
     - If >= $500: Confirm and move to step 4
   
   - Step 4: Instructions Phase
     - If existing broker: Explain copy trading setup with existing broker, share relevant links
     - If new broker: Recommend broker based on country, explain account creation, share setup links
     - Provide step-by-step instructions for trading copy setup

4. **State management**:
   - Check context.onboarding_state before asking questions
   - Resume from last incomplete step if interrupted
   - Update state after each answer
   - Mark onboarding as complete when done

5. **Handoff rules**:
   - If user requests call: Hand off to Scheduling Agent
   - If user asks FAQ questions: Hand off to Investments FAQ Agent
   - When onboarding complete: Hand off back to Triage Agent

6. **No tools needed** - all data embedded in prompt for simplicity

---

### Task 8: Update Triage Agent Routing Logic

- [x] **Status: DONE**

**Requirements:**
Modify the Triage Agent to route new leads to the Onboarding Agent:

1. **Update Triage Agent instructions** in `python-backend/airline/agents.py`:
   - Add routing logic to check `context.new_lead`
   - If `new_lead=True` AND user hasn't completed onboarding AND no specific request (call/FAQ):
     - Route to Onboarding Agent
   - If user requests call: Route to Scheduling Agent (existing logic)
   - If user asks FAQ questions: Route to Investments FAQ Agent (existing logic)
   - Otherwise: Continue with appropriate agent

2. **Add Onboarding Agent to Triage Agent's handoff list**:
   - Include onboarding_agent in triage_agent.handoffs list

3. **Ensure routing priority**:
   - Specific requests (call, FAQ) take priority over onboarding
   - Onboarding Agent is default handler for new leads without specific requests

---

### Task 9: Set Up Onboarding Agent Handoffs

- [x] **Status: DONE**

**Requirements:**
Configure handoff relationships for the Onboarding Agent:

1. **Add handoffs FROM Onboarding Agent** in `python-backend/airline/agents.py`:
   - Onboarding Agent can hand off to:
     - Scheduling Agent (when user requests call)
     - Investments FAQ Agent (when user asks FAQ questions)
     - Triage Agent (when onboarding complete or user wants to exit onboarding)

2. **Add handoffs TO Onboarding Agent**:
   - Ensure Scheduling Agent can return to Onboarding Agent (if user was in onboarding)
   - Ensure Investments FAQ Agent can return to Onboarding Agent (if user was in onboarding)
   - Triage Agent can route to Onboarding Agent (already set up in Task 8)

3. **Update agent imports** in `python-backend/server.py` and `python-backend/main.py`:
   - Add onboarding_agent to imports
   - Add to _get_agent_by_name() function
   - Add to _build_agents_list() function

---
