# 🧠 AI Delivery Watchtower

### Autonomous Intervention System for Real-Time Delivery Operations

---

## 🚀 Overview

Modern delivery systems (like Deliveroo or Uber Eats) rely heavily on reactive workflows. Issues such as delays, lost riders, or failed deliveries are typically handled after customers complain or when predefined rules are triggered.

This project introduces an **AI-powered operations watchtower** that continuously monitors live deliveries, detects weak signals *before* they become incidents, and autonomously intervenes using intelligent decision-making and realtime voice.

The angle is **preemption and prevention**, not only cleanup after failure: shrink mean time to detect, act earlier than rigid alerts, and route interventions through the same decision layer so outcomes stay consistent.

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
* intervenes *before* small drift becomes a customer-visible failure

---

## 💡 Solution

We build an **event-driven, agentic system** that:

1. Ingests delivery events (location updates, delays, status changes)
2. Continuously evaluates delivery health using an AI agent
3. Detects abnormal patterns (not just explicit failures)
4. Decides the best intervention strategy
5. Executes interventions via realtime voice ([LiveKit](https://livekit.com/) — open-source realtime media and [voice AI agents](https://docs.livekit.io/intro/overview/))
6. Stores all state, decisions, and history in MongoDB
7. Recovers workflows after failure or restart

**Build order:** start with the **smallest external API surface** (events in, decisions + voice out) and push complexity into **deep, composable problem-solving tools** the agents invoke (dispatch lookups, ETA replay, escalation policies)—so the system stays narrow at the boundary but capable inside.

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
[ Voice Agent (LiveKit) ]
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

### 3. Voice Agent (LiveKit)

Handles realtime voice sessions via [LiveKit](https://livekit.com/) (media + agent framework; see [LiveKit docs overview](https://docs.livekit.io/intro/overview/)):

* connects rider/customer or ops-style sessions
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

## 🔊 Voice Layer (LiveKit)

[LiveKit](https://livekit.com/) provides the **realtime voice/video infrastructure and agent tooling** so we are not stitching separate telephony + TTS vendors for the core loop. Documentation: [LiveKit documentation overview](https://docs.livekit.io/intro/overview/).

Used for:

* rider and customer voice sessions
* customer updates and escalation paths
* agent-driven conversational turns wired to MongoDB state

For the hackathon:

* prioritize one reliable voice path (browser or agent runner) over integrating every carrier edge case

---

## ⚙️ Tech Stack

* **Node.js / Python** → backend
* **MongoDB Atlas** → state + context engine (required)
* **LocalStack (SQS)** → event simulation
* **OpenAI / LLM API** → agent reasoning
* **[LiveKit](https://livekit.com/)** → realtime voice/video + [agents framework](https://docs.livekit.io/intro/overview/) (replaces a separate Twilio + bespoke TTS stack for the hackathon loop)

---

## 🧪 Demo Scenario

### Bike Breakdown Flow

1. Delivery starts normally
2. Rider stops moving
3. ETA increases
4. Watchtower flags risk *before* a support ticket or hard failure
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
* **acts early** to preempt escalation, not only after tickets or complaints
* intervenes like a human operator over **LiveKit** voice sessions
* maintains long-running workflows
* recovers from failure

---

## 🏁 Goal

To demonstrate that:

> AI agents can act as real-time operational decision-makers in event-driven systems—**anticipating and preventing** failure modes where possible, not only mopping them up afterward.



## 🗣️ Pitch (Short)

“We built an AI operations watchtower for delivery systems. Instead of reacting to fixed rules after something breaks, it watches live deliveries, catches weak signals early, and intervenes through **LiveKit**-powered voice. MongoDB holds state and history so the same brain can recover workflows and stay consistent from triage to resolution.”

 