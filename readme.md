# 🧠 AI Delivery Watchtower

### Autonomous Intervention System for Real-Time Delivery Operations

---

## 🚀 Overview

Modern delivery systems (like Deliveroo or Uber Eats) rely heavily on reactive workflows. Issues such as delays, lost riders, or failed deliveries are typically handled after customers complain or when predefined rules are triggered.

This project introduces an **AI-powered operations watchtower** that continuously monitors live deliveries, detects weak signals of failure, and autonomously intervenes using intelligent decision-making and voice communication.

Instead of waiting for explicit errors, the system behaves like a human operations agent:

* constantly observing delivery state
* identifying anomalies early
* deciding the best course of action
* intervening via voice
* updating system state
* recovering from failures seamlessly

---

## 🎯 Problem Statement

Delivery operations are chaotic:

* riders get lost or delayed
* ETAs fluctuate unpredictably
* customers are left uninformed
* systems rely on rigid rules

There is no intelligent layer that:

* understands *context*
* adapts to *uncertainty*
* takes *proactive action*

---

## 💡 Solution

We build an **event-driven, agentic system** that:

1. Ingests delivery events (location updates, delays, status changes)
2. Continuously evaluates delivery health using an AI agent
3. Detects abnormal patterns (not just explicit failures)
4. Decides the best intervention strategy
5. Executes interventions via voice (ElevenLabs)
6. Stores all state, decisions, and history in MongoDB
7. Recovers workflows after failure or restart

---

## 🧱 Architecture

```text
[ Webhook Events ]
        ↓
[ LocalStack SQS Queue ]
        ↓
[ Event Router (Code) ]
        ↓
[ MongoDB (State + Event Store) ]
        ↓
[ Watchtower Agent ]
        ↓
[ Intervention Planner Agent ]
        ↓
[ Voice Agent (ElevenLabs) ]
        ↓
[ MongoDB (Transcripts + Decisions) ]
        ↓
[ Recovery Agent ]
        ↓
[ Next Action Loop ]
```

---

## 🤖 Agent Design

### 1. Watchtower Agent (Core Intelligence)

Continuously monitors delivery state and decides:

* Is this delivery healthy?
* Does something feel “off”?
* Should we act now or wait?

It reasons over:

* ETA changes
* rider movement
* time since last update
* route deviation
* past interventions

---

### 2. Intervention Planner Agent

Determines the best next action:

* call rider
* call customer
* wait
* escalate
* reassign

Focus: **choosing the right action at the right time**

---

### 3. Voice Agent (ElevenLabs)

Handles communication:

* calls rider/customer (simulated)
* asks contextual questions
* extracts structured meaning from responses

Example:

> “My bike broke down” → `issue: mechanical_failure`

---

### 4. Recovery / Consistency Agent

Ensures workflow continuity:

* resumes incomplete flows
* checks missing actions
* prevents duplication
* continues after system restarts

---

## 🗄️ MongoDB (Core System Brain)

MongoDB is not just storage. It powers:

* delivery state
* event history
* agent decisions
* intervention logs
* voice transcripts
* recovery checkpoints

Example:

```json
{
  "deliveryId": "D123",
  "status": "delayed",
  "events": [...],
  "agentDecisions": [...],
  "interventions": [...],
  "lastKnownState": {...}
}
```

---

## 🔊 Voice Layer (ElevenLabs)

Used for:

* rider interaction
* customer updates
* escalation handling

For the hackathon:

* simulated calls (audio playback)
* optional real call via Twilio (if time allows)

---

## ⚙️ Tech Stack

* **Node.js / Python** → backend
* **MongoDB Atlas** → state + context engine (required)
* **LocalStack (SQS)** → event simulation
* **OpenAI / LLM API** → agent reasoning
* **ElevenLabs** → voice synthesis
* **Twilio (optional)** → real phone calls

---

## 🧪 Demo Scenario

### Bike Breakdown Flow

1. Delivery starts normally
2. Rider stops moving
3. ETA increases
4. Watchtower detects anomaly
5. Planner decides to call rider
6. Voice agent asks what happened
7. Rider responds: “My bike broke down”
8. System updates MongoDB
9. Recovery agent decides:

   * notify customer
   * mark reassignment needed
10. System continues workflow
11. Kill + restart system → recovery resumes correctly

---

## ⚠️ Known Challenges & Open Questions

### 1. Defining “Abnormal”

* How does the agent distinguish normal delay vs real issue?
* Requires good prompt design and context structure

---

### 2. Overreaction Risk

* Calling too early can annoy users
* Need layered intervention strategy

---

### 3. Voice Reliability

* Calls may fail
* Need fallback strategies (retry, alternative action)

---

### 4. Trust vs Verification

* Rider responses may be unreliable
* Must validate against system data (movement, ETA)

---

### 5. Concurrency Issues

* Multiple agents acting on same delivery
* Requires state locking or checks

---

### 6. Simulation vs Reality

* No real GPS or dispatch system
* Must simulate cleanly but convincingly

---

## 📈 Scalability Considerations

In production:

* Replace SQS with Kafka or real event streaming
* Introduce:

  * distributed workers
  * streaming location data
  * real-time maps
* Add:

  * agent reputation scoring
  * adaptive thresholds
  * learning from past incidents

---

## 🧠 Key Innovation

This system is not rule-based.

It:

* reasons over incomplete data
* adapts to evolving situations
* intervenes like a human operator
* maintains long-running workflows
* recovers from failure

---

## 🏁 Goal

To demonstrate that:

> AI agents can act as real-time operational decision-makers in event-driven systems, not just passive responders.



## 🗣️ Pitch (Short)

“We built an AI operations watchtower for delivery systems. Instead of reacting to fixed rules, our system continuously monitors live deliveries, detects weak signals of failure, and intervenes through voice. Using MongoDB as a persistent state layer, it can recover from failures and manage long-running workflows like a human operations team.”

 