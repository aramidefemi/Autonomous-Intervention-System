# AI Delivery Watchtower — Test Plan & Demo Scenarios

## Purpose

This document defines every test scenario, edge case, and demo script for the Autonomous Intervention System. Each scenario includes the event sequence to inject, the expected system behaviour at each step, and which Prolonged Coordination sub-requirement it validates.

---

## Theme Requirements Traceability

Every scenario maps to one or more of these Prolonged Coordination sub-requirements:

| Code | Requirement |
|------|-------------|
| PC-1 | Multi-step workflows lasting hours/days |
| PC-2 | MongoDB as context engine (not just storage) |
| PC-3 | Tool call execution (voice, escalation, reassignment) |
| PC-4 | Reasoning state retention across steps |
| PC-5 | Recovery from single failures |
| PC-6 | Task consistency in multi-step workflows |
| PC-7 | Mid-workflow task modification |

---

## 1. Core Scenarios (Happy Path)

### Scenario 1.1 — Standard Delivery (No Intervention Needed)

**What it proves:** The system correctly identifies a healthy delivery and does NOT intervene.

**Requirements:** PC-2, PC-4

**Event Sequence:**

```json
[
  {
    "eventId": "E001",
    "deliveryId": "D-100",
    "type": "delivery_created",
    "timestamp": "2026-05-02T10:00:00Z",
    "data": {
      "orderId": "ORD-5001",
      "riderId": "R-10",
      "customerId": "C-20",
      "restaurantLocation": { "lat": 51.5074, "lng": -0.1278 },
      "customerLocation": { "lat": 51.5155, "lng": -0.1419 },
      "estimatedDeliveryTime": "2026-05-02T10:35:00Z"
    }
  },
  {
    "eventId": "E002",
    "deliveryId": "D-100",
    "type": "rider_location_update",
    "timestamp": "2026-05-02T10:05:00Z",
    "data": { "lat": 51.5080, "lng": -0.1290, "speed": 15 }
  },
  {
    "eventId": "E003",
    "deliveryId": "D-100",
    "type": "rider_location_update",
    "timestamp": "2026-05-02T10:10:00Z",
    "data": { "lat": 51.5095, "lng": -0.1320, "speed": 14 }
  },
  {
    "eventId": "E004",
    "deliveryId": "D-100",
    "type": "order_picked_up",
    "timestamp": "2026-05-02T10:12:00Z",
    "data": { "riderId": "R-10" }
  },
  {
    "eventId": "E005",
    "deliveryId": "D-100",
    "type": "rider_location_update",
    "timestamp": "2026-05-02T10:20:00Z",
    "data": { "lat": 51.5130, "lng": -0.1390, "speed": 16 }
  },
  {
    "eventId": "E006",
    "deliveryId": "D-100",
    "type": "delivery_completed",
    "timestamp": "2026-05-02T10:30:00Z",
    "data": { "actualDeliveryTime": "2026-05-02T10:30:00Z" }
  }
]
```

**Expected Behaviour:**

| Step | System Action | MongoDB State |
|------|--------------|---------------|
| E001 | Creates delivery record, starts monitoring | `status: "created"`, ETA stored |
| E002–E003 | Watchtower evaluates → healthy, no action | `healthScore: "green"`, no intervention docs |
| E004 | Updates delivery stage | `status: "in_transit"` |
| E005 | Watchtower evaluates → on track | `healthScore: "green"` |
| E006 | Marks complete, closes monitoring loop | `status: "completed"`, workflow archived |

**Pass Criteria:**
- Zero interventions triggered
- All events stored in MongoDB event history
- Watchtower agent ran at least 3 evaluation cycles (logged in `agentDecisions`)
- Delivery document has complete event timeline

---

### Scenario 1.2 — Bike Breakdown (Primary Demo Scenario)

**What it proves:** Full intervention lifecycle from anomaly detection through voice call to resolution.

**Requirements:** PC-1, PC-2, PC-3, PC-4, PC-6

**Event Sequence:**

```json
[
  {
    "eventId": "E010",
    "deliveryId": "D-200",
    "type": "delivery_created",
    "timestamp": "2026-05-02T11:00:00Z",
    "data": {
      "orderId": "ORD-5002",
      "riderId": "R-11",
      "customerId": "C-21",
      "restaurantLocation": { "lat": 51.5200, "lng": -0.0800 },
      "customerLocation": { "lat": 51.5350, "lng": -0.0650 },
      "estimatedDeliveryTime": "2026-05-02T11:30:00Z"
    }
  },
  {
    "eventId": "E011",
    "deliveryId": "D-200",
    "type": "order_picked_up",
    "timestamp": "2026-05-02T11:08:00Z",
    "data": { "riderId": "R-11" }
  },
  {
    "eventId": "E012",
    "deliveryId": "D-200",
    "type": "rider_location_update",
    "timestamp": "2026-05-02T11:12:00Z",
    "data": { "lat": 51.5230, "lng": -0.0770, "speed": 18 }
  },
  {
    "eventId": "E013",
    "deliveryId": "D-200",
    "type": "rider_location_update",
    "timestamp": "2026-05-02T11:17:00Z",
    "data": { "lat": 51.5230, "lng": -0.0770, "speed": 0 }
  },
  {
    "eventId": "E014",
    "deliveryId": "D-200",
    "type": "eta_update",
    "timestamp": "2026-05-02T11:18:00Z",
    "data": { "newETA": "2026-05-02T11:50:00Z", "reason": "system_recalculation" }
  },
  {
    "eventId": "E015",
    "deliveryId": "D-200",
    "type": "rider_location_update",
    "timestamp": "2026-05-02T11:22:00Z",
    "data": { "lat": 51.5230, "lng": -0.0770, "speed": 0 }
  }
]
```

**Simulated Voice Response (for Voice Agent):**

```json
{
  "callId": "CALL-001",
  "deliveryId": "D-200",
  "target": "rider",
  "riderId": "R-11",
  "transcriptSimulated": "My bike chain snapped, I can't move. I'm on Bethnal Green Road.",
  "extractedData": {
    "issue": "mechanical_failure",
    "subtype": "chain_broken",
    "riderCanContinue": false,
    "location": "Bethnal Green Road"
  }
}
```

**Expected Behaviour:**

| Step | System Action | MongoDB State |
|------|--------------|---------------|
| E010–E012 | Normal monitoring, healthy | `healthScore: "green"` |
| E013 | Watchtower detects: speed=0, same location as E012 | `healthScore: "amber"`, reasoning logged |
| E014 | ETA jumped +20min, combined with speed=0 → anomaly confirmed | `healthScore: "red"` |
| — | Intervention Planner decides: call rider | `interventions: [{ type: "call_rider", status: "pending" }]` |
| — | Voice Agent executes call | `interventions[0].status: "in_progress"`, transcript stored |
| — | Voice response parsed → mechanical_failure | `interventions[0].status: "completed"`, `extractedData` stored |
| — | Planner decides: notify customer + flag for reassignment | New intervention entries created |
| E015 | Confirms rider still stationary — consistent with reported issue | `status: "awaiting_reassignment"` |

**Pass Criteria:**
- Watchtower transitions health from green → amber → red with logged reasoning at each step
- Intervention Planner only acts after red (not amber) — shows restraint
- Voice call result stored as structured data in MongoDB
- Customer notification intervention queued after rider call completes
- Full decision chain traceable in `agentDecisions` array

---

## 2. Failure Recovery Scenarios

### Scenario 2.1 — System Crash Mid-Voice-Call

**What it proves:** System recovers from failure mid-tool-execution and resumes correctly.

**Requirements:** PC-5, PC-4, PC-6

**Setup:** Run Scenario 1.2 up to the point where Voice Agent begins the rider call. Then kill the process.

**Pre-Crash MongoDB State:**

```json
{
  "deliveryId": "D-200",
  "status": "intervention_active",
  "currentWorkflowStep": "voice_call_rider",
  "checkpoint": {
    "step": "voice_call_rider",
    "status": "in_progress",
    "startedAt": "2026-05-02T11:19:30Z",
    "callId": "CALL-001",
    "retryCount": 0
  },
  "pendingActions": ["notify_customer", "evaluate_reassignment"]
}
```

**Recovery Sequence:**

1. Restart the system
2. Recovery Agent scans MongoDB for `status: "intervention_active"` documents
3. Finds D-200 with incomplete voice call checkpoint
4. Evaluates: call started but no result recorded → needs retry or escalation

**Expected Behaviour:**

| Step | System Action | MongoDB State |
|------|--------------|---------------|
| Restart | Recovery Agent activates | Scans for incomplete workflows |
| Check | Reads checkpoint for D-200 | Determines voice call was in_progress |
| Decide | If call was <2 min ago → retry call; if >5 min → skip to escalation | Decision logged in `agentDecisions` |
| Resume | Executes retry or escalation | `checkpoint.retryCount: 1` or new escalation intervention |
| Continue | Picks up `pendingActions` and continues workflow | Customer notification proceeds |

**Pass Criteria:**
- No duplicate interventions (system doesn't re-call rider if call already completed)
- Recovery decision is logged with reasoning ("call started 3 minutes ago, no result, retrying")
- Pending actions from before crash are preserved and executed
- Workflow reaches the same end state as if no crash occurred

---

### Scenario 2.2 — Database Write Failure During State Update

**What it proves:** System handles partial write failures without corrupting delivery state.

**Requirements:** PC-5, PC-6

**Setup:** Simulate a MongoDB write timeout after the Watchtower evaluates but before the intervention is recorded.

**Injection Point:** After Watchtower writes `healthScore: "red"` but before Intervention Planner writes the `call_rider` action.

**Expected Behaviour:**

| Step | System Action | MongoDB State |
|------|--------------|---------------|
| Watchtower writes | Health updated to red | `healthScore: "red"` ✓ |
| Planner write fails | MongoDB timeout | No intervention document created |
| Next evaluation cycle | Watchtower sees red health, no intervention in progress | Triggers Planner again |
| Planner retries | Writes call_rider intervention | `interventions: [{ type: "call_rider" }]` |

**Pass Criteria:**
- System does NOT get stuck in a state where health is red but no intervention is ever triggered
- No phantom interventions (half-written documents)
- Idempotency: if the same decision is reached twice, only one intervention executes

---

### Scenario 2.3 — Voice Service (ElevenLabs) Unavailable

**What it proves:** Graceful degradation when an external tool call fails.

**Requirements:** PC-3, PC-5

**Setup:** Mock ElevenLabs API returning 503 for all requests.

**Expected Behaviour:**

| Step | System Action | MongoDB State |
|------|--------------|---------------|
| Voice call attempted | ElevenLabs returns 503 | `interventions[0].status: "failed"`, error logged |
| Retry 1 (after 30s) | Still 503 | `interventions[0].retryCount: 1` |
| Retry 2 (after 60s) | Still 503 | `interventions[0].retryCount: 2` |
| Fallback | Planner escalates to human operator or sends SMS | New intervention: `type: "escalate_to_human"` |

**Pass Criteria:**
- Retries are capped (not infinite)
- Fallback strategy activates after max retries
- Original voice intervention marked as `"failed"` with reason
- Workflow continues via alternative path, not stuck

---

## 3. Mid-Workflow Modification Scenarios

### Scenario 3.1 — Customer Cancels During Active Intervention

**What it proves:** System absorbs external changes mid-workflow without corruption.

**Requirements:** PC-7, PC-6, PC-4

**Event Sequence:** Start with Scenario 1.2 events, then inject cancellation after Watchtower has flagged the anomaly but before voice call completes:

```json
{
  "eventId": "E020",
  "deliveryId": "D-200",
  "type": "order_cancelled",
  "timestamp": "2026-05-02T11:20:00Z",
  "data": {
    "cancelledBy": "customer",
    "reason": "taking_too_long"
  }
}
```

**Expected Behaviour:**

| Step | System Action | MongoDB State |
|------|--------------|---------------|
| Pre-cancel | Voice call to rider in progress | `currentWorkflowStep: "voice_call_rider"` |
| E020 arrives | Event router flags priority change | `orderStatus: "cancelled"` |
| Planner re-evaluates | Cancels pending customer notification (no longer relevant) | `pendingActions` updated, customer notify removed |
| Voice call completes | Result still stored (rider info is useful for ops) | Transcript saved |
| Workflow adjusts | Instead of reassignment → mark delivery closed | `status: "cancelled_with_intervention"` |

**Pass Criteria:**
- Pending actions are pruned based on new context
- Completed actions are NOT rolled back (voice transcript preserved)
- Final status reflects both the cancellation and the intervention that occurred
- Agent reasoning log shows: "Order cancelled by customer — removing customer notification from pending actions, closing workflow"

---

### Scenario 3.2 — Priority Upgrade Mid-Delivery

**What it proves:** System can change intervention urgency on the fly.

**Requirements:** PC-7, PC-2

**Event Sequence:** Normal delivery in progress, then:

```json
{
  "eventId": "E025",
  "deliveryId": "D-300",
  "type": "priority_change",
  "timestamp": "2026-05-02T12:15:00Z",
  "data": {
    "previousPriority": "standard",
    "newPriority": "vip",
    "reason": "customer_is_premium_subscriber"
  }
}
```

**Expected Behaviour:**
- If delivery was in amber health and Watchtower was in "wait and observe" mode, the priority upgrade should push the Planner to intervene sooner
- Intervention thresholds should tighten (e.g., call rider after 3 min stationary instead of 5 min)
- MongoDB stores the priority change as part of the delivery context, and all subsequent agent decisions reference the updated priority

**Pass Criteria:**
- Agent decision log explicitly references priority level
- Intervention timing changes based on priority (demonstrable difference vs standard)

---

## 4. Context-Aware Reasoning Scenarios

### Scenario 4.1 — Repeat Offender Rider

**What it proves:** MongoDB history informs current decisions (context engine, not just storage).

**Requirements:** PC-2, PC-4

**Setup:** Pre-populate MongoDB with history for rider R-11:

```json
{
  "riderId": "R-11",
  "interventionHistory": [
    {
      "deliveryId": "D-050",
      "date": "2026-04-28",
      "issue": "rider_unresponsive",
      "callAttempts": 3,
      "resolved": false,
      "outcome": "reassigned"
    },
    {
      "deliverId": "D-080",
      "date": "2026-04-30",
      "issue": "significant_delay",
      "callAttempts": 1,
      "resolved": true,
      "outcome": "rider_resumed"
    }
  ]
}
```

**Now run Scenario 1.2 with rider R-11.**

**Expected Behaviour:**
- When Intervention Planner decides to call rider, it should reference the history
- Decision reasoning should note: "Rider R-11 has prior unresponsive incident — escalate sooner if call not answered within 60 seconds"
- Intervention strategy adapts: shorter timeout, quicker escalation to reassignment

**Pass Criteria:**
- Agent decision document includes `contextUsed: ["rider_history"]`
- Escalation threshold is measurably different from a rider with clean history
- MongoDB query for rider history is logged/traceable

---

### Scenario 4.2 — Repeat Complaint Customer

**What it proves:** Customer history changes communication strategy.

**Requirements:** PC-2, PC-3

**Setup:** Pre-populate:

```json
{
  "customerId": "C-21",
  "complaintHistory": [
    { "date": "2026-04-25", "type": "late_delivery", "compensation": "voucher_5" },
    { "date": "2026-04-29", "type": "late_delivery", "compensation": "voucher_5" }
  ],
  "customerTier": "at_risk"
}
```

**Expected Behaviour:**
- When customer notification is triggered, Voice Agent should use a more apologetic tone template
- Planner should flag for compensation in the intervention plan
- Decision log: "Customer C-21 has 2 recent complaints, marked at-risk — prioritising proactive update with apology"

---

## 5. Concurrency & Consistency Edge Cases

### Scenario 5.1 — Two Agents Act on Same Delivery Simultaneously

**What it proves:** State locking or conflict resolution prevents duplicate interventions.

**Requirements:** PC-6

**Setup:** Simulate two Watchtower evaluation cycles firing near-simultaneously (e.g., due to event backlog processing). Both detect the same anomaly.

**Expected Behaviour:**
- Only ONE intervention is created
- Second agent either: reads the lock/in-progress flag and skips, OR creates intervention but deduplication check removes it
- MongoDB should show one intervention document, not two

**Pass Criteria:**
- Exactly 1 voice call made (not 2)
- Deduplication logic logged
- No orphaned intervention documents

---

### Scenario 5.2 — Event Arrives Out of Order

**What it proves:** System handles event ordering gracefully.

**Requirements:** PC-6, PC-2

**Event Sequence:**

```json
[
  { "eventId": "E030", "type": "rider_location_update", "timestamp": "2026-05-02T13:10:00Z", "data": { "speed": 15 } },
  { "eventId": "E031", "type": "rider_location_update", "timestamp": "2026-05-02T13:05:00Z", "data": { "speed": 0 } },
  { "eventId": "E032", "type": "rider_location_update", "timestamp": "2026-05-02T13:15:00Z", "data": { "speed": 14 } }
]
```

Note: E031 has an earlier timestamp than E030 but arrives second.

**Expected Behaviour:**
- System processes by event timestamp, not arrival order
- Watchtower reconstructs timeline correctly: speed was 0 at 13:05, then 15 at 13:10, then 14 at 13:15
- Does NOT trigger anomaly (rider was briefly stopped, then resumed)

**Pass Criteria:**
- Events stored in MongoDB ordered by timestamp, not insertion order
- Watchtower reasoning references the corrected timeline

---

## 6. Boundary & Stress Cases

### Scenario 6.1 — Delivery With Zero Location Updates

**What it proves:** System handles missing data without crashing.

**Requirements:** PC-4, PC-5

**Event Sequence:** `delivery_created` → `order_picked_up` → long silence (no location events for 10 minutes)

**Expected Behaviour:**
- Watchtower should flag "no location data" as a distinct anomaly type (not the same as "rider stopped")
- Intervention strategy: check if GPS/system is working before calling rider
- Decision reasoning: "No location updates for 10 minutes — possible device issue or app crash"

---

### Scenario 6.2 — Rapid-Fire Events (Burst)

**What it proves:** System doesn't choke on high event volume.

**Requirements:** PC-6

**Setup:** Send 50 location updates for the same delivery within 10 seconds (simulating a GPS burst).

**Expected Behaviour:**
- SQS queue absorbs the burst
- Watchtower doesn't run 50 evaluation cycles — it batches or samples
- MongoDB stores all events but agent evaluation is throttled
- No duplicate interventions triggered by rapid re-evaluation

---

### Scenario 6.3 — Delivery Already Completed When Intervention Fires

**What it proves:** System checks current state before executing actions.

**Requirements:** PC-6, PC-4

**Setup:** Watchtower detects anomaly and queues an intervention. Before the intervention executes, a `delivery_completed` event arrives.

**Expected Behaviour:**
- Intervention Planner checks current delivery status before executing
- Finds `status: "completed"` → cancels the intervention
- Decision log: "Intervention cancelled — delivery already completed before execution"
- No voice call made

---

## 7. Demo Script (Hackathon Presentation)

### Recommended Demo Order (8–10 minutes)

**Act 1 — "It Works" (2 min)**
Run Scenario 1.1. Show the dashboard/logs. Point: "The system is monitoring but correctly doing nothing. That restraint is part of the intelligence."

**Act 2 — "It Catches Problems" (3 min)**
Run Scenario 1.2 (Bike Breakdown). Walk through each agent decision in MongoDB. Show the voice call transcript. Point: "Four agents coordinated across a multi-step workflow, each decision preserved in MongoDB."

**Act 3 — "It Survives Failure" (2 min)**
Run Scenario 2.1 (Crash Mid-Call). Kill the process live. Restart. Show recovery. Point: "The system resumed from its last checkpoint and completed the workflow. MongoDB held the reasoning state."

**Act 4 — "It Adapts" (2 min)**
Run Scenario 3.1 (Customer Cancels Mid-Intervention). Show the pending actions being pruned in real time. Point: "The workflow absorbed external changes without restarting. This is prolonged coordination."

**Closing (1 min)**
Show MongoDB — the full decision trail for one delivery. Every agent decision, every checkpoint, every intervention. "MongoDB isn't our database. It's our system's brain."

---

## 8. MongoDB Document Schemas (Expected)

### Delivery Document

```json
{
  "_id": "D-200",
  "orderId": "ORD-5002",
  "riderId": "R-11",
  "customerId": "C-21",
  "status": "in_transit",
  "priority": "standard",
  "healthScore": "green",
  "createdAt": "2026-05-02T11:00:00Z",
  "estimatedDeliveryTime": "2026-05-02T11:30:00Z",
  "events": [],
  "agentDecisions": [],
  "interventions": [],
  "checkpoint": {
    "step": null,
    "status": null,
    "updatedAt": null
  },
  "pendingActions": []
}
```

### Agent Decision Document

```json
{
  "decisionId": "DEC-001",
  "deliveryId": "D-200",
  "agent": "watchtower",
  "timestamp": "2026-05-02T11:17:30Z",
  "input": {
    "currentHealth": "amber",
    "lastLocationUpdate": "2026-05-02T11:17:00Z",
    "speed": 0,
    "timeSinceLastMovement": "5m",
    "etaDeviation": "+20m"
  },
  "reasoning": "Rider stationary for 5 minutes with 20-minute ETA increase. Pattern consistent with mechanical issue or accident. Escalating to red.",
  "decision": "escalate_health_to_red",
  "contextUsed": ["delivery_events", "rider_location_history"],
  "nextExpectedStep": "intervention_planner_evaluate"
}
```

### Intervention Document

```json
{
  "interventionId": "INT-001",
  "deliveryId": "D-200",
  "type": "call_rider",
  "status": "completed",
  "createdAt": "2026-05-02T11:18:00Z",
  "executedAt": "2026-05-02T11:18:30Z",
  "completedAt": "2026-05-02T11:19:45Z",
  "retryCount": 0,
  "callId": "CALL-001",
  "transcript": "My bike chain snapped, I can't move.",
  "extractedData": {
    "issue": "mechanical_failure",
    "riderCanContinue": false
  },
  "triggeredBy": "DEC-001",
  "followUpActions": ["notify_customer", "flag_reassignment"]
}
```

### Checkpoint Document

```json
{
  "deliveryId": "D-200",
  "step": "voice_call_rider",
  "status": "in_progress",
  "startedAt": "2026-05-02T11:18:30Z",
  "agentState": {
    "callId": "CALL-001",
    "retryCount": 0,
    "timeoutAt": "2026-05-02T11:20:30Z"
  },
  "pendingActions": ["notify_customer", "evaluate_reassignment"],
  "resumeStrategy": "retry_if_within_timeout_else_escalate"
}
```

---

## 9. Test Execution Checklist

Use this during development to track what passes:

| # | Scenario | Status | Notes |
|---|----------|--------|-------|
| 1.1 | Standard delivery (no intervention) | ⬜ | |
| 1.2 | Bike breakdown (full lifecycle) | ⬜ | |
| 2.1 | Crash mid-voice-call recovery | ⬜ | |
| 2.2 | DB write failure handling | ⬜ | |
| 2.3 | Voice service unavailable | ⬜ | |
| 3.1 | Customer cancels mid-intervention | ⬜ | |
| 3.2 | Priority upgrade mid-delivery | ⬜ | |
| 4.1 | Repeat offender rider (history-aware) | ⬜ | |
| 4.2 | Repeat complaint customer | ⬜ | |
| 5.1 | Duplicate intervention prevention | ⬜ | |
| 5.2 | Out-of-order events | ⬜ | |
| 6.1 | Zero location updates | ⬜ | |
| 6.2 | Rapid-fire event burst | ⬜ | |
| 6.3 | Completed delivery blocks intervention | ⬜ | |

---

## 10. Event Injection Script (Starter)

Use this to feed events into the SQS queue for testing:

```javascript
// inject-events.js
// Usage: node inject-events.js <scenario-file.json>

const AWS = require('aws-sdk');

const sqs = new AWS.SQS({
  endpoint: 'http://localhost:4566', // LocalStack
  region: 'eu-west-2',
  accessKeyId: 'test',
  secretAccessKey: 'test'
});

const QUEUE_URL = 'http://localhost:4566/000000000000/delivery-events';

async function injectEvents(scenarioFile) {
  const events = require(scenarioFile);

  for (const event of events) {
    console.log(`Injecting: ${event.eventId} (${event.type})`);

    await sqs.sendMessage({
      QueueUrl: QUEUE_URL,
      MessageBody: JSON.stringify(event),
      MessageAttributes: {
        'EventType': {
          DataType: 'String',
          StringValue: event.type
        }
      }
    }).promise();

    // Delay between events to simulate real timing
    // Adjust or remove for burst testing (Scenario 6.2)
    const delayMs = 2000;
    await new Promise(resolve => setTimeout(resolve, delayMs));
  }

  console.log(`Done. Injected ${events.length} events.`);
}

const scenarioFile = process.argv[2];
if (!scenarioFile) {
  console.error('Usage: node inject-events.js <scenario-file.json>');
  process.exit(1);
}

injectEvents(`./${scenarioFile}`);
```

---

## 11. Validation Queries (MongoDB)

Run these after each scenario to verify state:

```javascript
// Check all agent decisions for a delivery
db.deliveries.findOne(
  { _id: "D-200" },
  { agentDecisions: 1, interventions: 1, checkpoint: 1 }
)

// Verify no duplicate interventions
db.interventions.aggregate([
  { $match: { deliveryId: "D-200", type: "call_rider" } },
  { $group: { _id: "$type", count: { $sum: 1 } } }
])
// Expected: count = 1

// Check recovery agent picked up incomplete workflows
db.deliveries.find({
  "checkpoint.status": "in_progress",
  "status": { $ne: "completed" }
})

// Trace full decision chain for a delivery
db.deliveries.aggregate([
  { $match: { _id: "D-200" } },
  { $unwind: "$agentDecisions" },
  { $sort: { "agentDecisions.timestamp": 1 } },
  { $project: {
    agent: "$agentDecisions.agent",
    decision: "$agentDecisions.decision",
    reasoning: "$agentDecisions.reasoning",
    timestamp: "$agentDecisions.timestamp"
  }}
])
```
