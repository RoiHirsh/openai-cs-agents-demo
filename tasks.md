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
