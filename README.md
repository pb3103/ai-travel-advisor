# AI Advisor Chatbot — Petra Boras

## 1. Setup & run

### Prerequisites

- Docker Desktop with Docker Compose
- an OpenRouter API key

### Run

1. Enter the project directory.
2. Create a `.env` file from `.env.example` and set `OPENROUTER_API_KEY` to a valid OpenRouter API key.
3. Run:

```bash
docker compose up --build 
```

## 2. Architecture overview

The application is built as a single FastAPI backend with a React frontend and PostgreSQL database.
The backend uses three specialized agents:

![Architecture diagram](image.png)

The Advisor Agent is responsible for the conversational experience and decides when external information or another specialized agent is needed.

The Plan Agent manages the structured trip plan. It is only invoked when the user explicitly asks to create or change an itinerary, so normal travel questions do not accidentally modify the plan.

The Profile Agent extracts durable traveler preferences from conversations and stores them separately from trip-specific information. The stored profile is added to the Advisor context when a new message is processed, which allows preferences to be reused across conversations.

External information is accessed through three tools: weather data from Open-Meteo, exchange rates from Frankfurter and current travel/web information through OpenRouter web search.

All agents run in the same FastAPI process. The system does not use separate microservices, queues, or background agent services.

## 3. Key decisions

1. One backend with multiple agents

    The application uses multiple specialized agents for different responsibilities, but they all run inside the same FastAPI application. Keeping them together makes the project easier to run, understand and evaluate while still giving each agent a clear responsibility.

2. Advisor Agent as the orchestrator

    The Advisor Agent is the main conversational agent and uses tools to decide when live information or a structured trip-plan update is needed. I did not introduce a separate "orchestrator agent", since that would add another model call and complexity without providing a useful separation of responsibility.

3. PostgreSQL

    Conversations, messages, trip plans, traveler preferences and the system prompt are persisted in PostgreSQL. This allows conversations and traveler preferences to survive restarts and makes cross-conversation memory explicit rather than relying on frontend or model state.

4. Deterministic memory retrieval

    Traveler memory is retrieved directly from PostgreSQL and provided to the Advisor Agent. The Profile Agent is responsible for extracting and updating durable preferences, but retrieval itself is deterministic. This avoids using an additional agent just to decide which stored memories to retrieve.

5. Structured trip plans

    Trip plans are stored as structured JSON data rather than only as assistant text. This makes them independently editable by the user and allows the frontend to render the itinerary as a dedicated object.

6. System prompt

    The advisor system prompt is stored in the database and can be edited through the Settings page. The prompt is read when a message is processed, so changes take effect immediately without restarting the application.

7. Live information

    I used separate tools for information that can change over time instead of relying on the model's knowledge. Weather uses Open-Meteo, exchange rates use Frankfurter and broader current travel information uses web search.

## 4. Ambiguities

1. Agent architecture

    The assignment does not prescribe a specific agent architecture. I chose to use multiple specialized agents for different responsibilities and kept them within the same backend process to avoid unnecessary infrastructure.

2. Which external services to use

    The assignment requires current information but does not specify APIs. I chose simple APIs without additional API keys for weather and exchange rates, and web search for information such as current travel requirements.

3. What should be stored as memory

    It was not completely clear how much previous conversation information should be reused between conversations. I chose to store durable traveler preferences rather than entire conversation histories. This keeps the memory useful without sending unrelated old conversations to the model.

4. When should the trip plan be updated

    I decided that normal travel questions should not change the trip plan. The Plan Agent is only used when the user asks to create or modify an itinerary. For example, asking "is Kyoto expensive?" should not change an existing Kyoto itinerary.

## 5. AI usage

I first used Claude Code to inspect the existing repository and understand the assignment, then implemented the application in milestones and tested each major feature before moving on. 
AI was used for planning and implementing the backend and frontend architecture, implementing the three-agent system, creating the database models and API routes, building and improving the frontend, reviewing the codebase for unused code, debugging issues found during testing etc.
I also used Claude Code to investigate specific failures instead of assuming the first implementation was correct. For example, the first OpenRouter model returned a 404 because there were no available endpoints, so I checked the available models and changed the configuration.
Another example was the trip planner. During testing, the model returned the structured plan in an unexpected nested format and the validation allowed an empty object through. I found this through live testing and then simplified the schema and added additional validation.
I also tested the application after the fixes instead of only relying on code inspection. This included live tool calls, streaming, trip-plan creation and updates, traveler memory across conversations, system prompt changes and frontend edge cases.


## 6. Known limitations

1. No authentication or authorization

    It was intentionally left out because user accounts are out of scope for the assignment, but a production version would need authentication and authorization.

2. Problem with sensitive data

    The Profile Agent is instructed not to store sensitive information such as passport numbers, card details or passwords. I also tested this during development and the information was not saved to the traveler profile. However, this is not a complete privacy solution. Sensitive information entered directly into a chat message could still be stored as part of the conversation history. A production version would need stronger data handling and privacy controls.

3. No rate limiting 

    There is currently no rate limiting on the message endpoint. A production version would need protection against excessive usage and unexpected API costs.

4. No automated test suite 

    I did not add a full automated test suite. I tested the main features manually, including chat, tools, trip plans, memory and the main frontend flows, but automated tests would be useful if the project were developed further.

5. Weather forecast range

    The weather tool only has access to the forecast range provided by the external weather API so the requests for dates outside that range cannot be answered with the same level of accuracy.

## 7. Beyond the spec (optional)

I added several small improvements:
1. conversation titles are automatically generated from the first user message instead of keeping every conversation as "New conversation"
2. conversation pinning, with pinned conversations kept in a separate section
3. empty-state landing screen with example prompts to make it easier to start a conversation
4. tool progress is shown in the chat while the advisor is waiting for live information, for example "Searching the web..." or "Checking the weather...".



